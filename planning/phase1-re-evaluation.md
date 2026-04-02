# Phase 1 Re-Evaluation

Status: Decided
Date: 2026-04-03 (rev 2: 2026-04-03)
Owner: Systems Engineering
Supersedes: Relevant sections of integration-plan.md (Phase 7), webui-architecture.md (§2, §3.2, §6),
            design-tokens.md (§11), ui-mapping.md (§3.1, §4.1, §6.1, §7.1, §7.3)

---

## 1. Purpose

This document re-evaluates the Phase 1 design in light of an external architectural
review. For each critique point, a disposition is assigned and justified. The document
closes with the final, amended Phase 1 scope.

Any design changes decided here are the authoritative record. Referenced source
documents are amended separately where noted.

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

**Original decision:** webui-architecture.md §2 states SSR is disabled and gives four
reasons for the choice. The original framing implies a permanent rejection.

**Critique:** The critique correctly observes that permanently rejecting SSR forecloses
a useful future capability (faster perceived load, better error boundaries, potential
server-side auth guard simplification). It should be deferred, not excluded.

**Amendment:** The Phase 1 design is unchanged — `@sveltejs/adapter-static` and
`ssr = false` remain correct for Phase 1. The language in webui-architecture.md §2 is
updated to state "deferred" rather than "disabled/rejected". The conditions under which
SSR becomes worth revisiting are:
- Operator count grows beyond a single LAN user (requires real auth session management).
- A Node.js server process becomes acceptable in the LXC deployment topology.
- Page load time on low-bandwidth LAN connections becomes a reported pain point.

Until one of these conditions is met, the adapter-static SPA approach is optimal.
The SSR upgrade path is documented in phase2-architecture.md.

**Documents affected:** webui-architecture.md §2.

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
phase2-architecture.md.

**Phase 1 unchanged:** Phase 1 binds Uvicorn to localhost. LAN exposure is not
unlocked until Phase 2 with the reverse proxy in place.

---

### C3 — Health Polling: Moved from Layout to Store Module

**Original decision:** webui-architecture.md §3.2 and §6.2 placed `setInterval` polling
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

**Documents affected:** webui-architecture.md §3.2, §6.1, §6.2.

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
phase2-architecture.md §3 as a mandatory Phase 2 deliverable, to be written before any
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
making rollback atomic (symlink swap). This is documented in phase2-architecture.md §4.

**Phase 1 unchanged:** `rsync` overwrite of `webui/build/` is acceptable for
localhost-only Phase 1 deployment.

---

### C6 — SQLite Concurrency: Phase 1 Acceptable; Migration Path Phase 2 Optional

**Original decision:** integration-plan.md §12 already documents WAL mode for
concurrent reads. Phase 1 stays SQLite.

**Critique:** Correctly identifies that SQLite is an acceptable Phase 1 database for
low-concurrency operator use, but a migration path should be anticipated.

**Decision:** Phase 1 unchanged. The migration path from SQLite to Postgres is
documented in phase2-architecture.md §6 as a Phase 2 optional feature. It will not
be actioned unless one of these triggers is met:
- Concurrent write contention causes measurable latency (> 100ms on triage actions).
- The operator count grows to require multi-user concurrent sessions.
- Background worker jobs produce sustained write traffic alongside API writes.

---

### C7 — Retry/Backoff: Phase 2

**Original decision:** webui-architecture.md §7 documents the API client error handling
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
phase2-architecture.md §5.

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

**Original design:** ui-mapping.md §4.1 listed `FilterSidebar` as a Phase 1 Dashboard
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
column). The `FilterSidebar` component is not built. The layout diagram in ui-mapping.md
§3.1 is annotated with a deferral note.

**Phase 2 scope:** Filter Sidebar introduction is documented in phase2-architecture.md
§13.

**Documents affected:** ui-mapping.md §3.1 (annotation), §4.1 (deferral note), §6.1
(note).

---

### C10 — Infinite Scroll: Phase 1 Uses LoadMoreButton Pagination

**Original design:** ui-mapping.md §7.3 specified automatic infinite scroll for the
Audit Timeline: "On scroll near the bottom of the list, the next page is loaded
automatically (infinite scroll with a load threshold of 80% of container height)."

**Critique:** Infinite scroll adds complexity that is not justified for Phase 1. The
Audit Timeline will contain tens to low hundreds of events in normal Phase 1 use.

**Decision: Modified Phase 1.** Phase 1 uses cursor-based pagination via an explicit
`LoadMoreButton` component (already listed as `Load-more / pagination → LoadMoreButton`
in ui-mapping.md §4.3). The automatic IntersectionObserver scroll trigger is removed
from Phase 1. Operators click "Load more" to fetch the next cursor page.

**Phase 1 behaviour:**
- Audit Timeline loads first page (default 20 items) on mount.
- `LoadMoreButton` appears below the list if more pages are available.
- Clicking it appends the next cursor page to the existing list.
- Changing the action-type filter resets cursor and reloads from page one.

**Phase 2 scope:** Replacing `LoadMoreButton` with IntersectionObserver-based automatic
scroll loading is documented in phase2-architecture.md §14.

**Documents affected:** ui-mapping.md §7.3 (scrolling description).

---

### C11 — KPI Thresholds: From API Config, Not Hard-Coded

**Original design:** design-tokens.md §11 defined a hard-coded threshold table per KPI
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
- design-tokens.md §11: Hard-coded threshold table removed. Replaced with a design
  note explaining that thresholds are runtime configuration values from the config API.
- KpiCard props: `thresholds: { warning: number, error: number }` (passed in).
- The config endpoint's `kpi_thresholds` field is specified in the API integration
  document; the threshold values come from `photo-ingress.conf` on the server
  (operator configures by editing the config file in Phase 1).

**Phase 2 scope:** A settings UI allowing in-place threshold editing via
`PATCH /api/v1/config/thresholds` is documented in phase2-architecture.md §15.

**Documents affected:** design-tokens.md §11 (remove threshold table; add config-API
note); web-api-ui-integration-plan.md config endpoint response shape (noted change,
no new file required).

---

### C12 — Photo-Wheel Blur Tokenization

**Original design:** ui-mapping.md §7.1 specified raw pixel values in the visual
transform rules table: `4px` for ±1 offset cards, `8px` for ±2 offset cards.

**Critique:** design-tokens.md §1 explicitly states that "no raw values appear in
component styles". Using raw `4px` and `8px` in the interaction spec contradicts the
token-first principle already established for the project.

**Decision: Modified Phase 1.** This is a quality correction, not a feature change.
Three tokens are added to design-tokens.md in a new §13:

- `--wheel-blur-center` = `0px` (center card, fully sharp)
- `--wheel-blur-near` = `4px` (cards at ±1 offset)
- `--wheel-blur-far` = `8px` (cards at ±2 offset)

The visual transform rules table in ui-mapping.md §7.1 references these tokens.
No visual change to the user.

**Documents affected:** design-tokens.md (new §13: Photo Wheel Visual Transform Tokens);
ui-mapping.md §7.1 (Blur column).

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
| In-process rate limiting (FastAPI dependency) | Simple token bucket; no Redis required |
| Structured audit for auth failures | 401/403 events written to audit_log |
| Input validation on all route parameters | Via Pydantic models at API routers |
| CORS allowlist to configured UI origin | Default: `http://localhost:8000` |
| Security headers (X-Content-Type-Options etc.) | Via FastAPI middleware |
| Photo-Wheel blur levels tokenized | `--wheel-blur-near` / `--wheel-blur-far` tokens in design-tokens.md (C12) |
| KPI thresholds from `GET /api/v1/config` | `kpi_thresholds` object; no hardcoded values in SPA (C11) |
| Audit Timeline: `LoadMoreButton` cursor pagination | Explicit click to load next page; no infinite scroll (C10) |

### 4.2 Explicitly Deferred to Phase 2

| Item | Phase 2 Classification |
|------|----------------------|
| LAN exposure | Mandatory (requires reverse proxy first) |
| Reverse proxy (Nginx/Caddy) | Mandatory |
| TLS termination | Mandatory (via reverse proxy) |
| Brotli compression | Mandatory (via reverse proxy) |
| Proxy-level rate limiting | Mandatory (replaces in-process in Phase 2) |
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
| `design/webui-architecture.md` | §2, §3.2, §6.1, §6.2 | SSR framing (C1); health polling ownership (C3) |
| `planning/integration-plan.md` | Phase table, Phase 7 | Phase 7 reclassified via this document; no direct edit required |
| `design/design-tokens.md` | §11, new §13 | KPI threshold table removed, config-API note added (C11); Photo-Wheel blur tokens added (C12) |
| `design/ui-mapping.md` | §3.1, §4.1, §6.1, §7.1, §7.3 | Filter Sidebar deferred to Phase 2 (C9); blur tokenization (C12); LoadMoreButton pagination (C10) |
