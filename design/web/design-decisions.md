# Web Control Plane Design Decisions (Consolidated)

Status: Active


## Phase 2 Decision Addendum: C5 API Versioning Posture

Date: 2026-04-11
Owner: Systems Engineering

Decision:
1. `/api/v1` is the stable Phase 2 operator API surface.
2. Phase 2 API changes must be additive by default.
3. Any breaking or deprecated change requires explicit classification, rationale, and transition documentation before merge.
4. No `/api/v2` introduction is allowed during current Phase 2 scope.

Rationale:
1. Phase 2 requires controlled evolution without regressions for existing dashboard/staging/audit/settings flows.
2. Explicit additive-vs-breaking classification prevents uncontrolled schema and path drift.
3. LAN-only deployment still benefits from deterministic compatibility and rollback-safe operator behavior.

Implementation guardrails:
1. Versioning rules are defined in `design/web/api.md` under the C5 addendum.
2. Every API change must be reviewed against `design/infra/api-versioning-checklist.md`.
3. Integration tests must continue to assert presence of canonical `/api/v1` paths.

## Phase 2 Decision Addendum: C6 Dashboard Filter Sidebar

Date: 2026-04-11
Owner: Systems Engineering

Decision:
1. Dashboard file-type filtering is implemented client-side against already-loaded dashboard staging data.
2. Filter state is session-local and non-persistent.
3. Multiple file-type filters can be active simultaneously.
4. Filter option accents are derived from dashboard filter design tokens.

Rationale:
1. C6 requires improved operator focus without introducing API or backend scope.
2. Client-side filtering avoids server-coupling and preserves existing `/api/v1/staging` contract.
3. Session-local state aligns with Phase 1.5 interaction invariants and avoids global side effects.

Guardrails:
1. No backend endpoint changes for C6.
2. No server-side filtering logic.
3. Existing dashboard data loading behavior remains unchanged.


This document consolidates invariants, decisions, and rationale documents for the web control plane.

---

## Source Document: web-control-plane-techstack-decision.md

# Tech Stack Decision — Web Control Plane

Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Context

The photo-ingress project is a Python CLI application driven by systemd timers inside
an LXC container on LXD. The existing codebase is modular, uses SQLite via a registry
abstraction, and has zero web serving components today. This decision adds the minimal
technology required to expose a read/write operator control plane over HTTP.

Evaluation criteria in priority order:

1. Minimalism — smallest number of new runtime dependencies.
2. Fit with existing Python architecture — new components extend, not replace, existing
   domain and registry modules.
3. Maintainability — documented, well-supported, easy to reason about.
4. Containerised deployment on LXC/LXD — must be runnable as a systemd service inside
   the existing `photo-ingress` LXC container without Docker or secondary daemons.

---

## 2. ASGI Server: Uvicorn

### Options considered

| Option    | Notes |
|-----------|-------|
| Uvicorn   | Pure-Python ASGI server. Minimal, fast, official FastAPI default. |
| Hypercorn | Supports HTTP/2 and HTTP/3 but adds complexity not needed for LAN use. |
| Gunicorn  | WSGI only without a worker class; adds a process manager that duplicates systemd. |
| Daphne    | Tied to Django Channels ecosystem; not relevant here. |

### Decision: Uvicorn

**Rationale:**

- Single Python subprocess, trivially managed by a systemd unit.
- No process supervisor layer needed — systemd already provides restart, logging, and
  dependency ordering.
- First-class FastAPI integration with no configuration gaps.
- Well-understood resource footprint for LAN-only operator traffic (low concurrency).
- Installed as a single pip dependency alongside FastAPI.

**Deployment model inside LXC:**

Uvicorn runs as a systemd service (`photo-ingress-api.service`). It binds to either
`127.0.0.1` (localhost-only mode) or the container's LAN address depending on the
deployment phase. Port is configured in the project config file (default: 8000 or a
chosen unprivileged port). No separate reverse proxy is required in Phase 1.

---

## 3. API Framework: FastAPI

### Options considered

| Option   | Notes |
|----------|-------|
| FastAPI  | Modern async Python, Pydantic validation, OpenAPI generation, minimal overhead. |
| Flask    | Synchronous-first, no built-in OpenAPI, needs extensions for async. |
| Starlette | FastAPI is a thin layer on top; using Starlette directly would require manually recreating validation and routing. |
| Django REST Framework | Large dependency surface; full ORM and auth system is excess for this project. |
| aiohttp  | Framework + server bundled; less idiomatic for pure API services; no OpenAPI out of box. |

### Decision: FastAPI

**Rationale:**

- Sits directly on top of the existing Python ecosystem. Existing domain services and
  registry classes are imported directly — no ORM or framework-specific model layer is
  introduced.
- Pydantic handles request/response validation at the boundary, consistent with the
  existing project's validation-at-boundary design principle.
- Automatic OpenAPI schema generation removes doc maintenance overhead.
- Async-native: Uvicorn and FastAPI share the same async event loop model, allowing
  I/O-bound registry reads to be non-blocking.
- Minimal footprint: `fastapi` and `uvicorn` are the only new runtime packages required
  to serve the API. Pydantic is already used by FastAPI and fits the project's data
  validation philosophy.
- `photo-ingress-core` (existing domain services) is imported as a regular Python
  package inside the FastAPI application service layer. No duplication of business
  logic.

**Application structure:**

```
api/
  app.py             — FastAPI application factory and lifespan
  routers/           — Route modules grouped by resource
  services/          — Application service layer (translates HTTP to domain calls)
  schemas/           — Pydantic request/response models
  auth.py            — Bearer token validation dependency
  rate_limit.py      — Per-route rate limiting
  audit_hook.py      — Audit-first transaction wrapper
```

---

## 4. API Documentation UI: RapiDoc

### Options considered

| Option  | Notes |
|---------|-------|
| Swagger UI | Default FastAPI built-in. Functional but visually dated, heavy JS bundle. |
| ReDoc   | Clean, read-only, two-panel layout. Wide adoption, static serving. |
| RapiDoc | Modern dark-mode-native design, interactive, single JS file, no framework deps. |
| Scalar  | Newer entrant, polished, but less adoption track record. |

### Decision: RapiDoc

**Rationale:**

- The control plane UI uses a dark-mode design system. RapiDoc is dark-mode-native and
  visually consistent with the operator interface without custom CSS overrides.
- Single self-contained JS file, served as a static asset from the FastAPI application.
  No CDN dependency; deployable fully offline/LAN.
- Supports the same OpenAPI schema FastAPI generates — zero additional schema
  maintenance.
- Interactive: operators can fire test requests against the live API from the docs page,
  useful during triage workflow validation.
- ReDoc is still acceptable as a fallback (static, read-only), but provides lower
  operator utility. For a high-interactivity operator tool, RapiDoc is the better fit.

**Integration:** RapiDoc is mounted at `/api/docs` as a static HTML page that includes
the RapiDoc component pointed at `/api/openapi.json`. FastAPI generates the schema
automatically. No additional tooling required.

---

## 5. Summary Decision Table

| Component      | Decision    | Alternative considered | Key reason for choice |
|----------------|-------------|------------------------|----------------------|
| ASGI Server    | Uvicorn     | Hypercorn              | systemd-native, minimal, no extra process manager |
| API Framework  | FastAPI     | Flask, Starlette       | async, Pydantic, OpenAPI, fits existing Python arch |
| API Docs UI    | RapiDoc     | ReDoc                  | dark-mode-native, interactive, offline-safe single file |
| Frontend SPA   | SvelteKit   | React, Vue             | minimal runtime, compile-time output, no heavy framework |

---

## 6. Dependencies Not Introduced

The following were explicitly considered and excluded:

- **Docker / Docker Compose** — The existing LXC container already provides process
  isolation. Docker-in-LXC adds complexity with no operator benefit.
- **Message broker (Redis, RabbitMQ)** — Background job queue for sidecar generation is
  deferred to Phase 2. SQLite-backed polling is sufficient for Phase 1 queue depth.
- **External authentication server** — OIDC / OAuth is a deferred control. Static
  bearer token covers initial LAN-only deployment.
- **Nginx / Caddy in Phase 1** — Uvicorn binds directly. Reverse proxy TLS termination
  is a Phase 2 hardening step.
- **Celery or similar task runner** — Not introduced until sidecar/thumbnail worker
  scope becomes active (Phase 2+).

---

## 7. Revisit Criteria

This decision should be revisited if:

- Concurrent operator sessions exceed single-threaded Uvicorn capacity (threshold:
  sustained > 10 concurrent requests with p99 > 500ms).
- Authentication requirements advance to multi-user OIDC, requiring a more capable auth
  integration layer.
- The thumbnail worker reaches a volume requiring a proper background task queue.

---

## Source Document: web-control-plane-phase1-scope.md

# Phase 1 Re-Evaluation

Date: 2026-04-03 (rev 2: 2026-04-03, drift addendum: 2026-04-06)
Owner: Systems Engineering
Supersedes: Relevant sections of planning/planned/phase-2-architecture-roadmap.md (Phase 7),
            architecture.md#source-document-webui-architecture-phase1md (§2, §3.2, §6),
            detailed-design/design-tokens.md (§11),
            planning/implemented/web-design-source/webui-component-mapping-phase1.md (§3.1, §4.1, §6.1, §7.1, §7.3)

---

## 1. Purpose

This document re-evaluates the Phase 1 design in light of an external architectural
review. For each critique point, a disposition is assigned and justified. The document
closes with the final, amended Phase 1 scope.

Any design changes decided here are the authoritative record. Referenced source
documents are amended separately where noted.

### 1.1 Implementation drift addendum (2026-04-06)

Implementation has advanced through Phase 1 Chunks 0-5, while Chunk 6 remains open.
This document remains the decision baseline, but execution sequencing is now tracked in:

- `planning/implemented/web-control-plane-phase1-implementation-roadmap.md`
- `planning/planned/phase-2-architecture-roadmap.md`

Rate-limiting posture clarification:
- Phase 1 does not include request-throttling implementation as a completion requirement.
- All operator-access throttling is deferred to the Phase 2 proxy-level LAN gate.
- LAN exposure is blocked until the Phase 2 proxy gate (including proxy-level throttling)
  is implemented and signed off.

---

## 2. Critique Disposition Table

| # | Critique Point | Disposition | Phase |
|---|---------------|-------------|-------|
| C1 | SSR should remain an optional future capability, not rejected | Modified Phase 1 | Phase 1 decision amended; delivery of SSR deferred to Phase 2 optional |
| C2 | Reverse proxy not needed in Phase 1, mandatory in Phase 2 | Phase 2 mandatory | Promotes integration-plan Phase 7 (optional) to Phase 2 (mandatory) |
| C3 | Health polling belongs in a dedicated store, not in `+layout.js` | Modified Phase 1 | Small structural fix applied within Phase 1 |
| C4 | API versioning should be formalised early | Keep Phase 1 as-is | Already present; formal versioning strategy documented in Phase 2 doc |
| C5 | Build artifacts should be versioned for rollback | Phase 2 | Not needed for initial operator deployment; introduced at hardening stage |
| C6 | SQLite concurrency acceptable for Phase 1; migration path needed | Phase 2 optional | Phase 1 stays SQLite with WAL; migration path documented in Phase 2 doc |
| C7 | Retry/backoff in API client for Phase 2 | Phase 2 | Phase 1 uses fail-fast; retry adds complexity without Phase 1 benefit |
| C8 | Keep Phase 1 minimal; defer non-essential complexity | Guiding principle | Applied per-item; see §3.8 |
| C9 | Filter Sidebar not essential for Phase 1 | Phase 2 mandatory | Phase 1 uses full-width main content; sidebar deferred |
| C10 | Infinite Scroll in Audit Timeline is Phase 2 complexity | Modified Phase 1 | Phase 1 uses explicit `LoadMoreButton` cursor pagination; infinite scroll deferred |
| C11 | KPI Thresholds must not be hard-coded in UI | Modified Phase 1 | Thresholds served from `GET /api/v1/config`; no hardcoded values in SPA |
| C12 | Photo-Wheel blur levels should be tokenized | Modified Phase 1 | Raw `4px`/`8px` values replaced with `--wheel-blur-near`/`--wheel-blur-far` tokens |

---

## 3. Per-Critique Justification

### C1 — SSR: Deferral, Not Rejection

**Original decision:** architecture.md#source-document-webui-architecture-phase1md §2 states SSR is disabled and gives four
reasons for the choice. The original framing implies a permanent rejection.

**Critique:** The critique correctly observes that permanently rejecting SSR forecloses
a useful future capability (faster perceived load, better error boundaries, potential
server-side auth guard simplification). It should be deferred, not excluded.

**Amendment:** The Phase 1 design is unchanged — `@sveltejs/adapter-static` and
`ssr = false` remain correct for Phase 1. The language in architecture.md#source-document-webui-architecture-phase1md §2 is
updated to state "deferred" rather than "disabled/rejected". The conditions under which
SSR becomes worth revisiting are:
- Operator count grows beyond a single LAN user (requires real auth session management).
- A Node.js server process becomes acceptable in the LXC deployment topology.
- Page load time on low-bandwidth LAN connections becomes a reported pain point.

Until one of these conditions is met, the adapter-static SPA approach is optimal.
The SSR upgrade path is documented in web-control-plane-architecture-phase2.md.

**Documents affected:** architecture.md#source-document-webui-architecture-phase1md §2.

---

### C2 — Reverse Proxy: Phase 1 Stays Direct, Phase 2 Mandatory

**Original decision:** integration-plan.md placed Nginx/Caddy introduction as "Phase 7:
Optional". This was too weak a commitment given the security requirements.

**Critique:** The critique is correct. For any LAN-exposed deployment, TLS, request
logging, Brotli compression, and proxy-level rate limiting are operational necessities,
not optional enhancements. Calling this "optional" understated the risk.

**Amendment:** The reverse proxy is reclassified from Phase 7 optional to Phase 2
mandatory. Phase 1 retains direct Uvicorn binding to `127.0.0.1` (localhost-only).
Phase 2 is not reached until the reverse proxy is in place.

The integration-plan.md phase table is not amended directly; this document
supersedes phase 7's classification. Phase 2 architecture is defined in
web-control-plane-architecture-phase2.md.

**Phase 1 unchanged:** Phase 1 binds Uvicorn to localhost. LAN exposure is not
unlocked until Phase 2 with the reverse proxy in place.

---

### C3 — Health Polling: Moved from Layout to Store Module

**Original decision:** architecture.md#source-document-webui-architecture-phase1md §3.2 and §6.2 placed `setInterval` polling
for health data inside `+layout.svelte`'s `onMount`. This works but is an architectural
misplacement: layout files should be responsible only for rendering, not for data
lifecycle management.

**Critique:** Correct. Polling is a side-effect concern. It belongs in the store that
owns the health data, not in the component that renders it.

**Amendment (Phase 1 scope change):**

- `health.svelte.js` store takes ownership of the polling lifecycle.
- The store exposes a `connect()` function that starts the polling interval and a
  `disconnect()` function that tears it down.
- `+layout.svelte` calls `health.connect()` in its `onMount` and `health.disconnect()`
  in its `onDestroy`.
- `+layout.js` no longer performs a health fetch at navigation time. The store provides
  the reactive health state directly.
- `AppHeader` and `AppFooter` subscribe to the health store for their reactive data.

This change has no user-visible impact. It produces a cleaner component/store boundary
and makes the polling lifecycle independently testable.

**Documents affected:** architecture.md#source-document-webui-architecture-phase1md §3.2, §6.1, §6.2.

---

### C4 — API Versioning: Already Present; Strategy Formalised in Phase 2 Doc

**Original decision:** All API endpoints in integration-plan.md already use the
`/api/v1/` prefix.

**Critique:** The critique asks that versioning be "formalised early". The `/api/v1/`
prefix is already in place. What is missing is a documented policy covering:
- When a v2 is warranted.
- Deprecation timeline rules.
- How breaking vs non-breaking changes are classified.

**Amendment:** No Phase 1 scope change. The versioning policy is documented formally in
web-control-plane-architecture-phase2.md §3 as a mandatory Phase 2 deliverable, to be written before any
mutating endpoint leaves experimental status. Since Phase 1 endpoints are read-only and
internal, the risk of versioning drift is low in Phase 1.

---

### C5 — Build Artifact Versioning: Phase 2

**Original decision:** project-structure.md describes `webui/build/` as a deployment
artifact deployed by overwrite (`rsync`). No versioning or rollback mechanism exists.

**Critique:** Correct in direction, but premature for Phase 1. During Phase 1, the
operator is the sole user and the system is on localhost. Overwrite deployment is
acceptable.

**Decision: Phase 2.** Artifact versioning is introduced as part of Phase 2 hardening,
alongside the reverse proxy. The reverse proxy can serve from a versioned directory,
making rollback atomic (symlink swap). This is documented in web-control-plane-architecture-phase2.md §4.

**Phase 1 unchanged:** `rsync` overwrite of `webui/build/` is acceptable for
localhost-only Phase 1 deployment.

---

### C6 — SQLite Concurrency: Phase 1 Acceptable; Migration Path Phase 2 Optional

**Original decision:** integration-plan.md §12 already documents WAL mode for
concurrent reads. Phase 1 stays SQLite.

**Critique:** Correctly identifies that SQLite is an acceptable Phase 1 database for
low-concurrency operator use, but a migration path should be anticipated.

**Decision:** Phase 1 unchanged. The migration path from SQLite to Postgres is
documented in web-control-plane-architecture-phase2.md §6 as a Phase 2 optional feature. It will not
be actioned unless one of these triggers is met:
- Concurrent write contention causes measurable latency (> 100ms on triage actions).
- The operator count grows to require multi-user concurrent sessions.
- Background worker jobs produce sustained write traffic alongside API writes.

---

### C7 — Retry/Backoff: Phase 2

**Original decision:** architecture.md#source-document-webui-architecture-phase1md §7 documents the API client error handling
strategy as fail-fast: non-2xx responses throw a typed `ApiError`; the component
renders an `ErrorBanner`. No retries are performed.

**Critique:** Retry/backoff is suggested for Phase 2.

**Decision: Phase 2.** Fail-fast is the correct Phase 1 behaviour because:
- The operator is the only user; a visible error banner is sufficient feedback.
- Retry logic on mutating endpoints (triage) requires idempotency key management across
  retries, which adds state complexity.
- Transparent retries on read endpoints could mask connection problems the operator
  needs to see.

Phase 2 introduces selective retry with backoff on read-only endpoints (health, KPIs)
where transient errors are expected and silent retry is safe. Mutating endpoints remain
fail-fast with idempotency key replay as the retry mechanism. This is documented in
web-control-plane-architecture-phase2.md §5.

---

### C8 — Phase 1 Minimalism: Applied as a Filter

**Decision:** This principle was used as a filter across all items above. The consistent
outcome: everything that requires new processes, new dependency classes, or multi-user
concerns moves to Phase 2. Phase 1 scope contracts to:

- One Python process (Uvicorn) serving both the API and the static UI assets.
- Localhost-only binding.
- Single SQLite database with WAL mode.
- Fail-fast API client.
- Static SPA with polling in a store (C3 amendment).
- `/api/v1/` prefix already in place (C4).
- No Node.js process at runtime.

---

### C9 — Filter Sidebar: Phase 2 Mandatory

**Original design:** planning/implemented/web-design-source/webui-component-mapping-phase1.md §4.1 listed `FilterSidebar` as a Phase 1 Dashboard
component providing file-type filtering (`All Files`, `Images`, `Videos`, `Documents`).

**Critique:** The sidebar is browsing ergonomics, not core operator workflow. The
operator can triage, audit, and manage the blocklist without type filtering in
Phase 1.

**Decision: Phase 2 mandatory.** Justification:
- The filter sidebar requires a filter-state store, filter parameters propagated to all
  Dashboard API calls, the API returning counts broken down by file type, a sidebar
  collapse/drawer on tablet, and a modal sheet on mobile — a non-trivial slice of work.
- The core workflow is type-agnostic in Phase 1. The queue is small enough that an
  unfiltered view is fully usable.
- No API endpoint changes are deferred by this decision: `GET /api/v1/staging/items`
  already supports a `type` query parameter per the integration plan.

**Phase 1 change:** Phase 1 Dashboard uses a full-width main content area (no sidebar
column). The `FilterSidebar` component is not built. The layout diagram in planning/implemented/web-design-source/webui-component-mapping-phase1.md
§3.1 is annotated with a deferral note.

**Phase 2 scope:** Filter Sidebar introduction is documented in web-control-plane-architecture-phase2.md
§13.

**Documents affected:** planning/implemented/web-design-source/webui-component-mapping-phase1.md §3.1 (annotation), §4.1 (deferral note), §6.1
(note).

---

### C10 — Infinite Scroll: Phase 1 Uses LoadMoreButton Pagination

**Original design:** planning/implemented/web-design-source/webui-component-mapping-phase1.md §7.3 specified automatic infinite scroll for the
Audit Timeline: "On scroll near the bottom of the list, the next page is loaded
automatically (infinite scroll with a load threshold of 80% of container height)."

**Critique:** Infinite scroll adds complexity that is not justified for Phase 1. The
Audit Timeline will contain tens to low hundreds of events in normal Phase 1 use.

**Decision: Modified Phase 1.** Phase 1 uses cursor-based pagination via an explicit
`LoadMoreButton` component (already listed as `Load-more / pagination → LoadMoreButton`
in planning/implemented/web-design-source/webui-component-mapping-phase1.md §4.3). The automatic IntersectionObserver scroll trigger is removed
from Phase 1. Operators click "Load more" to fetch the next cursor page.

**Phase 1 behaviour:**
- Audit Timeline loads first page (default 20 items) on mount.
- `LoadMoreButton` appears below the list if more pages are available.
- Clicking it appends the next cursor page to the existing list.
- Changing the action-type filter resets cursor and reloads from page one.

**Phase 2 scope:** Replacing `LoadMoreButton` with IntersectionObserver-based automatic
scroll loading is documented in web-control-plane-architecture-phase2.md §14.

**Documents affected:** planning/implemented/web-design-source/webui-component-mapping-phase1.md §7.3 (scrolling description).

---

### C11 — KPI Thresholds: From API Config, Not Hard-Coded

**Original design:** detailed-design/design-tokens.md §11 defined a hard-coded threshold table per KPI
metric (e.g., Pending in Staging: green 0–50, amber 51–200, red >200). These values
would have been static constants baked into the SPA build.

**Critique:** Thresholds are operational configuration, not visual constants. Hard-coding
them in the UI requires a UI rebuild every time deployment-specific thresholds need
adjustment.

**Decision: Modified Phase 1.** The thresholds are served from the existing
`GET /api/v1/config` endpoint (already in integration-plan.md Phase 1). The endpoint
returns a `kpi_thresholds` object with per-metric warning and error boundaries. The
`config.svelte.js` store caches this response. `KpiCard` receives thresholds as props
from the parent page/store; no hardcoded values remain in the SPA.

**What changes for Phase 1:**
- detailed-design/design-tokens.md §11: Hard-coded threshold table removed. Replaced with a design
  note explaining that thresholds are runtime configuration values from the config API.
- KpiCard props: `thresholds: { warning: number, error: number }` (passed in).
- The config endpoint's `kpi_thresholds` field is specified in the API integration
  document; the threshold values come from `photo-ingress.conf` on the server
  (operator configures by editing the config file in Phase 1).

**Phase 2 scope:** A settings UI allowing in-place threshold editing via
`PATCH /api/v1/config/thresholds` is documented in web-control-plane-architecture-phase2.md §15.

**Documents affected:** detailed-design/design-tokens.md §11 (remove threshold table; add config-API
note); web-control-plane-integration-plan.md config endpoint response shape (noted change,
no new file required).

---

### C12 — Photo-Wheel Blur Tokenization

**Original design:** planning/implemented/web-design-source/webui-component-mapping-phase1.md §7.1 specified raw pixel values in the visual
transform rules table: `4px` for ±1 offset cards, `8px` for ±2 offset cards.

**Critique:** detailed-design/design-tokens.md §1 explicitly states that "no raw values appear in
component styles". Using raw `4px` and `8px` in the interaction spec contradicts the
token-first principle already established for the project.

**Decision: Modified Phase 1.** This is a quality correction, not a feature change.
Three tokens are added to detailed-design/design-tokens.md in a new §13:

- `--wheel-blur-center` = `0px` (center card, fully sharp)
- `--wheel-blur-near` = `4px` (cards at ±1 offset)
- `--wheel-blur-far` = `8px` (cards at ±2 offset)

The visual transform rules table in planning/implemented/web-design-source/webui-component-mapping-phase1.md §7.1 references these tokens.
No visual change to the user.

**Documents affected:** detailed-design/design-tokens.md (new §13: Photo Wheel Visual Transform Tokens);
planning/implemented/web-design-source/webui-component-mapping-phase1.md §7.1 (Blur column).

---

## 4. Phase 1 Final Scope (Amended)

The following table defines what is and is not in Phase 1 after the re-evaluation.

### 4.1 In Scope

| Item | Notes |
|------|-------|
| Uvicorn + FastAPI on `127.0.0.1` | Localhost only; no LAN exposure |
| Read-only API endpoints (`/api/v1/`) | health, staging, items, audit-log, config, blocklist |
| Static bearer token auth | Token in `photo-ingress.conf [web]` section |
| RapiDoc at `/api/docs` | Served as static asset; exempted from auth |
| SvelteKit adapter-static SPA | No Node.js process at runtime |
| Dark-mode design token system | `tokens.css` as CSS custom properties |
| `health.svelte.js` store with polling | Store owns `connect()` / `disconnect()` lifecycle |
| `+layout.svelte` subscribes to health store | No fetching, no polling in layout |
| Write path: triage (accept/reject/defer) | With idempotency keys, audit-first writes |
| Write path: blocklist CRUD | With idempotency keys, confirmation dialog |
| SQLite WAL mode concurrency | Shared between CLI and API process |
| Fail-fast API client | `ApiError` thrown; `ErrorBanner` rendered |
| `/api/v1/` URL prefix | Version prefix already in place |
| Request-throttling policy | Deferred: no Phase 1 throttling implementation gate; proxy-level throttling is mandatory in Phase 2 before LAN exposure |
| Structured audit for auth failures | 401/403 events written to audit_log |
| Input validation on all route parameters | Via Pydantic models at API routers |
| CORS allowlist to configured UI origin | Default: `http://localhost:8000` |
| Security headers (X-Content-Type-Options etc.) | Via FastAPI middleware |
| Photo-Wheel blur levels tokenized | `--wheel-blur-near` / `--wheel-blur-far` tokens in detailed-design/design-tokens.md (C12) |
| KPI thresholds from `GET /api/v1/config` | `kpi_thresholds` object; no hardcoded values in SPA (C11) |
| Audit Timeline: `LoadMoreButton` cursor pagination | Explicit click to load next page; no infinite scroll (C10) |

### 4.2 Explicitly Deferred to Phase 2

| Item | Phase 2 Classification |
|------|----------------------|
| LAN exposure | Mandatory (requires reverse proxy first) |
| Reverse proxy (Nginx/Caddy) | Mandatory |
| TLS termination | Mandatory (via reverse proxy) |
| Brotli compression | Mandatory (via reverse proxy) |
| Proxy-level rate limiting | Mandatory (Phase 2 LAN-exposure gate) |
| Build artifact versioning and rollback | Mandatory |
| API versioning policy document | Mandatory |
| Retry/backoff for read-only API client calls | Mandatory |
| SSR capability | Optional (see C1 conditions) |
| SQLite → Postgres migration | Optional |
| Background worker (sidecar/thumbnail) | Optional |
| Task queue (Redis or alternative) | Optional |
| OIDC/OAuth authentication | Optional |
| CDN or asset caching | Optional |
| Filter Sidebar | Mandatory (Phase 1 Dashboard uses full-width layout without type filtering) |
| Audit Timeline infinite scroll | Mandatory (Phase 1 uses LoadMoreButton; IntersectionObserver approach deferred) |
| KPI threshold settings UI | Mandatory (Phase 2 introduces `PATCH /api/v1/config/thresholds` + Settings page form) |

---

## 5. Documents Amended by This Re-Evaluation

| Document | Sections affected | Nature of change |
|----------|------------------|-----------------|
| `architecture.md#source-document-webui-architecture-phase1md` | §2, §3.2, §6.1, §6.2 | SSR framing (C1); health polling ownership (C3) |
| `planning/planned/phase-2-architecture-roadmap.md` | Phase table, Phase 7 | Phase 7 reclassified via this document; no direct edit required |
| `detailed-design/design-tokens.md` | §11, new §13 | KPI threshold table removed, config-API note added (C11); Photo-Wheel blur tokens added (C12) |
| `planning/implemented/web-design-source/webui-component-mapping-phase1.md` | §3.1, §4.1, §6.1, §7.1, §7.3 | Filter Sidebar deferred to Phase 2 (C9); blur tokenization (C12); LoadMoreButton pagination (C10) |

---

## Source Document: photowheel-visual-design-decisions.md

# PhotoWheel Visual Design Decisions

Date: 2026-04-08
Owner: Systems Engineering
Scope: Binding design decisions for PhotoWheel fidelity alignment with approved mockup

---

## Purpose

This document records authoritative design decisions for the PhotoWheel component.
These decisions close the fidelity gap between the current staging implementation
and the approved mockup (`design/ui-mocks/Astronaut photo review interface.png`).

A root-cause analysis identified three categories of visual divergence. This
document makes binding choices for each, states the rationale, and defines the
visual invariants that any conforming implementation must satisfy.

These decisions supersede any conflicting behavioral description in earlier
documents. Where earlier documents (e.g. `planning/implemented/web-design-source/webui-component-mapping-phase1.md` §7.1)
describe the same properties, the values in this document take precedence.

---

## Reference Documents

| Document | Role |
|----------|------|
| `design/ui-mocks/Astronaut photo review interface.png` | Approved visual target |
| `planning/implemented/web-design-source/webui-component-mapping-phase1.md` §2.2, §7.1 | Mockup analysis and interaction spec |
| `detailed-design/design-tokens.md` | Token catalogue |
| `staging-token-mismatch-root-cause.md` | Prior staging diagnostic |

---

## Decision A — Wheel Viewport and Navigation Model

### A.1 Viewport Model

**Decision: bounded viewport with clipped overflow.**

The PhotoWheel renders inside a viewport container that:

1. Has a maximum width equal to the available content area of the page layout.
   The wheel does not produce a horizontal scrollbar and does not extend
   beyond the page content bounds.
2. Clips card content that extends beyond the viewport edges. Cards at the
   periphery of the visible range are cut off at the container boundary,
   creating the visual impression that the deck continues beyond the
   visible frame.
3. Centers the focused (active) card horizontally within the viewport.
   The active card is always at the horizontal midpoint of the container.

**Overflow behavior:** `overflow: hidden`. The wheel is not a scrollable
region. Navigation is performed exclusively through the input model
(keyboard, mouse wheel, touch gesture, card click) — never by scrollbar.

**Width behavior:** The viewport fills its parent's content width. It does
not define its own fixed pixel width. On narrow viewports, responsive
rules from `planning/implemented/web-design-source/webui-component-mapping-phase1.md` §6 apply (reduced visible
card count).

### A.2 Centering Rules

The active card is always positioned at the horizontal center of the
viewport. Non-active cards are positioned relative to the active card's
center point. The centering contract is:

- The midpoint of the active card aligns with the midpoint of the
  viewport container.
- Cards to the left and right of the active card are positioned
  symmetrically outward from center.
- When the active index changes, the arrangement recenters on the new
  active card with an animated transition.

### A.3 Navigation Topology

**Decision: finite, clamped.**

The wheel is a finite linear sequence. Navigation stops at index 0 (first
item) and index N-1 (last item). There is no wrap-around from last to
first or first to last.

**Rationale:** The staging queue is an ordered work list. Wrapping would
create ambiguity about which items have been reviewed and would complicate
the triage workflow. The user needs clear start and end boundaries.

**Boundary behavior:**

- Keyboard: ArrowLeft at index 0 is a no-op. ArrowRight at index N-1
  is a no-op.
- Mouse wheel: scroll events at the boundary are released to the page
  (not captured), allowing the user to scroll past the wheel.
- Touch: swipe gestures at the boundary are no-ops. Momentum is
  cancelled at the boundary (existing `cancelledByBoundary` behavior
  is correct).

### A.4 Non-Goals

- Infinite/circular navigation is not supported.
- Scroll-based panning within the wheel container is not supported.
- Programmatic "scroll to" with arbitrary pixel offsets is not supported.
- The wheel does not participate in the page's scroll position.

---

## Decision B — Card Geometry, Overlap, and Depth Model

### B.1 Geometric Model

**Decision: arc-based 3D geometry with Y-axis rotation.**

Cards are arranged along an implied circular arc in 3D space. The active
card faces the viewer directly. Cards to the left and right progressively
rotate away from the viewer around the Y axis, creating the visual
impression that the card deck curves into the background.

This is a 3D carousel with perspective projection, not a linear track
with depth cues.

### B.2 Card Transform Tiers

Cards are assigned to one of three visual tiers based on their positional
distance from the active card.

**Tier 0 — Active (distance = 0):**
- Faces the viewer directly (no Y-axis rotation).
- Full scale, full opacity, no blur.
- Highest Z-order; visually in front of all other cards.
- Positioned at the horizontal center of the viewport.

**Tier 1 — Adjacent (distance = 1):**
- Rotated on the Y axis toward the viewer's periphery. Left card
  rotates clockwise (positive rotateY); right card rotates
  counter-clockwise (negative rotateY).
- Reduced scale relative to the active card.
- Partial overlap with the active card. The near edge of each adjacent
  card extends behind the active card.
- Reduced opacity.
- Moderate depth blur per design tokens.

**Tier 2 — Distant (distance >= 2):**
- Greater Y-axis rotation than Tier 1.
- Further reduced scale.
- Greater overlap; cards may partially occlude each other.
- Lower opacity.
- Strongest depth blur per design tokens.
- Cards beyond the viewport edge are clipped by the container.

### B.3 Overlap Rules

**Decision: cards overlap. Adjacent cards extend partially behind the
active card.**

The current flex-with-gap layout prevents overlap and contradicts the
mockup. The corrected model requires:

1. Cards do not have positive spacing (gap) between them. Instead,
   adjacent cards share horizontal space with the active card.
2. Overlap is achieved through the combination of:
   - Y-axis rotation (which foreshortens the card, making its far edge
     recede and its near edge advance).
   - Horizontal positioning that places adjacent cards closer to center
     than a non-overlapping layout would.
3. The overlap amount increases with distance from the active card.
   Tier 2 cards overlap Tier 1 cards; Tier 1 cards overlap the active
   card.
4. Z-ordering ensures the active card is always visually on top,
   Tier 1 cards are behind the active card but in front of Tier 2, and
   so on.

### B.4 Depth Ordering

Z-order assignment follows a strict depth-from-center rule:

- Active card: highest z-index within the wheel.
- Distance 1: lower z-index than active.
- Distance 2+: lower z-index than distance 1.
- Within the same distance tier, z-index values are equal (left and
  right mirror each other).

The `translateZ()` values, `scale()` values, and `z-index` values all
decrease monotonically with distance from center. No card at a greater
distance may visually occlude a card at a lesser distance.

### B.5 Perspective Context

The wheel container establishes a CSS perspective context. All card
transforms are interpreted relative to this shared context. The
perspective origin is the center of the wheel container.

### B.6 Visual Invariants

The following invariants must hold in any conforming implementation:

| ID | Invariant |
|----|-----------|
| VIS-1 | The active card is always the frontmost card at center. |
| VIS-2 | Adjacent cards are partially behind and overlapping the active card. |
| VIS-3 | Cards farther from center appear smaller, more rotated, more blurred, and more transparent. |
| VIS-4 | The depth illusion is continuous — no visual discontinuity between tiers. |
| VIS-5 | Transitions between active index changes are animated; no instantaneous position jumps. |
| VIS-6 | The wheel visual is symmetric: left and right sides mirror each other about the active card. |
| VIS-7 | Cards beyond the viewport boundary are clipped, not hidden or removed. |

#### VIS-1 Validation Note — Perceptual Invariant, Not a Pixel Gate

VIS-1 ("the active card is the frontmost card at center") is validated as a
**perceptual invariant**. It is satisfied by the combination of:

- **Frontmost**: enforced by z-index ordering (active card z-index > all
  other tiers). The active card is never occluded.
- **At center**: fulfilled perceptually through the depth model — the active
  card has maximum scale, zero Y-axis rotation, and full opacity, making it
  the visually dominant element anchoring the cluster regardless of its
  exact pixel coordinate within the viewport.

**VIS-1 is not a pixel-position gate.** It does not require the active
card's bounding-box midpoint to equal the viewport's midpoint in absolute
pixels. Absolute-position centering is constrained by the render-window +
spacer architecture and varies at boundary states (see Decision A.2 —
Centering Invariant, Revised). VIS-1 is considered satisfied when:

1. No other card visually occludes or overlaps the active card's front face.
2. The active card is visually dominant (largest, most opaque, least blurred,
   zero rotation) relative to all other visible cards.
3. The depth cues (overlap, rotation, scale, blur) collectively convey that
   the active card is the perceptual center of the visible cluster.

Acceptance testing for VIS-1 must verify conditions (1)–(3) rather than
asserting a pixel-level position equality.

#### VIS-1 — Stage-Model Restatement

Under Decision D (Stage-Based Slot Architecture), VIS-1 is a **structural
invariant** of the layout, not merely a perceptual one:

- **Frontmost**: enforced by z-index ordering (unchanged).
- **At center**: enforced by the center slot's fixed position at the
  viewport midpoint. The active item is always bound to the center slot.
  Center is a CSS construction, not an approximation.

The perceptual validation criteria (1)–(3) above remain valid as a
fallback verification method, but the primary guarantee is architectural.
Under the stage model, VIS-1 acceptance testing may additionally assert
that the active card's bounding-box midpoint equals the viewport's
horizontal midpoint within a small pixel tolerance (e.g., ±2px).

### B.7 Non-Goals

- Exact rotation angles, scale factors, and overlap pixel values are not
  specified here. Those are tuning parameters for implementation.
- The arc does not need to follow a mathematically precise circle. A
  visually convincing approximation using tiered transforms is acceptable.
- Per-card configurable geometry is not supported. All cards in the same
  tier receive the same transform treatment.

---

## Decision C — Thumbnail Loading and Error Visibility

### C.1 Loading Strategy

**Decision: load on render-window entry; preload on idle.**

Thumbnails are loaded when a card enters the render window (determined
by `RENDER_RADIUS`). The browser's `loading="lazy"` attribute controls
the exact moment of the network request within the rendered DOM.

In addition, when the wheel interaction state is idle, adjacent
thumbnails within `PRELOAD_RADIUS` are preloaded via programmatic
`Image()` objects. This ensures that thumbnails for the next likely
navigation targets are cached before the user scrolls.

Thumbnails are not loaded based on focus alone. They are not loaded
on explicit user retry action in the current design.

### C.2 Error State Semantics

**Decision: error state is transient, scoped to a card's render
lifecycle.**

When a thumbnail fails to load, the card enters an error state and
displays a visible fallback label ("IMAGE ERROR", "VIDEO FILE", or
"DOCUMENT FILE" depending on the file extension).

The error state is not permanent across the item's lifetime. It is
reset when:

- The card unmounts (scrolls out of the render window) and re-mounts
  (scrolls back into the render window). The windowing system
  naturally causes re-mount, which resets image state to "loading"
  and triggers a fresh load attempt.
- The item's identity (`sha256`) changes, which resets image state.

The error state is not reset by:

- Timer-based automatic retry.
- User clicking the error card.
- Focus change to or from the card.

### C.3 Retry Semantics

**Decision: implicit retry via re-render; no explicit retry mechanism.**

There is no retry button, timer, or automatic backoff for failed
thumbnails. The natural retry path is:

1. User scrolls the failed card out of the render window.
2. User scrolls back. The card re-mounts; the thumbnail re-requests.

This is sufficient because:

- Thumbnail failures are expected to be rare (backend generates
  thumbnails lazily; most failures are transient 404s during
  initial generation).
- The windowing system already unmounts and remounts cards as the
  user navigates, providing organic retry opportunities.
- Adding explicit retry would require additional interaction surface
  and state management with no meaningful UX benefit for the
  expected failure rate.

### C.4 Fallback Display Rules

When a thumbnail is in error state, the card displays a text label
in place of the image. The label is determined by the file's extension:

| Extension class | Label |
|----------------|-------|
| Image files (.jpg, .jpeg, .png, .webp, .gif, .bmp, .tiff, .heic, .heif) | IMAGE ERROR |
| Video files (.mp4, .mov, .m4v, .avi, .mkv, .webm) | VIDEO FILE |
| All other extensions | DOCUMENT FILE |

The label is intentionally visible. It communicates to the operator that
the item exists in the queue but its visual preview is unavailable. This
is preferable to a silent placeholder because it signals that the item
requires attention or that the thumbnail pipeline has a problem.

### C.5 UX Invariants

| ID | Invariant |
|----|-----------|
| UX-1 | Card dimensions are fixed regardless of image state. A loading, loaded, or errored card occupies the same space. No layout shift occurs when image state transitions. |
| UX-2 | Thumbnail loading and error states do not block or delay wheel navigation. The user can always scroll, swipe, or use keyboard navigation regardless of any card's image state. |
| UX-3 | The skeleton loading animation is visible during the "loading" state. It is replaced by either the image (on success) or the fallback label (on error). There is no intermediate blank state. |
| UX-4 | Preloading does not trigger visible loading indicators. Preloaded images populate the browser cache silently; the visible skeleton only appears on the card's own img element. |

### C.6 Non-Goals

- Explicit "retry" button on error cards is not in scope.
- Progressive image loading (low-res then high-res) is not supported.
- Thumbnail generation on demand via the API is not supported (thumbnails
  are generated by the backend pipeline; the API only serves cached
  results).
- Offline or service-worker caching of thumbnails is not in scope.

---

## Design Token Dependencies

These decisions depend on the following existing design tokens. No new
tokens are introduced by these decisions.

| Token | Role in these decisions |
|-------|----------------------|
| `--wheel-blur-center` | Blur for Tier 0 (active card) |
| `--wheel-blur-near` | Blur for Tier 1 (adjacent cards) |
| `--wheel-blur-far` | Blur for Tier 2 (distant cards) |
| `--duration-slow` | Transition duration for card position changes |
| `--easing-default` | Easing curve for card transitions |
| `--surface-card` | Card background surface |
| `--border-default` | Card border |
| `--action-primary` | Active card highlight border |

New tokens may be required during implementation for Y-axis rotation
angles and overlap offsets. Those tokens should follow the naming
convention `--wheel-*` and be added to `tokens.css` alongside the
existing `--wheel-blur-*` tokens.

---

## Decision D — Stage-Based Slot Architecture

Date: 2026-04-08
Supersedes: The spatial-carousel track-and-spacer layout model in
PhotoWheel.svelte. Existing decisions A.1, A.3, A.4, B-series, and
C-series remain valid and are not modified by this decision.

### Background

The current implementation positions cards inside a flex track with
spacer elements representing off-screen items. The track is centered
in the viewport via `justify-content: center`. This model cannot
enforce the A.2 centering invariant at boundary indices because
spacer asymmetry causes the active card to drift away from the
viewport midpoint (see Decision A.2 — Centering Invariant (Revised)
for the detailed failure analysis).

An architectural review concluded that the centering failure is
structural, not presentational, and that patching the existing model
would produce a fragile, self-contradictory layout. This decision
authorizes the replacement of the track-and-spacer layout with a
stage-based slot model.

### D.1 Slot Layout

**Decision: fixed-position slot grid with structural center.**

The wheel renders a fixed number of visual slots:
`SLOT_COUNT = 2 * RENDER_RADIUS + 1` (currently 11).

Each slot has a spatially invariant position relative to the viewport.
Slot positions do not change when navigation occurs. The center slot
(index `RENDER_RADIUS`, currently slot 5) is anchored at the
horizontal midpoint of the wheel container.

Slot positions may be implemented via CSS grid, absolute positioning,
or any mechanism that produces fixed, symmetric positions. The
implementation mechanism is not prescribed; the invariant is that slot
positions are static.

### D.2 Content Binding

**Decision: navigation changes content, not position.**

When the user navigates, the items bound to each slot change. The
mapping is:

```
slotPosition ∈ [0, SLOT_COUNT - 1]
itemIndex = activeIndex - RENDER_RADIUS + slotPosition
```

If `itemIndex < 0` or `itemIndex >= itemCount`, the slot is empty
(not rendered). This handles boundary conditions without spacers.

The center slot always binds to `items[activeIndex]`.

### D.3 Center Slot Invariant

The center slot is the sole actionable slot. Only the item in the
center slot may be accepted, rejected, or deferred. This is enforced
by the slot position, not by runtime index comparison.

The A.2 centering invariant becomes a structural property:

- The center slot is at the viewport midpoint by CSS construction.
- The active item is always bound to the center slot.
- Therefore, the active card is always at the viewport center.

The interior/boundary behavioral regions defined in the revised A.2
section no longer apply. Centering is uniform across all indices.

### D.4 Visual Narrative — Content Animation

**Decision: the wheel feels dynamic through content motion, not slot
motion.**

Slot positions are static, but the visual impression of a moving wheel
is preserved through content animation when `activeIndex` changes:

- Items slide, crossfade, or parallax between slot positions during
  transitions.
- The animation direction corresponds to the navigation direction
  (content slides left when navigating right, and vice versa).
- The animation is governed by `--duration-slow` and
  `--easing-default`, consistent with existing transition tokens.
- When interaction stops, the wheel settles into a stable, centered
  stage with no residual motion.

The specific animation technique (CSS transitions on content position,
keyed Svelte transitions, or explicit requestAnimationFrame) is an
implementation choice, not a design decision. The invariant is that
navigation produces a perceptible motion effect and does not appear
as an instantaneous content swap.

### D.5 Tier Styling

The existing tier-based visual treatment (Decision B) is preserved.
The tier computation changes input but not output:

- **Current model:** `tier = f(Math.abs(itemIndex - activeIndex))`
- **Stage model:** `tier = f(Math.abs(slotPosition - RENDER_RADIUS))`

Since the center slot always holds the active item, these produce
identical visual results. The transform values (translateZ, rotateY,
scale), opacity, blur, and z-index from B.2 are unchanged.

### D.6 Relationship to Existing Decisions

| Decision | Impact |
|----------|--------|
| A.1 Viewport model | Unchanged. `overflow: hidden` still applies. |
| A.2 Centering | Restored to original intent. Center slot is at viewport midpoint by construction. The revised perceptual-centering workaround is superseded. |
| A.3 Navigation topology | Unchanged. Finite, clamped. `clampIndex()` is unmodified. |
| A.4 Non-goals | Unchanged. |
| B.1–B.5 Geometry and depth | Unchanged. Tier transforms apply identically to slot positions. |
| B.6 Visual invariants | VIS-1 through VIS-7 are preserved or strengthened. See VIS-1 restatement below. |
| B.7 Non-goals | Unchanged. |
| C.1–C.6 Thumbnails | Unchanged. Render-window entry still triggers loading; windowing still causes unmount/remount for retry. |

### D.7 Modules Affected

| Module | Change |
|--------|--------|
| `photowheel-input.ts` | None. Operates in index-space. |
| `photowheel-momentum.ts` | None. Operates in index-space. |
| `photowheel-windowing.ts` | `getRenderWindow()` unchanged. `getWindowSlotCounts()` becomes unnecessary and may be removed. `getPreloadIndexes()` unchanged. |
| `PhotoWheel.svelte` | Template refactored: spacer elements removed, slot-position iteration replaces item-slice iteration, `slotStyle()` takes slot position. CSS: track replaced with fixed-slot container. |
| `PhotoCard.svelte` | None. |

### D.8 Non-Goals

- This decision does not prescribe the CSS layout mechanism (grid vs.
  absolute vs. other). Any mechanism that produces fixed, symmetric
  slot positions is acceptable.
- This decision does not prescribe the content animation technique.
- This decision does not introduce variable slot counts or responsive
  slot reduction. Those may be addressed separately if needed.
- This decision does not change the render radius, preload radius, or
  windowing thresholds.

---

## Decision A.2 — Centering Invariant (Revised)

Date: 2026-04-08
Supersedes: Decision A §A.2 ("Centering Rules") — original invariant retained
for intent but replaced by this refined invariant for acceptance testing.

> **Note (2026-04-08):** This section documents the perceptual-centering
> workaround adopted under the spatial-carousel architecture. Decision D
> (Stage-Based Slot Architecture) restores the original A.2 intent: the
> active card is at the viewport center by structural construction. The
> interior/boundary behavioral regions, relaxed acceptance criteria, and
> explicit non-goals below no longer apply under the stage model. This
> section is retained for historical reference.

### Background: Why the Original Invariant Cannot Hold

The original A.2 centering rule states:

> "The midpoint of the active card aligns with the midpoint of the
> viewport container."

This invariant assumes that the active card can be positioned at the
viewport's geometric center independently of its index. In the current
architecture, centering is a consequence of the track's flex layout, not
a directly controlled property of the active card. Specifically:

1. The `.track` is a flex container with `justify-content: center`.
   This centers the **entire flex content** — left spacer, rendered
   cards, and right spacer — within the viewport, not the active card
   individually.

2. Spacer elements represent the aggregate width of cards outside the
   render window on each side. Their formula is:
   `flex-basis: calc(var(--slot-count) × (220px + var(--space-4)))`.

3. When `activeIndex` is far from both list boundaries (distance to
   each end ≥ RENDER_RADIUS), the left and right spacers are
   approximately equal. The active card sits at the geometric center
   of a symmetric content block, and `justify-content: center`
   places it near the viewport center. The original invariant holds
   within rounding tolerance.

4. When `activeIndex` is near a list boundary (distance to one end
   < RENDER_RADIUS), the spacer on the boundary side shrinks toward
   zero while the opposite spacer remains large. The flex content
   becomes asymmetric. The active card — still at the center of the
   rendered card cluster — shifts away from the viewport midpoint
   toward the boundary side. The shift magnitude is proportional to
   the spacer asymmetry.

Enforcing strict viewport-center alignment at boundary indices would
require either:
- Changing spacer semantics to compensate (scope violation), or
- Applying a per-frame corrective translation to the track or active
  card (introduces coupling between layout and windowing state that
  does not exist today).

Both options are excluded by the architectural preservation constraint.

### Revised Centering Invariant: Perceptual Centering Model

The active card is the **perceptual center** of the visible card
arrangement. Centering is defined relative to the rendered card cluster,
not relative to the viewport's geometric midpoint.

#### Definition

The **rendered card cluster** is the contiguous group of card elements
currently in the DOM, produced by the render window
(`items.slice(window.start, window.end + 1)`). The cluster does not
include spacer elements.

**Perceptual centering** means:

1. The active card is at the positional center of the rendered card
   cluster. It has an equal count of rendered cards on its left and
   right sides (within ±1 card when the render window is clamped at
   a list boundary).

2. The rendered card cluster (including its flanking spacers) is
   centered in the viewport by the track's `justify-content: center`
   rule. The track's flex layout is the sole mechanism for horizontal
   positioning.

3. Visual depth cues (scale, opacity, blur, z-index) decrease
   symmetrically outward from the active card, reinforcing it as the
   focal center regardless of its absolute viewport position.

#### Behavioral Regions

The centering behavior divides into two regions based on the active
card's distance from list boundaries:

**Interior region** (distance to both list ends ≥ RENDER_RADIUS):

- The spacers are symmetric or near-symmetric.
- The active card is approximately viewport-centered.
- Acceptance tolerance: the horizontal midpoint of the active card is
  within **half a card-width + gap** of the viewport's horizontal
  midpoint. (This accounts for the discrete nature of spacer slot
  counts and the flex gap contributing to minor per-pixel variation.)

**Boundary region** (distance to one list end < RENDER_RADIUS):

- The spacer on the boundary side is smaller than the opposite spacer.
- The active card shifts toward the boundary side of the viewport.
- The shift is bounded: the active card never leaves the central
  third of the viewport (i.e., its midpoint stays within the middle
  33% of the container width).
- The rendered card cluster remains centered by `justify-content:
  center`. The active card remains at the center of the cluster.

#### Transition Continuity

When `activeIndex` changes, the card arrangement recenters on the new
active card with an animated transition governed by `--duration-slow`
and `--easing-default`. The perceptual center tracks the active card
smoothly. There must be no discontinuous jump in the active card's
position between consecutive index changes, including transitions
that cross the interior/boundary threshold.

### Revised Acceptance Criteria

| ID | Criterion |
|----|-----------|
| CTR-1 | The active card has equal rendered card count on left and right (±1 at boundaries). |
| CTR-2 | In the interior region, the active card midpoint is within `(card-width / 2 + gap)` of the viewport midpoint. |
| CTR-3 | In the boundary region, the active card midpoint remains within the central third of the viewport central third of the viewport width, measured from container bounding box. |
| CTR-4 | Visual depth tiers (scale, blur, opacity, z-index) are symmetric about the active card. |
| CTR-5 | Animated transitions between index changes are continuous; no instantaneous position jumps. |
| CTR-6 | The track's `justify-content: center` is the sole horizontal positioning mechanism. No per-frame corrective offsets or programmatic scroll adjustments are applied. |

Viewport‑relative proximity metrics (CTR‑2) are observational only and not treated as pass/fail gates.

### Non-Goals (Explicit Relaxations)

These properties are **not guaranteed** by the revised invariant:

- **Exact pixel-center alignment of the active card with the viewport
  midpoint** at all indices. This is a consequence of the spacer model
  and is not corrected.
- **Identical active-card viewport position at all indices.** The active
  card's absolute position within the viewport varies by index,
  particularly in the boundary region.
- **Sub-pixel centering precision.** The discrete spacer slot counts and
  flex gap arithmetic produce minor rounding offsets. These are not
  treated as defects.
- **Centering independent of item count.** With very few items
  (itemCount < 2 × RENDER_RADIUS + 1), no spacers are generated and
  centering is determined entirely by flex layout of the actual cards.
  The perceptual center still holds but viewport-center proximity
  depends on item count.

### Relationship to Other Decisions

This revision does not modify:

- **Decision A.1** (viewport overflow model) — unchanged.
- **Decision A.3** (navigation topology) — unchanged.
- **Decision A.4** (non-goals for navigation) — unchanged.
- **Decisions B.1–B.7** (card geometry and depth model) — unchanged.
  Note: the overlap model in B.3 will change card positioning within
  the cluster. The perceptual centering invariant is defined in terms
  of card count symmetry and depth-cue symmetry, not absolute pixel
  positions, so it remains valid after B-series implementation.
- **Decisions C.1–C.6** (thumbnail loading) — unchanged.

### Rationale for Choosing Perceptual Centering

Three alternative models were evaluated:

**A) Visual-Center Tolerance Model** — defines centering as "within N
pixels of viewport center at all indices." Rejected because no single
tolerance value works for both interior and boundary regions without
being so large as to be meaningless. The boundary drift is structural,
not a rounding artifact.

**B) Perceptual Centering Model** — defines centering relative to the
rendered card cluster. **Selected.** This model is architecturally
honest: it describes what the layout actually achieves and matches user
perception. The active card is always the focal center of the visible
group. Users perceive centering relative to the card group, not
relative to the viewport edge. At boundary indices the asymmetry is
natural (fewer cards exist on one side) and does not read as a layout
defect.

**C) Anchor-Relative Centering** — defines centering relative to the
track's logical midpoint or a fixed anchor element. Rejected because
the track midpoint shifts with spacer sizes, making it no more stable
than viewport-center, and introducing an artificial reference point
with no visual correspondence.

---

## Decision E — Active Photo Visual Dominance

Date: 2026-04-09

### Background

The approved mockup shows the active photo as the dominant visual element,
occupying a substantial portion of the viewport width. The current
implementation uses a fixed 220px card width for all slots, including the
active card. This produces cards that are visually subordinate to the CTA
buttons and metadata panel rather than commanding the layout.

### E.1 Active Card Sizing

**Decision: the active card must be the largest single visual element on
the staging page.**

The active card occupies at minimum 35% of the viewport width at the
minimum supported viewport (1180 CSS px landscape). On wider viewports
the active card may scale proportionally but must never exceed 50% of the
viewport width.

The active card's thumbnail area has a 4:3 aspect ratio (matching the
existing `PhotoCard` `aspect-ratio: 4 / 3` rule).

Non-active card widths scale relative to the active card width through
the existing tier scale factors (Decision B.2): Tier 1 at 0.78×, Tier 2
at 0.60×. Slot spacing, overlap offsets, and slot-offset custom property
must be recalculated to accommodate the larger base width.

### E.2 Visual Hierarchy Invariant

The active card must be unambiguously the primary visual focus. This is
enforced by the combination of:

1. **Scale dominance**: the active card is larger than any other single
   UI element on the page (buttons, metadata, header, etc.).
2. **Depth prominence**: the active card is frontmost (z-index, translateZ,
   zero rotation, full opacity — existing B.2 Tier 0 rules apply).
3. **Spatial centrality**: the active card is at the viewport center
   (existing D.3 center-slot invariant applies).

### E.3 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| DOM-1 | Active card rendered width ≥ 35% of viewport width at 1180 CSS px. |
| DOM-2 | Active card rendered width ≤ 50% of viewport width at all viewports. |
| DOM-3 | Active card bounding box area > any single CTA button bounding box area. |
| DOM-4 | Active card thumbnail aspect ratio is 4:3 (±1px tolerance). |

### E.4 Non-Goals

- Pixel-exact match with the mockup's card size. The mockup is a target,
  not a specification.
- Dynamic card sizing based on item count or queue length.
- Different sizing for image vs. video vs. document items.

---

## Decision F — Primary Action Cluster

Date: 2026-04-09

### Background

The approved mockup shows two action presentation layers:

1. **Inline controls**: small Accept/Reject buttons positioned to the
   right of the active card within the wheel region.
2. **CTA controls**: large, prominently outlined Accept and Reject
   buttons below the wheel. Each CTA button has an outlined border
   (teal for Accept, red for Reject), a hand icon (✋), and large
   label text. The buttons span the full content width as a two-column
   grid.

The current implementation renders CTA buttons as small filled buttons
without icons, using the same `ActionButton` component as the inline
controls. This fails to communicate the drag-and-drop affordance and
reduces the visual weight of the primary action.

### F.1 CTA Button Design

**Decision: CTA buttons are large, outlined drop targets with icons.**

Each CTA button:

1. Has a colored outline border (Accept: `--action-accept`, Reject:
   `--action-reject`) with no fill (background is transparent or
   matches the page surface).
2. Displays a hand icon (✋ or equivalent SVG) to the left of the label.
   The icon communicates drag-and-drop affordance.
3. Has label text sized at `--text-xl` or larger.
4. Has minimum touch target height of 64px (WCAG 2.2 Level AAA target
   size).
5. Spans the available width in a two-column grid (Accept left,
   Reject right).

### F.2 CTA Glow Feedback

When a dragged photo hovers over a CTA button, the button displays an
active glow effect using the existing shadow tokens (`--shadow-accept-glow`
or `--shadow-reject-glow`). This provides clear visual feedback that the
drop target is valid.

### F.3 Inline Controls

The inline Accept/Reject buttons to the right of the wheel remain small,
filled buttons (existing design). They serve as a click shortcut for
users who prefer not to use keyboard or drag. They do not duplicate the
CTA visual treatment.

### F.4 Single-Item Semantics

**Decision: all triage actions operate on the single active item only.**

There is no multi-select, no bulk action, and no "select then act" flow.
The active card (center slot) is always the implicit target of any triage
action.

### F.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| ACT-1 | CTA Accept button has a visible teal border and no solid fill. |
| ACT-2 | CTA Reject button has a visible red border and no solid fill. |
| ACT-3 | Both CTA buttons display a hand icon. |
| ACT-4 | CTA button height ≥ 64px. |
| ACT-5 | CTA buttons are arranged in a two-column grid spanning the content width. |
| ACT-6 | Only the active card is affected by any triage action. |

### F.6 Non-Goals

- Animated button state transitions beyond hover/active/glow.
- Tertiary action buttons (defer is keyboard-only; D key).
- Swipe-to-accept or swipe-to-reject on the card itself.
- Undo/confirmation dialogs after triage (existing behavior is immediate).

---

## Decision G — Drag and Drop Semantics

Date: 2026-04-09

### Background

The approved mockup's large CTA buttons with hand icons imply a
drag-and-drop interaction: the operator drags the active photo onto the
Accept or Reject target to perform triage. No drag-and-drop
implementation exists in the current codebase.

### G.1 Drag Source

**Decision: only the active card (center slot) is draggable.**

The active card's DOM element has `draggable="true"`. Non-active cards
are not draggable. The drag data payload includes the item's `sha256`
identifier.

When dragging begins:

1. The drag preview shows a reduced-opacity thumbnail of the active card.
2. The wheel interaction model is suspended (no navigation during drag).
3. The inline controls are visually de-emphasized.

### G.2 Drop Targets

**Decision: the two CTA buttons are the only valid drop targets.**

The Accept CTA accepts drops and triggers the accept triage action.
The Reject CTA accepts drops and triggers the reject triage action.

No other element on the page accepts drops. Dropping outside a valid
target cancels the drag with no side effect.

### G.3 Visual Feedback During Drag

| State | Visual |
|-------|--------|
| Drag started | Active card reduces opacity to 0.5; CTA buttons pulse border. |
| Drag over Accept | Accept CTA: glow (`--shadow-accept-glow`), border thickens. |
| Drag over Reject | Reject CTA: glow (`--shadow-reject-glow`), border thickens. |
| Drop on target | Triage action fires; card exits with existing transition. |
| Drop outside | Drag cancelled; active card opacity restores to 1.0. |

### G.4 Keyboard and Click Parity

Drag-and-drop is an optional interaction path. All triage actions remain
fully accessible via:

- Keyboard: A (accept), R (reject), D (defer).
- Inline button clicks.
- CTA button clicks.

### G.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| DND-1 | Active card has `draggable="true"`. |
| DND-2 | Non-active cards do not have `draggable="true"`. |
| DND-3 | Dropping on Accept CTA triggers accept triage action. |
| DND-4 | Dropping on Reject CTA triggers reject triage action. |
| DND-5 | Dropping outside any target produces no side effect. |
| DND-6 | CTA buttons display glow feedback during dragover. |
| DND-7 | Wheel navigation is suspended while drag is active. |

### G.6 Non-Goals

- Touch-based drag (HTML5 drag events are pointer-only; touch triage
  uses buttons or keyboard).
- Drag between cards (reordering the queue).
- Drag to external targets.
- Custom drag ghost image (native browser preview is acceptable).

---

## Decision H — Scroll Containment

Date: 2026-04-09

### Background

The staging page must not produce a vertical scrollbar at the minimum
supported viewport. When the user interacts with the PhotoWheel via
mouse wheel, the scroll events must not chain to the page — the wheel
region must fully capture scroll input.

### H.1 No Vertical Page Scrollbar

**Decision: the staging page layout must fit within a single viewport
without producing a vertical scrollbar.**

The root layout establishes `min-height: 100vh` on `.app-shell`. The
staging page must constrain its content to fit within the `<main>`
area without overflow. The layout model is:

```
100vh = header + padding-top + content + padding-bottom + footer
```

All staging page elements (title, wheel, CTA buttons, metadata) must
fit within this budget. If the content would overflow, the details
panel must collapse or become scrollable internally rather than
extending the page.

### H.2 Scroll Chaining Prevention

**Decision: the PhotoWheel container prevents scroll chaining.**

The `.wheel` element must apply `overscroll-behavior: contain` to prevent
mouse-wheel events from propagating to the page when the wheel region
has pointer focus. This supplements the existing `hasPointerFocus` +
`shouldPreventWheelScroll()` JavaScript guard with a CSS-level
containment.

Additionally, `touch-action: pan-y` must not be set on the wheel
container. The wheel handles its own touch input; touch events must
not trigger page scroll.

### H.3 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| SCR-1 | No vertical scrollbar visible on the staging page at 1180 × 820 CSS px. |
| SCR-2 | Mouse-wheel events inside the wheel region do not scroll the page. |
| SCR-3 | The `.wheel` element has `overscroll-behavior: contain`. |
| SCR-4 | Touch interaction with the wheel does not trigger page scroll. |

### H.4 Non-Goals

- Horizontal scroll containment (already prevented by `overflow-x: hidden`).
- Responsive reflow for viewports smaller than the minimum supported.
- Custom scrollbar styling.

---

## Decision I — Operator-First Metadata

Date: 2026-04-09

### Background

The current `ItemMetaPanel` displays metadata in a flat definition list
with equal visual weight: Filename, SHA-256, Size, Account, OneDrive ID.
For an operator performing triage, the most decision-relevant fields
are the source account and capture timestamp — not the filename or hash.

The approved mockup shows metadata directly below the active card as
compact inline text: filename on one line, then SHA prefix + capture
time, then account.

### I.1 Metadata Hierarchy

**Decision: metadata is organized into primary (operator-relevant) and
secondary (technical) tiers.**

**Primary tier** (always visible, prominent):

| Field | Display |
|-------|---------|
| Account | Source account identifier (e.g., `user@account.com`) |
| Capture time | Formatted timestamp (e.g., `Captured at 14:15`) |
| Filename | Original filename |

**Secondary tier** (de-emphasized or disclosed on demand):

| Field | Display |
|-------|---------|
| SHA-256 | Truncated hash prefix (e.g., `E007GAE...`) |
| File size | Human-readable size (e.g., `4.2 MB`) |
| OneDrive ID | Internal reference (hidden by default) |

### I.2 Placement

**Decision: primary metadata is integrated into the active card's
visual region, not in a separate panel.**

Following the mockup, the primary metadata fields appear directly below
the active card's thumbnail within the card container. This eliminates
the separate `ItemMetaPanel` as a standalone section and instead makes
the metadata part of the card's visual identity.

Secondary metadata may remain in a collapsible or on-demand detail
region (see Decision J).

### I.3 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| META-1 | Account and capture time are visible without interaction. |
| META-2 | Account and capture time are rendered at `--text-base` or larger. |
| META-3 | SHA-256 is truncated to ≤ 16 characters when displayed. |
| META-4 | OneDrive ID is not visible by default. |
| META-5 | Primary metadata is visually attached to the active card, not in a separate panel. |

### I.4 Non-Goals

- Editable metadata fields.
- Metadata for non-active cards (only the active card shows metadata).
- Real-time metadata refresh (data is static per queue hydration).

---

## Decision J — Details Presentation Strategy

Date: 2026-04-09

### Background

The current implementation places an `ItemMetaPanel` below the CTA
buttons, contributing to vertical overflow. The mockup does not show a
separate details panel; all relevant information is on the card or
omitted.

### J.1 No Standalone Details Panel in Default View

**Decision: the staging page default view does not include a standalone
details panel.**

The `ItemMetaPanel` component is removed from the default staging page
layout. Primary metadata is shown on the active card (Decision I.2).
Secondary metadata is available via a disclosure mechanism.

### J.2 Disclosure Mechanism

**Decision: secondary metadata is available via a side-sheet or drawer
triggered by an explicit user action.**

The disclosure mechanism is a slide-in panel (right-side sheet) that
overlays the page content. It is triggered by a small "details" icon or
link on the active card. It does not push or reflow the main layout.

The sheet contains:

- Full SHA-256 hash (copyable).
- File size in human-readable format.
- OneDrive ID.
- Any future diagnostic fields.

The sheet closes via an explicit close button, Escape key, or clicking
outside the sheet.

### J.3 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| DET-1 | No standalone details panel visible in the default staging view. |
| DET-2 | A disclosure affordance (icon/link) is present on the active card. |
| DET-3 | The detail sheet does not cause the page to reflow or scroll. |
| DET-4 | The detail sheet is dismissible via close button, Escape, or click-outside. |

### J.4 Non-Goals

- Bottom-sheet (mobile pattern) — this is a desktop-first tool.
- Persistent sidebar (would reduce wheel viewport width).
- Modal dialog (too disruptive for optional information).

---

## Decision K — Minimum Viewport and Full-Viewport Layout

Date: 2026-04-09

### Background

The staging UI is a purpose-built operator tool used primarily on tablets
and desktop monitors. The minimum supported device is the iPad 10th
generation in landscape orientation (~1180 × 820 CSS px).

### K.1 Minimum Supported Viewport

**Decision: the staging page is designed for a minimum viewport of
1180 × 820 CSS px (iPad 10th gen, landscape).**

Below this viewport, the page may degrade gracefully but no layout
guarantees are made. The existing responsive breakpoint at 980px for
inline-control repositioning is below the minimum; it is retained for
incidental narrow-window use but is not a design target.

### K.2 Full-Viewport Layout Model

**Decision: the staging page uses a full-viewport, no-scroll layout.**

The staging page fills exactly 100vh. The vertical layout budget is:

| Region | Sizing |
|--------|--------|
| App header | `auto` (fixed height, existing) |
| Page title | `auto` (single line) |
| PhotoWheel + inline controls | `1fr` (fills remaining space) |
| CTA buttons | `auto` (fixed height, ≥ 64px per F.1) |
| App footer | `auto` (fixed height, existing) |

The page `<main>` padding must be accounted for in the layout budget.
The PhotoWheel region receives all remaining vertical space after fixed
elements are measured.

The wheel's `min-height: 360px` may be replaced with a flex-grow or
grid `1fr` approach to fill available space dynamically.

### K.3 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| VP-1 | At 1180 × 820 CSS px, the staging page has no vertical scrollbar. |
| VP-2 | The PhotoWheel region fills the vertical space between the title and CTA buttons. |
| VP-3 | Reducing browser height below 820px does not break the layout (content clips or compresses, no overflow). |

### K.4 Non-Goals

- Portrait orientation support (iPad portrait is ~820 × 1180 — the
  vertical layout would require a fundamentally different design).
- Mobile phone support (viewport width < 768px).
- Print stylesheet.

---

## Invariant Summary — Fidelity Pass

This table consolidates all new invariants introduced by Decisions E–K
for reference by implementation plans.

| ID | Decision | Invariant |
|----|----------|-----------|
| DOM-1 | E (Dominance) | Active card width ≥ 35% viewport at minimum VP. |
| DOM-2 | E (Dominance) | Active card width ≤ 50% viewport at all VPs. |
| DOM-3 | E (Dominance) | Active card area > any single CTA button area. |
| DOM-4 | E (Dominance) | Active thumbnail 4:3 aspect ratio. |
| ACT-1 | F (Actions) | Accept CTA: outlined teal border, no fill. |
| ACT-2 | F (Actions) | Reject CTA: outlined red border, no fill. |
| ACT-3 | F (Actions) | Both CTAs display hand icon. |
| ACT-4 | F (Actions) | CTA height ≥ 64px. |
| ACT-5 | F (Actions) | CTA two-column grid spanning content width. |
| ACT-6 | F (Actions) | Only active card affected by triage actions. |
| DND-1 | G (Drag & Drop) | Active card: `draggable="true"`. |
| DND-2 | G (Drag & Drop) | Non-active cards: not draggable. |
| DND-3 | G (Drag & Drop) | Drop on Accept CTA triggers accept. |
| DND-4 | G (Drag & Drop) | Drop on Reject CTA triggers reject. |
| DND-5 | G (Drag & Drop) | Drop outside: no side effect. |
| DND-6 | G (Drag & Drop) | CTA glow feedback during dragover. |
| DND-7 | G (Drag & Drop) | Wheel navigation suspended during drag. |
| SCR-1 | H (Scroll) | No vertical scrollbar at 1180 × 820. |
| SCR-2 | H (Scroll) | Wheel events do not scroll page. |
| SCR-3 | H (Scroll) | `.wheel` has `overscroll-behavior: contain`. |
| SCR-4 | H (Scroll) | Touch on wheel does not scroll page. |
| META-1 | I (Metadata) | Account + capture time visible without interaction. |
| META-2 | I (Metadata) | Primary metadata at `--text-base` or larger. |
| META-3 | I (Metadata) | SHA-256 truncated to ≤ 16 chars. |
| META-4 | I (Metadata) | OneDrive ID hidden by default. |
| META-5 | I (Metadata) | Primary metadata attached to active card. |
| DET-1 | J (Details) | No standalone details panel in default view. |
| DET-2 | J (Details) | Disclosure affordance on active card. |
| DET-3 | J (Details) | Detail sheet does not reflow page. |
| DET-4 | J (Details) | Detail sheet dismissible. |
| VP-1 | K (Viewport) | No vertical scrollbar at minimum VP. |
| VP-2 | K (Viewport) | Wheel fills vertical space between title and CTA. |
| VP-3 | K (Viewport) | Below-minimum VP clips, does not overflow. |

---

## Revision History

| Date | Change |
|------|--------|
| 2026-04-08 | Initial authoritative decisions (A, B, C) |
| 2026-04-08 | Added Decision A.2 — Centering Invariant (Revised): replaced strict viewport-center alignment with perceptual centering model |
| 2026-04-08 | Added Decision D — Stage-Based Slot Architecture: authorized migration from spatial-carousel to fixed-slot model. Restored original A.2 centering intent. Reframed VIS-1 as structural invariant. Marked revised A.2 as historical. |
| 2026-04-09 | Added Decisions E–K — Fidelity Pass invariants: active photo dominance, primary action cluster, drag & drop, scroll containment, operator-first metadata, details presentation, minimum viewport and full-viewport layout. |
