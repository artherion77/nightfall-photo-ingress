# Web Control Plane — Phase 1 Implementation Roadmap

Status: In progress — Chunks 0-3 implemented
Date: 2026-04-03
Owner: Systems Engineering

Authoritative sources consumed to produce this document:
- `planning/planned/web-control-plane-phase1-scope.md` (Phase 1 Re-Evaluation, **authoritative scope**)
- `planning/planned/web-control-plane-project-structure.md` (**authoritative structure**)
- `planning/planned/web-control-plane-techstack-decision.md` (**authoritative tech stack**)
- `planning/planned/web-control-plane-integration-plan.md` (detailed endpoint and data-flow spec)
- `design/web/webui-architecture-phase1.md` (layout, stores, API layer, component hierarchy)
- `design/web/webui-component-mapping-phase1.md` (mockup analysis, component map)
- `design/web/webui-design-tokens-phase1.md` (dark-mode token catalogue)

---

## 1. Phase 1 Goal Summary

Phase 1 delivers a minimal, localhost-only, single-operator web control plane for
`nightfall-photo-ingress`. It is implemented as a single additional Python process
(FastAPI + Uvicorn on `127.0.0.1:8000`) that serves both a REST API and the pre-built
SvelteKit SPA from the same origin.

Phase 1 ends with a fully functional, security-hardened operator control plane
exposable to `localhost` only. LAN exposure, TLS, and reverse proxy introduction are
Phase 2 mandatory items.

### Phase 1 functional scope at a glance

| Capability | Notes |
|---|---|
| Read-only API (health, staging, audit, config, blocklist) | All endpoints live |
| Static bearer token auth | `[web] api_token` in `photo-ingress.conf` |
| SvelteKit SPA — all 5 pages rendered with live data | Dashboard, Staging, Audit, Blocklist, Settings |
| Triage write path (accept / reject / defer) | With idempotency keys and audit-first writes |
| Blocklist CRUD | Add / edit / toggle / delete via UI |
| Security hardening | Rate limiting, CORS, security headers, auth-failure audit |
| RapiDoc API docs at `/api/docs` | Served offline from static asset |

---

## 2. Dependency Graph — Implementation Chunks

```
Chunk 0: Foundation
   │
   ├──► Chunk 1: Read-Only API (Python)
   │       │
   │       └──► Chunk 4: Triage Write Path (Python)
   │               │
   │               └──► Chunk 5: Blocklist Write Path (Python)
   │                       │
   │                       └──► Chunk 6: Security Hardening (Python + wiring)
   │
   └──► Chunk 2: Design Token System + Base UI Infrastructure (SvelteKit)
           │
           └──► Chunk 3: Read-Only UI Pages (SvelteKit — wires to Chunk 1)
                   │
                   ├──► Chunk 4 (adds interactive write path to Chunk 3 Staging page)
                   └──► Chunk 5 (adds write controls to Chunk 3 Blocklist page)
```

**Notes:**
- Chunks 1 and 2 can be developed in parallel after Chunk 0.
- Chunk 3 cannot start until both Chunk 1 (API live) and Chunk 2 (base components exist).
- Chunks 4 and 5 each have a backend half and a UI half; the backend half can be
  written before Chunk 3 is complete but the UI half depends on Chunk 3.
- Chunk 6 is the final gate before Phase 1 is declared complete.

---

## 3. Chunk 0 — Project Foundation

Status: Implemented (2026-04-03)

### Purpose

Establish the repository skeleton (`api/` and `webui/` trees), add required
dependencies to `pyproject.toml`, scaffold the SvelteKit project, and confirm the two
processes start without errors. No functional endpoints or UI pages are required.

### Required inputs

- `planning/planned/web-control-plane-project-structure.md` §2, §5, §6, §7
- `planning/planned/web-control-plane-techstack-decision.md` §2, §3
- `planning/planned/web-control-plane-integration-plan.md` §3

### Expected output

**Repository structure:**
```
api/
  __init__.py
  app.py                — FastAPI application factory (no routes yet), lifespan stub
webui/
  package.json
  svelte.config.js      — adapter-static, ssr = false
  vite.config.js        — /api proxy to localhost:8000
  src/
    app.html
    routes/
      +layout.svelte    — bare scaffold (no header/footer yet)
      +layout.js        — export const ssr = false
      +page.svelte      — placeholder "Dashboard coming soon"
      staging/+page.svelte
      audit/+page.svelte
      blocklist/+page.svelte
      settings/+page.svelte
      +error.svelte
```

**Other:**
- `pyproject.toml`: `fastapi` and `uvicorn[standard]` added under `[project.optional-dependencies]` group `web` (not in default deps — keeps CLI install minimal).
- `systemd/nightfall-photo-ingress-api.service` — unit template, binds to `127.0.0.1:8000`, `EnvironmentFile=` config path.
- `.gitignore` additions: `webui/node_modules/`, `webui/.svelte-kit/`, `webui/build/`, `api/__pycache__/`.

### Acceptance criteria

1. `pip install -e '.[web]'` succeeds from repo root.
2. `uvicorn api.app:app --port 8000` starts without errors; `GET http://localhost:8000/` returns 404 (no routes registered yet).
3. `cd webui && npm install && npm run dev` starts the Vite dev server on port 5173 without errors.
4. `cd webui && npm run build` produces `webui/build/index.html`.
5. All existing Python tests pass (`pytest`).
6. No domain or registry module imports `api/` (dependency direction enforced).

### Out of scope for this chunk

- Any actual API endpoint or UI functionality.
- Auth, rate limiting, or security configuration.
- Any database migration.

---

### ⛔ STOP — Chunk 0 complete. Return control to user for review before continuing.

---

## 4. Chunk 1 — Read-Only API

### Purpose

Implement all Phase 1 read-only API endpoints, the bearer-token auth dependency,
Pydantic response schemas, the service layer, and two required database migrations.
RapiDoc is wired up at `/api/docs`. The API must return correct, paginated live data
from the SQLite registry.

### Required inputs

- `planning/planned/web-control-plane-integration-plan.md` §4 (endpoints, auth, migrations)
- `design/web/webui-architecture-phase1.md` §7 (API layer structure)
- `src/nightfall_photo_ingress/config.py` (config loading — extend for `[web]` section)
- Existing registry / domain modules (as import targets; not modified)
- `src/nightfall_photo_ingress/status.py` (health snapshot reader)

### Expected output

**Files created / modified:**

```
api/
  app.py             — Application factory with StaticFiles mount stub, lifespan (registry connect/disconnect)
  auth.py            — Bearer token dependency: reads [web] api_token from AppConfig; raises HTTP 401 on mismatch
  routers/
    health.py        — GET /api/v1/health
    staging.py       — GET /api/v1/staging, GET /api/v1/items/{item_id}
    audit_log.py     — GET /api/v1/audit-log
    config.py        — GET /api/v1/config/effective
    blocklist.py     — GET /api/v1/blocklist (read path only)
  services/
    health_service.py    — Reads /run/nightfall-status.d/photo-ingress.json
    staging_service.py   — Paginated registry queries for pending items
    audit_service.py     — Paginated audit_log table queries with action filter
    config_service.py    — Reads AppConfig; redacts api_token and all secret fields
    blocklist_service.py — Queries blocked_rules table (read path)
  schemas/
    health.py    — HealthResponse, ServiceStatus
    staging.py   — StagingItem, StagingPage
    audit.py     — AuditEvent, AuditPage
    config.py    — EffectiveConfig
    blocklist.py — BlockRule, BlockRuleList
  rapiddoc.py    — Static HTML mount returning the RapiDoc UI page
src/nightfall_photo_ingress/
  config.py      — Extend: add [web] section (api_token, bind_host, bind_port)
src/nightfall_photo_ingress/migrations/
  XXXX_add_blocked_rules.py         — CREATE TABLE blocked_rules (...)
  XXXX_add_ui_idempotency.py        — CREATE TABLE ui_action_idempotency (...)
webui/static/rapiddoc/
  rapidoc-min.js  — RapiDoc self-contained JS bundle (single file, no CDN dependency)
tests/
  test_api_health.py       — health endpoint schema, auth rejection
  test_api_staging.py      — pagination, item detail, cursor correctness
  test_api_audit_log.py    — event listing, action filter
  test_api_config.py       — effective config, token redaction
  test_api_blocklist.py    — list rules (read path)
  test_api_auth.py         — missing/invalid token → 401; /api/docs exempt
```

### Endpoint contract summary

| Method | Path | Auth required | Description |
|--------|------|---------------|-------------|
| GET | `/api/v1/health` | Yes | Poll status, auth status, registry status, disk usage |
| GET | `/api/v1/staging` | Yes | Paginated pending items (cursor: `after`, limit: default 20) |
| GET | `/api/v1/items/{item_id}` | Yes | Single item detail |
| GET | `/api/v1/audit-log` | Yes | Paginated audit events (`action=` filter, cursor-based) |
| GET | `/api/v1/config/effective` | Yes | Effective config dump (api_token redacted) |
| GET | `/api/v1/blocklist` | Yes | List all block rules |
| GET | `/api/docs` | No | RapiDoc UI |
| GET | `/api/openapi.json` | No | FastAPI-generated OpenAPI schema |

### Acceptance criteria

1. All six data endpoints return HTTP 200 with well-formed JSON matching their Pydantic response schemas.
2. `GET /api/v1/staging` returns cursor-paginated results; supplying `after=` cursor returns the next page.
3. `GET /api/v1/audit-log?action=accepted` returns only `accepted` events.
4. `GET /api/v1/config/effective` returns config with `api_token` value replaced by `[redacted]`.
5. Any endpoint with a missing or invalid `Authorization: Bearer` header returns HTTP 401.
6. `GET /api/docs` returns an HTML page containing the RapiDoc component; no auth required.
7. `GET /api/openapi.json` lists all six data endpoints.
8. The `blocked_rules` and `ui_action_idempotency` schema additions are applied idempotently for valid schema-v2 registries.
9. The current runtime does not bump `PRAGMA user_version` for these additions; they are created as optional additive tables during registry initialization.
10. API read-path results must match CLI/domain queries for identical filters (snapshot comparison).
11. All `tests/test_api_*.py` tests pass using `httpx.AsyncClient` with `ASGITransport` when executed explicitly or included in the active pytest collection.
12. All existing CLI tests still pass.

### Out of scope for this chunk

- Any write (POST / PATCH / DELETE) endpoint.
- Rate limiting or CORS headers (Chunk 6).
- Frontend wiring (Chunk 3).
- Static file serving of the SPA build (stubbed in `app.py`, completed in Chunk 3).

---

### ⛔ STOP — Chunk 1 complete. Return control to user for review before continuing.

---

## 5. Chunk 2 — Design Token System + Base UI Infrastructure

**Status: COMPLETED (2026-04-03)**

**Implementation Note:** The design token system and global reset stylesheet are
**fully implemented** and ready for use. All tokens are defined in `webui/src/styles/tokens.css`,
global reset in `webui/src/styles/reset.css`, and both are imported globally in the
root layout. Components use tokens exclusively with zero raw colour or pixel values in
component styles. See `design/web/webui-design-tokens-phase1.md` for the complete
token catalogue and compliance checklist.

### Purpose

Build the complete dark-mode design token system and all shared/common SvelteKit
components that page-specific components and layouts depend on. No page routes are
wired to real API data in this chunk. This chunk can proceed in parallel with Chunk 1.

### Required inputs

- `design/web/webui-design-tokens-phase1.md` (full token catalogue — authoritative)
- `design/web/webui-architecture-phase1.md` §1.5 (global styling, tokens, reset)
- `design/web/webui-component-mapping-phase1.md` §4 (component mapping)
- `planning/planned/web-control-plane-phase1-scope.md` §3.3 (C3: health store lifecycle), §3.11 (C11: KPI thresholds from API), §3.12 (C12: blur tokens)

### Delivered output

```
webui/src/styles/
  tokens.css            — All CSS custom properties (colours, spacing, typography, radius, shadows, animations)
  reset.css             — Global normalization and base element styling

webui/src/app.html
  (updated)             — Added color-scheme: dark meta tag

webui/src/routes/
  +layout.svelte        — Root layout importing reset.css and tokens.css globally
  (no other routes yet) — Placeholder pages ready for Chunk 3

webui/src/lib/components/
  common/
    StatusBadge.svelte      — Coloured dot + label; uses status tokens
    KpiCard.svelte          — Metric box; accepts thresholds as prop (C11)
    ActionButton.svelte     — Button; uses action-* tokens
    ConfirmDialog.svelte    — Modal overlay; uses surface and shadow tokens
    ErrorBanner.svelte      — Inline error; uses status-error token
    LoadingSkeleton.svelte  — Animated placeholder; uses surface tokens
    EmptyState.svelte       — Zero-items state; uses text tokens
    LoadMoreButton.svelte   — Cursor pagination button (C10)

  layout/
    AppHeader.svelte    — Top band: logo, nav tabs; subscribes to health store
    AppFooter.svelte    — Bottom band: version, last poll time; subscribes to health store
    PageTitle.svelte    — Consistent heading with tokens

webui/src/lib/stores/
  health.svelte.js    — State: {polling_ok, auth_ok, registry_ok, disk_ok, last_updated, error}
                        API: connect(), disconnect() with 30s polling interval
                        No polling logic in layout or component files (C3)
```

### Completed acceptance criteria

1. ✅ `npm run build` produces a build with no TypeScript errors and no Svelte compile warnings.
2. ✅ Root layout renders with global design tokens available to all components.
3. ✅ `tokens.css` defines all colour, spacing, typography, radius, shadow, and animation tokens.
4. ✅ Photo Wheel blur tokens (`--wheel-blur-*`) reserved for Phase 2; not implemented in Phase 1 (C12).
5. ✅ `KpiCard` accepts `thresholds` as a prop; no threshold values hardcoded (C11).
6. ✅ `health.svelte.js` exposes `connect()` and `disconnect()`; called from root layout (C3).
7. ✅ `LoadMoreButton` exists as standalone component (C10).
8. ✅ All common components render correctly in isolation and use token references only.
9. ✅ No raw colour hex, pixel, or named CSS values in any component `<style>` block.
10. ✅ Global `reset.css` normalizes form elements and applies token-based base styling.
11. ✅ Design tokens documented in `design/web/webui-design-tokens-phase1.md` (Implemented status).
12. ✅ Architecture updated in `design/web/webui-architecture-phase1.md` §1.5 (Global Styling section).

### Out of scope for this chunk (completed in later chunks)

- Any API call or live data wiring (Chunk 3).
- Page-specific components (dashboard, staging, audit, blocklist — Chunk 3).
- Interactive triage or blocklist write controls (Chunks 4, 5).

---

## 6. Chunk 3 — Read-Only UI Pages

Status: Implemented (2026-04-03)

### Purpose

This chunk may be internally executed as 3a (API clients + stores + Dashboard +
Settings) and 3b (Staging display + Audit + Blocklist) if needed.

Wire all five SvelteKit pages to the live API (Chunk 1 required). Implement all
page-specific components. Produce a deployable static build served by the FastAPI
application. After this chunk, an operator can log in, view the dashboard, browse
the staging queue (display only), read the audit timeline, view blocklist rules, and
read the settings/config page.

### Delivered summary

- Added read-only API client layer in `webui/src/lib/api/` (`client.ts`, `health.ts`,
  `staging.ts`, `audit.ts`, `config.ts`, `blocklist.ts`).
- Added read-only stores: `kpis.svelte.js`, `stagingQueue.svelte.js`,
  `auditLog.svelte.js`, `blocklist.svelte.js`, `config.svelte.js`.
- Replaced placeholder route pages with live read-only pages and loaders for
  Dashboard, Staging, Audit, Blocklist, and Settings.
- Mounted SPA static output in FastAPI and implemented route fallback behavior:
  serve `200.html`, then `index.html` when static route files are missing.
- Added integration coverage in `tests/integration/ui/` and validated with
  `tests/integration/api` as a combined regression suite.

### Required inputs

- Chunk 1 (API live and returning correct data)
- Chunk 2 (base components and stores available)
- `design/web/webui-architecture-phase1.md` §4–§7 (page structure, stores, API layer)
- `design/web/webui-component-mapping-phase1.md` §4–§7
- `planning/planned/web-control-plane-integration-plan.md` §5 (phase 2 data-flow)
- `planning/planned/web-control-plane-phase1-scope.md` §3.10 (C10: LoadMoreButton), §3.11 (C11: KPI thresholds from API config endpoint)

### Expected output

```
webui/src/lib/api/
  client.ts      — Base fetch wrapper: Authorization header, ApiError on non-2xx, network failure → ApiError(status=0)
  health.ts      — getHealth(): GET /api/v1/health
  staging.ts     — getStagingPage(cursor?, limit?), getItem(id)
  audit.ts       — getAuditLog(cursor?, limit?, action?)
  config.ts      — getEffectiveConfig()
  blocklist.ts   — getBlocklist()

webui/src/lib/stores/
  kpis.svelte.js            — State: {pending_count, accepted_today, rejected_today, live_photo_pairs, last_poll_duration_s, loading, error}; loaded from GET /api/v1/staging (counts) + health
  stagingQueue.svelte.js    — State: {items[], cursor, total, loading, error}; actions: loadPage(cursor), clearQueue
  auditLog.svelte.js        — State: {events[], cursor, hasMore, filter, loading, error}; actions: loadMore(), setFilter(action)
  blocklist.svelte.js       — State: {rules[], loading, error}; loadRules() action
  config.svelte.js          — State: {kpi_thresholds, ...effectiveConfig, loading, error}; thresholds fetched from GET /api/v1/config/effective (C11)

webui/src/lib/components/
  dashboard/
    KpiGrid.svelte          — Grid of KpiCard; thresholds sourced from config store (C11)
    PollRuntimeChart.svelte — Sparkline chart of recent poll durations; data from audit log or health
    HealthBar.svelte        — Horizontal status bar with four subsystem dots
    AuditPreview.svelte     — Last 5 audit events; includes AuditEvent rows; onViewAll → navigate /audit

  staging/
    PhotoWheel.svelte       — Carousel with center + neighbour cards; display-only in this chunk (no triage actions)
                              Blur levels use --wheel-blur-near / --wheel-blur-far tokens (C12)
                              Neighbor cards at ±1: blurred/scaled; ±2: more blurred/scaled
    PhotoCard.svelte        — Single card: thumbnail placeholder, filename, SHA-256 (truncated), timestamp, account
    ItemMetaPanel.svelte    — Detail panel for center card

  audit/
    AuditTimeline.svelte    — Scrollable event list + LoadMoreButton (C10); filter pill row
    AuditEvent.svelte       — Single event row: icon, filename, action badge, relative time

  blocklist/
    BlockRuleList.svelte    — List of rules with enabled badge; read-only in this chunk (no edit/delete yet)

  settings/
    ConfigTable.svelte      — Read-only key/value table of effective config; redacted fields shown as [redacted]

webui/src/routes/
  +page.svelte              — Dashboard: KpiGrid, HealthBar, PollRuntimeChart, AuditPreview
  +page.js                  — load(): GET /api/v1/staging?limit=20 + GET /api/v1/audit-log?limit=5 + GET /api/v1/config/effective + GET /api/v1/health
  staging/+page.svelte      — PhotoWheel display; ItemMetaPanel for center item
  staging/+page.js          — load(): GET /api/v1/staging?limit=20
  audit/+page.svelte        — AuditTimeline + filter pills
  audit/+page.js            — load(): GET /api/v1/audit-log?limit=50
  blocklist/+page.svelte    — BlockRuleList (read-only)
  blocklist/+page.js        — load(): GET /api/v1/blocklist
  settings/+page.svelte     — ConfigTable
  settings/+page.js         — load(): GET /api/v1/config/effective

api/app.py                  — StaticFiles mount: webui/build/ at '/'
                              SPA fallback: use 200.html; fallback to index.html when 200.html is absent

tests/
  integration/ui/           — Pytest integration tests (API + static serving contract):
    test_dashboard.py       — Dashboard data endpoints and static root serving behavior
    test_staging_display.py — Staging endpoint behavior and read-only mutation rejection (404/405)
    test_audit.py           — Audit first page, action filter, and cursor follow-up page
    test_settings.py        — Config redaction and blocklist shape checks
    test_error_states.py    — Error-path behavior including auth rejection and SPA route fallback
```

### Acceptance criteria

1. Navigating to `http://localhost:8000/` serves the Dashboard with live KPI values from the API.
2. AppHeader health badge reflects current health state and updates every 30 seconds.
3. AppFooter last-poll timestamp comes from the health store; updates live.
4. Dashboard KPI thresholds are sourced from `GET /api/v1/config/effective`; no threshold value exists in the compiled SPA (C11).
5. Staging page shows the PhotoWheel with items from the pending queue; no Accept/Reject buttons are present.
6. Audit page loads the first page of events and shows `LoadMoreButton`; clicking it appends the next page (C10).
7. Audit filter pills (by action type) reset the list and reload from page 1.
8. Settings page shows the effective config with `api_token` displayed as `[redacted]`.
9. Blocklist page shows the list of rules (no edit controls yet).
10. `npm run build` produces a clean build; FastAPI serves it at `/`; SPA client-side routing works (direct routes serve `200.html` or `index.html` fallback).
11. `ErrorBanner` renders when the API returns a non-2xx response; `LoadingSkeleton` renders while data is loading.
12. Dark-mode design tokens are applied consistently; no raw colour or pixel values appear in component styles.
13. Integration tests pass for `tests/integration/ui/` and related API checks.

### Out of scope for this chunk

- Any write action (accept, reject, defer, blocklist CRUD).
- PhotoWheel keyboard navigation and drag-and-drop (Chunk 4).
- Blocklist edit/add/delete controls (Chunk 5).
- API summary counts (accepted_today, rejected_today, live_photo_pairs) — Phase 2 P2-I.
- 7-day poll runtime history endpoint and line chart — Phase 2 P2-J.
- Filename field in audit events — Phase 2 P2-K.
- Item thumbnail endpoint and real image display in PhotoCard — Phase 2 P2-L.

### Known Gaps — Staging Deploy Review (2026-04-03)

The following deviations from the UI mockups were found during Chunk 3 staging
validation. All are within the defined Chunk 3 scope and should be corrected before
Chunk 4 work begins. Full analysis in `audit/open-points/chunk3-ui-drift-analysis.md`.

**Two blocking bugs (fixed in the same session — see §2 of audit doc):**
- `import.meta.env.PUBLIC_API_TOKEN` compiled to `"undefined"` in the Vite bundle;
  replaced with `$env/static/public` import in `client.ts` and `health.svelte.js`.
- `+error.svelte` used the SvelteKit v1 prop API (`export let error`); updated to
  SvelteKit v2 `$page.error` via `$app/stores`.

**Dashboard visual / text corrections needed:**
- D-V1: `<h1>` text should be "Photo-Ingress Dashboard", not "Dashboard".
- D-V2: `HealthBar` should appear above `KpiGrid`, not below.
- D-V3: `HealthBar` labels should use full names: "OneDrive Auth", "Registry Integrity",
  "Disk Usage" (not "Auth", "Registry", "Disk").
- D-V4: `KpiCard` should have a colour-coded bottom border driven by threshold state.
- D-V5: `AuditPreview` heading should be "Audit Timeline" in accent colour.
- D-V6: Audit event rows should show a colour-coded action badge (`StatusBadge`).
- D-V7: Audit event timestamps should display as relative time ("25 mins ago").
- D-V8: Audit event identifier should show filename where available (blocked on P2-K);
  fall back to "SHA-256: {prefix}" format in the interim.

**Staging visual corrections needed:**
- S-V1: `PhotoWheel` should use CSS 3D perspective coverflow, not a flat flex row.
  Cards should visually recede (scale + translateZ) by distance from active index.
- S-V2: Blur/scale algorithm must use `Math.abs(index - activeIndex)` (distance from
  active card), not the current `index % 2` even/odd logic.
- S-V3: `--wheel-blur-near` and `--wheel-blur-far` tokens must be defined in
  `tokens.css`; the `PhotoWheel` must reference them (not hardcoded values).
- S-V4: `PhotoCard` SHA field should be prefixed "SHA-256: {hash}".
- S-V5: `PhotoCard` timestamp should format `first_seen_at` as "Captured at HH:MM".

---

### ⛔ STOP — Chunk 3 complete. Return control to user for review before continuing.

---

## 7. Chunk 4 — Triage Write Path

### Purpose

Add the three triage mutation endpoints to the API and wire the Staging Queue page to
perform accept, reject, and defer actions with idempotency keys, optimistic UI updates,
and audit-first writes.

### Required inputs

- Chunk 3 (Staging page and PhotoWheel read-only display complete; no triage controls yet)
- Chunk 1 (auth, service layer patterns established)
- `planning/planned/web-control-plane-integration-plan.md` §6 (triage design)
- `design/web/webui-architecture-phase1.md` §6.3 (optimistic UI), §7.2 (base client extension for idempotency header)
- Existing read-only UI plumbing from Chunk 3:
  - `webui/src/lib/api/client.ts` + read endpoint modules
  - `webui/src/lib/stores/stagingQueue.svelte.js` (currently read-only load/append)
  - `webui/src/routes/staging/+page.svelte` and `PhotoWheel.svelte` display path
- `design/web/webui-component-mapping-phase1.md` §4.2 and §7 (TriageControls and interaction model)
- Existing domain transition functions (`accept`, `reject`) in `src/nightfall_photo_ingress/domain/`

### Expected output

**Backend:**
```
api/
  audit_hook.py        — Context manager: writes audit event before state mutation; on exception writes compensating event
  routers/
    triage.py          — POST /api/v1/triage/{item_id}/accept|reject|defer
                         Requires X-Idempotency-Key header; returns idempotency replay on duplicate key
  services/
    triage_service.py  — Wraps domain accept/reject/defer functions; enforces audit-first via audit_hook
  schemas/
    triage.py          — TriageRequest (body), TriageResponse (action_correlation_id, item_id, state)

tests/
  test_api_triage.py   — accept/reject/defer happy paths; idempotency key replay; missing key → 422; invalid item_id → 404
```

**Frontend:**
```
webui/src/lib/api/
  triage.ts           — postAccept(itemId, idempotencyKey), postReject(itemId, idempotencyKey), postDefer(itemId, idempotencyKey)

webui/src/lib/stores/
  stagingQueue.svelte.js  — Extended: triageItem(action, itemId) — optimistic remove, on error restore + push toast

webui/src/lib/components/staging/
  PhotoWheel.svelte    — Completed: keyboard nav (ArrowLeft/ArrowRight to shift wheel; A/R/D shortcuts for Accept/Reject/Defer)
  TriageControls.svelte — Two layers of triage controls matching the UI mock:
                          1. Inline small Accept / Reject buttons overlaid on the active (centre) card
                          2. Two large full-width CTA buttons below the wheel (teal Accept, red Reject)
                             as shown in design/ui-mocks/Astronaut photo review interface.png
                          Both layers use ActionButton with action-* tokens; Defer available via keyboard only (D key)
                          Generates UUID v4 idempotency key per action
                          On action: call store.triageItem() → optimistic remove → API call → success advances wheel / error restores

tests/integration/ui/
  test_triage.py      — Accept removes item from wheel; Reject removes item; Defer re-queues; duplicate idempotency key returns same result
  test_triage_error_recovery.py — API 500 on accept restores item to wheel; toast shown
```

### Acceptance criteria

1. `POST /api/v1/triage/{item_id}/accept` transitions item from `pending` to `accepted` in the registry; item removed from staging queue.
2. `POST /api/v1/triage/{item_id}/reject` transitions item to `rejected`; item removed from staging queue.
3. `POST /api/v1/triage/{item_id}/defer` returns item to `pending` without file-system change.
4. Submitting the same `X-Idempotency-Key` a second time returns the cached prior response; state is not changed again.
5. Missing `X-Idempotency-Key` header returns HTTP 422.
6. Audit log shows triage events with actor (`api`), item ID, and timestamp.
7. Optimistic update removes the item from the PhotoWheel immediately on action.
8. On API error (500), the item is restored to the wheel and a toast notification appears.
9. Keyboard shortcuts `A`, `R`, `D` fire the corresponding triage action on the center item.
10. `ArrowLeft` / `ArrowRight` shift the wheel without triggering a triage action.
11. CLI triage and API triage produce identical registry state when applied to the same item (parity test).
12. All `test_api_triage.py` and `test_triage*.py` Playwright tests pass.

### Out of scope for this chunk

- Blocklist write operations (Chunk 5).
- Rate limiting on triage endpoints (Chunk 6).
- Drag-and-drop is implemented, but graceful degradation for touch/mouse is acceptable at Phase 1 quality.

---

### ⛔ STOP — Chunk 4 complete. Return control to user for review before continuing.

---

## 8. Chunk 5 — Blocklist Management Write Path

### Purpose

Add blocklist mutation endpoints (create, update, delete) to the API and wire the
Blocklist page to provide a complete CRUD operator interface.

### Required inputs

- Chunk 3 (Blocklist page with read-only `BlockRuleList` ready)
- Chunk 1 (`blocked_rules` migration and read path established)
- `planning/planned/web-control-plane-integration-plan.md` §7
- `design/web/webui-architecture-phase1.md` §7.2 (idempotency key in base client)

### Expected output

**Backend:**
```
api/routers/
  blocklist.py     — Extended: POST /api/v1/blocklist, PATCH /api/v1/blocklist/{rule_id}, DELETE /api/v1/blocklist/{rule_id}
                     All require X-Idempotency-Key; DELETE uses hard delete for Phase 1
api/services/
  blocklist_service.py — Extended: create_rule, update_rule, delete_rule; writes to blocked_rules table
api/schemas/
  blocklist.py     — Extended: BlockRuleCreate (body), BlockRuleUpdate (body), BlockRuleDeleteResponse

tests/
  test_api_blocklist.py — Extended: create rule, update pattern/enabled, delete rule, idempotency replay
```

**Frontend:**
```
webui/src/lib/api/
  blocklist.ts     — Extended: createRule(body, idempotencyKey), updateRule(id, body, idempotencyKey), deleteRule(id, idempotencyKey)

webui/src/lib/stores/
  blocklist.svelte.js  — Extended: createRule(), updateRule(), deleteRule() actions with optimistic updates and error rollback

webui/src/lib/components/blocklist/
  BlockRuleList.svelte — Extended: toggle enabled/disabled button, edit button, delete button per row
  BlockRuleForm.svelte — Add / edit form; fields: pattern (string), type (enum), reason (string optional)
                         Mounted inline (expand) or as a drawer; wired to POST / PATCH path

webui/src/routes/blocklist/
  +page.svelte     — Extended: BlockRuleList with controls + BlockRuleForm (add new rule) + ConfirmDialog for delete

tests/integration/ui/
  test_blocklist_crud.py  — Add rule → appears in list; toggle enabled → badge updates; delete with confirm → removed from list; cancel delete → not removed
```

### Acceptance criteria

1. A rule created via UI (`BlockRuleForm`) is persisted to the `blocked_rules` table.
2. CLI ingest honours newly created blocklist rules (blocked SHA-256 skipped on next poll).
3. Toggling a rule's `enabled` flag updates the database; disabled rules are not enforced by ingest.
4. Deleting a rule removes it from the database (hard delete).
5. The `ConfirmDialog` appears before delete is executed; cancelling does not delete.
6. `X-Idempotency-Key` replay on POST returns the previously created rule without duplicate insertion.
7. Blocklist rules created via the UI must behave identically to manually created rules in DB/Config (ingest behavior parity).
8. All `test_api_blocklist.py` and `test_blocklist_crud.py` tests pass.

### Out of scope for this chunk

- Blocklist rule import/export.
- Rate limiting on blocklist endpoints (Chunk 6).

---

### ⛔ STOP — Chunk 5 complete. Return control to user for review before continuing.

---

## 9. Chunk 6 — Security Hardening

### Purpose

Apply all security hardening required before Phase 1 can be considered production-ready
for localhost-only operator use. No new user-visible functionality is added.

### Required inputs

- Chunks 0–5 complete (all endpoints and UI functional)
- `planning/planned/web-control-plane-integration-plan.md` §9 (hardening checklist)
- `planning/planned/web-control-plane-phase1-scope.md` §4.1 (in-scope items: rate limiting, CORS, headers, auth-failure audit, input validation)
- Targeted OWASP checklist limited to Phase-1-relevant concerns

### Expected output

```
api/
  rate_limit.py        — Sliding window token bucket; per-route per-IP; in-process (no Redis)
                         POST routes: 30 req/min; GET routes: 120 req/min
                         Returns HTTP 429 with Retry-After header on limit exceeded

api/app.py             — Extended:
                           CORS middleware: allowlist = [configured UI origin, default http://localhost:8000]
                           Security headers middleware:
                             X-Content-Type-Options: nosniff
                             X-Frame-Options: DENY
                             Referrer-Policy: strict-origin-when-cross-origin

api/auth.py            — Extended: every 401/403 event writes structured audit record
                         (IP, path, method, timestamp) to audit_log table before returning error

api/routers/*.py       — All rate_limit dependency injected on POST/PATCH/DELETE routes

tests/
  test_api_rate_limit.py  — Exceeding limit returns 429; Retry-After header present; limit resets after window
  test_api_cors.py        — Origin in allowlist gets CORS headers; origin outside allowlist does not
  test_api_security_headers.py — All required headers present on every response
  test_api_auth_audit.py  — 401 on invalid token writes audit record; 403 writes audit record
```

**Validation audit:**
- Review all path parameters, query parameters, and request bodies across all routers.
- Confirm all string inputs pass through Pydantic models before reaching service layer.
- Confirm no raw user input is passed to file system operations or SQL queries outside of parameterised ORM/query methods.
- Document findings in `audit/open-points/` if any gap is found (do not block hardening if issue is minor and fixable immediately).

**Targeted OWASP review (Phase-1-relevant concerns only):**

| OWASP Category | Phase 1 mitigation |
|---|---|
| A01 Broken Access Control | Bearer token on all /api/v1/ routes; auth-failure audit |
| A02 Cryptographic Failures | No secrets in SPA build; token read server-side only |
| A03 Injection | Pydantic validation at all boundaries; parameterised queries |
| A04 Insecure Design | Audit-first writes; idempotency keys on all mutations |
| A05 Security Misconfiguration | CORS allowlist; security headers; localhost binding only |
| A06 Vulnerable Components | `pip-audit` run against `[web]` dependencies |
| A07 Auth Failures | 401/403 event audit; no token in logs |
| A08 Software Integrity | Rate limiting; no unsigned redirects |
| A09 Logging/Monitoring | Structured auth-failure audit in audit_log |
| A10 SSRF | API makes no outbound requests initiated by user input |

### Acceptance criteria

1. `POST` endpoints return HTTP 429 after 30 requests within a 60-second window from the same IP.
2. `GET` endpoints return HTTP 429 after 120 requests within a 60-second window.
3. Every HTTP 401 and 403 response triggers an audit log write with client IP, path, and method.
4. All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: strict-origin-when-cross-origin`.
5. A CORS `Origin` header from an unlisted origin receives no `Access-Control-Allow-Origin` response header.
6. `pip-audit` reports no critical vulnerabilities in the `[web]` dependency group.
7. All `test_api_rate_limit.py`, `test_api_cors.py`, `test_api_security_headers.py`, and `test_api_auth_audit.py` tests pass.
8. Targeted OWASP review completed for Phase-1-relevant concerns; any new open points are logged in `audit/open-points/`.
9. All prior test suites (Chunks 0–5) continue to pass.

### Out of scope for this chunk

- LAN exposure or TLS (Phase 2 mandatory — reverse proxy required first).
- Redis-backed rate limiting (Phase 2 optional upgrade).
- Retry/backoff in the API client (Phase 2 mandatory).
- OIDC/OAuth authentication (Phase 2 optional).

---

### ⛔ STOP — Chunk 6 complete. Phase 1 implementation is DONE. Return control to user for final review.

---

## 10. Phase 1 Explicitly Out-of-Scope Items

The following are deferred to Phase 2 or later. Do not implement them during Phase 1.

| Item | Phase 2 classification | Source |
|---|---|---|
| LAN exposure | Mandatory | Re-Evaluation C2 |
| Reverse proxy (Nginx/Caddy) | Mandatory | Re-Evaluation C2 |
| TLS termination | Mandatory | Re-Evaluation C2 |
| Brotli compression | Mandatory | Re-Evaluation C2 |
| Proxy-level rate limiting (replaces in-process) | Mandatory | Re-Evaluation C2 |
| Build artifact versioning and rollback | Mandatory | Re-Evaluation C5 |
| API versioning policy document | Mandatory | Re-Evaluation C4 |
| Retry / backoff in API client read calls | Mandatory | Re-Evaluation C7 |
| Filter Sidebar on Dashboard | Mandatory | Re-Evaluation C9 |
| Audit Timeline infinite scroll | Mandatory | Re-Evaluation C10 |
| KPI threshold settings UI (`PATCH /api/v1/config/thresholds`) | Mandatory | Re-Evaluation C11 |
| SSR capability | Optional | Re-Evaluation C1 |
| SQLite → Postgres migration | Optional | Re-Evaluation C6 |
| Background worker (sidecar/thumbnail) | Optional | Integration plan §8 |
| Task queue (Redis or alternative) | Optional | Tech stack decision §6 |
| OIDC/OAuth authentication | Optional | Tech stack decision §6 |
| CDN or asset caching | Optional | — |
| Phase 5: Sidecar and metadata endpoint | Optional | Integration plan §8 |

---

## 11. Phase 1 Deliverables Summary

At the end of Chunk 6, the following artefacts must exist and be passing tests:

### Source code
- `api/` — complete FastAPI application: routers, services, schemas, auth, rate limiting, audit hook, CORS, security headers
- `webui/src/` — complete SvelteKit SPA: 5 pages, all components, stores, API layer, design token system
- `webui/static/rapiddoc/rapidoc-min.js` — RapiDoc offline asset

### Configuration
- `src/nightfall_photo_ingress/config.py` — extended with `[web]` section (api_token, bind_host, bind_port)
- `conf/photo-ingress.conf.example` — updated with `[web]` section example and inline documentation

### Database
- Two migrations applied: `blocked_rules`, `ui_action_idempotency`

### Systemd
- `systemd/nightfall-photo-ingress-api.service` — deployable unit

### Tests
- `tests/test_api_health.py`
- `tests/test_api_staging.py`
- `tests/test_api_audit_log.py`
- `tests/test_api_config.py`
- `tests/test_api_blocklist.py`
- `tests/test_api_triage.py`
- `tests/test_api_auth.py`
- `tests/test_api_rate_limit.py`
- `tests/test_api_cors.py`
- `tests/test_api_security_headers.py`
- `tests/test_api_auth_audit.py`
- `tests/integration/ui/test_dashboard.py`
- `tests/integration/ui/test_staging_display.py`
- `tests/integration/ui/test_triage.py`
- `tests/integration/ui/test_triage_error_recovery.py`
- `tests/integration/ui/test_audit.py`
- `tests/integration/ui/test_blocklist_crud.py`
- `tests/integration/ui/test_settings.py`
- `tests/integration/ui/test_error_states.py`

### Documentation
- This roadmap document (updated with chunk completion status as work progresses)
- Targeted OWASP review findings documented in `audit/open-points/` if any gaps remained unresolved
