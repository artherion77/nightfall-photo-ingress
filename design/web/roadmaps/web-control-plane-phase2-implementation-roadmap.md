# Web Control Plane — Phase 2 Implementation Roadmap

Status: In Progress — Chunk P2-1 (API Client Retry/Backoff) complete; P2-2 not started
Date: 2026-04-06
Owner: Systems Engineering
Depends on: Phase 1 complete (all Chunks 0-6 implemented and validated);
Phase 1.5 complete for P2-2 through P2-7 (P2-1 already implemented)

Authoritative Phase 2 design:
- `design/web/web-control-plane-architecture-phase2.md`

Phase 1 completion record:
- `design/web/roadmaps/web-control-plane-phase1-implementation-roadmap.md`

Phase 1.5 completion gate:
- `design/web/roadmaps/web-control-plane-phase1.5-implementation-roadmap.md`

---

## 1. Phase 2 Goal Summary

Phase 2 completes the mandatory prerequisites for LAN exposure and adds the three
operator-facing features deferred from Phase 1 (Filter Sidebar, Audit Timeline Infinite
Scroll, KPI Threshold Configuration). Phase 2 concludes with the LAN exposure gate:
Caddy reverse proxy, TLS, and proxy-level rate limiting.

Phase 2 has two tiers (see `design/web/web-control-plane-architecture-phase2.md §2`):
- **Phase 2 Mandatory:** Required before LAN exposure is permitted.
- **Phase 2 Optional:** Deferred; may be adopted independently based on operational need.

This roadmap covers only the Mandatory items, delivered as implementation chunks.
Optional items are listed in §10 for reference.

### Phase 2 Mandatory items at a glance

| Item | Chunk | Notes |
|------|-------|-------|
| API client retry/backoff for read-only calls | P2-1 | Frontend only |
| Filter Sidebar on Dashboard | P2-2 | Frontend + query param extension |
| Audit Timeline Pagination → Infinite Scroll | P2-3 | Frontend only |
| KPI Threshold Configuration via API | P2-4 | Backend + frontend |
| API Versioning Policy + v1 schema snapshot | P2-5 | Documentation + annotations |
| Build artifact versioning and rollback scripts | P2-6 | Deployment tooling |
| Caddy reverse proxy + TLS + rate limiting (LAN gate) | P2-7 | Infrastructure |

---

## 2. Chunk Dependency Graph

```
Phase 1 (all chunks complete)
    │
    ├──► P2-1: API Client Retry/Backoff   (independent; already complete)
    │
    └──► Phase 1.5 (quality gate complete)
            │
            ├──► P2-2: Filter Sidebar             (depends on Phase 1 staging endpoint
            │                                        and Phase 1.5 PhotoWheel/thumbnail gate)
            │
            ├──► P2-3: Audit Timeline ∞ Scroll    (depends on Phase 1 audit endpoint
            │                                        and Phase 1.5 completion gate)
            │
            ├──► P2-4: KPI Threshold Config       (depends on Phase 1 config endpoint
            │                                        and Phase 1.5 completion gate)
            │
            ├──► P2-5: API Versioning Policy      (documentation; blocked on Phase 1.5 gate)
            │
            ├──► P2-6: Build Artifact Versioning  (deployment tooling; blocked on Phase 1.5 gate)
            │
            └──► P2-7: Caddy LAN Gate             (depends on P2-5 and P2-6 being complete;
                                                     all mandatory code chunks should be done first)
```

**Execution order:** P2-1 is already complete. P2-2 through P2-6 remain independent
after the Phase 1.5 gate, and may be implemented in any order. P2-7 (LAN gate)
should not be activated until all other mandatory chunks are complete and stable.

**Recommended sequence:** P2-1 → Phase 1.5 gate → P2-2 → P2-3 → P2-4 → P2-5 → P2-6 → P2-7.

---

## 3. Chunk P2-1 — API Client Retry/Backoff

Status: Implemented (2026-04-06)

### Purpose

Add automatic retry with exponential backoff for all read-only (GET) API calls made
by the SPA. Mutations remain fail-fast; idempotency-key replay is the operator's retry
mechanism for mutations. Health polling surfaces a visible error indicator only after
three consecutive poll failures (after retries).

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §6 (retry policy specification)
- Phase 1 `apiFetch` in `webui/src/lib/api/client.ts`
- Phase 1 `health.svelte.js` direct-fetch polling loop

### Expected output

**`webui/src/lib/api/client.ts`** — Extended:
- `RETRY_DELAYS_MS = [500, 1000, 2000]` — three retry delays (ms)
- `jittered(ms)` — applies ±10% jitter
- `apiFetch` wraps GET requests in a retry loop:
  - Status 503 or network failure (status 0): retry up to 3 times with exponential backoff
  - Status 429: retry after `Retry-After` header value (falling back to backoff schedule)
  - All other 4xx/5xx: throw immediately, no retry
  - Mutations (POST/PATCH/DELETE): fail-fast, no retry

**`webui/src/lib/stores/health.svelte.js`** — Extended:
- Remove direct `fetch` call; use `getHealth()` from `$lib/api/health` instead
- Track `consecutiveFailures` counter
- Silently swallow poll errors below the `FAILURE_THRESHOLD` (3)
- Set store error state only when `consecutiveFailures >= FAILURE_THRESHOLD`
- Reset counter on successful poll

### Acceptance criteria

1. A GET request that receives a 503 response is retried up to 3 times before failing.
2. A GET request that encounters a network failure (status 0) is retried up to 3 times.
3. A GET request that receives a 429 response waits for `Retry-After` seconds before retry.
4. A POST/PATCH/DELETE request that fails is never retried automatically.
5. Retry delays are approximately 500ms, 1000ms, 2000ms with ±10% jitter.
6. Health poll errors are silently swallowed for the first two consecutive failures;
   only the third consecutive failure surfaces an error in the store.
7. A successful health poll resets the consecutive failure counter.
8. All existing integration tests continue to pass.

### Test strategy

The retry logic is implemented entirely in the TypeScript client layer. No pytest
integration test can exercise client-side retry behavior without a browser-level driver
(Playwright). Retry correctness is verified by code review; regression safety is
verified by running the existing integration suite.

If a Playwright harness is added in a future chunk, the following scenarios should be
automated:
- Mock a slow 503 then 200 response; verify the SPA eventually renders the data.
- Mock 3× 503; verify error banner appears.
- Mock 2× network failure then 200; verify no visible error indicator.

---

### Chunk P2-1 complete (2026-04-06) — 61 integration tests pass; no regressions.

---

## 4. Chunk P2-2 — Filter Sidebar

Status: Not Started

### Purpose

Add a file-type filter sidebar to the Dashboard page. The sidebar lets the operator
scope dashboard counts and the recent audit preview to a specific file type (Images,
Videos, Documents) or all files (default). Filter state is ephemeral (session only).

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §13
- Phase 1 `GET /api/v1/staging` — extend with optional `type` query parameter
- Phase 1 `GET /api/v1/config/effective` — `allowed_types` field used for dynamic options
- Phase 1 Dashboard page and KPI components

### Expected output

**Backend:**
```
api/routers/staging.py     — Extended: optional ?type= query parameter on GET /api/v1/staging
                             Valid values from config.allowed_types; unknown values → 422
api/schemas/staging.py     — Extended: StagingPage gains optional type filter in query model
```

**Frontend:**
```
webui/src/lib/api/staging.ts
  getStagingPage(cursor?, limit?, type?)  — pass ?type= when provided

webui/src/lib/components/dashboard/FilterSidebar.svelte
  props: options[] (string[]), selected: string, onChange: (type: string) => void
  Renders checkbox group; 'all' is default

webui/src/routes/(app)/dashboard/+page.svelte
  Extended: filterType $state; FilterSidebar wired; all API calls pass ?type= when filter active
  Layout: sidebar column + main content grid (see architecture §13.5)
```

### Acceptance criteria

1. `GET /api/v1/staging?type=image` returns only items whose MIME type is an image type.
2. `GET /api/v1/staging?type=unknown_value` returns HTTP 422.
3. Selecting "Images" in the sidebar filters the staging queue count on the Dashboard.
4. Selecting "All Files" restores unfiltered state; no `type=` parameter is sent.
5. Filter options are driven by `allowed_types` from the config response (dynamic).
6. Filter state is not persisted across page refresh (ephemeral, session only).
7. All existing integration tests continue to pass.

---

## 5. Chunk P2-3 — Audit Timeline Infinite Scroll

Status: Not Started

### Purpose

Replace the explicit `LoadMoreButton` in `AuditTimeline` with an `IntersectionObserver`-
based automatic scroll trigger. When the operator scrolls to within 200px of the
bottom of the list, the next cursor page is fetched and appended automatically.
The `LoadMoreButton` component is retained in `common/` and continues to work for
other explicit-pagination flows.

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §14
- Phase 1 `AuditTimeline.svelte` using `LoadMoreButton`
- Phase 1 `GET /api/v1/audit-log?after=...&limit=...` (unchanged by this chunk)

### Expected output

**Frontend:**
```
webui/src/lib/components/audit/AuditTimeline.svelte
  Replace <LoadMoreButton> with a sentinel <div bind:this={sentinel}>
  IntersectionObserver watches sentinel with rootMargin '200px'
  Observer fires: fetch next page, append, move sentinel to end
  Loading skeleton row shown while next page loads
  When no more pages: remove/hide sentinel (IntersectionObserver disconnected)
  Filter changes: reset cursor + clear appended list → fresh first-page load

webui/src/lib/components/common/LoadMoreButton.svelte  — retained, no change
```

### Acceptance criteria

1. Scrolling to within 200px of the bottom of the audit list triggers a next-page
   fetch without any button click.
2. A loading skeleton row is visible while the next page is loading.
3. When the last page is reached, no further fetches are triggered.
4. Changing a filter resets the list and loads the first page fresh.
5. `LoadMoreButton` component exists and is unmodified.
6. All existing integration tests continue to pass.

---

## 6. Chunk P2-4 — KPI Threshold Configuration

Status: Not Started

### Purpose

Add an operator-editable KPI threshold form to the Settings page. The form calls a
new `PATCH /api/v1/config/thresholds` endpoint to store per-metric warning/error
thresholds in a `config_overrides` SQLite table. Overrides take precedence over
config-file values at runtime. Existing `GET /api/v1/config/effective` response is
unchanged in shape.

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §15
- Phase 1 `GET /api/v1/config/effective` (returns `kpi_thresholds`, read-only)
- Phase 1 Settings page (`/settings`)

### Expected output

**Backend:**
```
api/routers/config.py
  PATCH /api/v1/config/thresholds — validates metric keys and warning < error
  DELETE /api/v1/config/thresholds — resets to config-file baseline

api/services/config_service.py — Extended: apply_thresholds(overrides), reset_thresholds()

api/schemas/config.py — Extended: ThresholdUpdate (metric_key → {warning, error})

src/nightfall_photo_ingress/migrations/
  New optional table: config_overrides (metric_key, warning, error, updated_at)

GET /api/v1/config/effective — Extended: merges config_overrides into kpi_thresholds before
  returning (config-file values are baseline; overrides take precedence per metric)
```

**Frontend:**
```
webui/src/lib/api/config.ts
  patchThresholds(overrides, idempotencyKey)
  deleteThresholds(idempotencyKey)        — reset to defaults

webui/src/routes/(app)/settings/+page.svelte
  Extended: KPI Thresholds form section
    One row per metric: label + warning input + error input + unit
    Inline validation: warning < error
    Save calls patchThresholds; success toast
    Reset to Defaults calls deleteThresholds; success toast

tests/integration/api/test_config.py — Extended: PATCH thresholds happy path;
    GET effective reflects override; DELETE reverts to baseline;
    warning >= error returns 422; unknown key returns 422
```

### Acceptance criteria

1. `PATCH /api/v1/config/thresholds` persists threshold overrides to `config_overrides` table.
2. `GET /api/v1/config/effective` returns merged kpi_thresholds (config-file baseline + overrides).
3. `DELETE /api/v1/config/thresholds` removes overrides; GET effective reverts to config-file baseline.
4. `warning >= error` for any metric returns HTTP 422.
5. An unknown metric key returns HTTP 422.
6. Settings page form renders one row per metric from config effective response.
7. Saving the form surfaces a success toast; validation errors are shown inline.
8. All new `test_config.py` tests pass; all existing integration tests continue to pass.

---

## 7. Chunk P2-5 — API Versioning Policy

Status: Not Started

### Purpose

Document the API versioning policy (already defined in the architecture doc) in a
snapshot artifact and add a lightweight annotation to the OpenAPI application to make
the policy discoverable from the running API. No breaking changes occur in Phase 2;
this chunk is preparatory.

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §5

### Expected output

```
docs/api/v1-schema-snapshot.md   — v1 endpoint inventory; shape summary; breaking-change
                                    classification table; deprecation timeline policy

api/app.py                        — OpenAPI `description` field updated to reference
                                    versioning policy and deprecation timeline
```

### Acceptance criteria

1. `docs/api/v1-schema-snapshot.md` exists and documents all current `/api/v1/` endpoints
   with their response shapes, required headers, and breaking-change status.
2. The API description at `/api/v1/openapi.json` references the versioning policy.
3. No endpoint paths or schemas are changed by this chunk.

---

## 8. Chunk P2-6 — Build Artifact Versioning

Status: Not Started

### Purpose

Establish the versioned build artifact release directory layout and the deploy/rollback
scripts required before Caddy can serve static assets from a versioned path. After this
chunk, the operator can deploy a new SvelteKit build by running a single script and
roll back to the previous build with a symlink swap.

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §4 (release directory layout,
  deployment procedure, rollback)
- `install/` directory conventions used by Phase 1

### Expected output

```
install/webui-deploy.sh       — Package build/, upload to releases/{RELEASE}/, update current symlink
install/webui-rollback.sh     — Re-point current symlink to a previous release directory
install/README-deploy.md      — Operator runbook for deploy and rollback procedures

conf/deploy.env.example       — DEPLOY_HOST, DEPLOY_PATH, RELEASE_KEEP_COUNT variables
```

No changes to `api/` or `webui/src/`.

### Acceptance criteria

1. `install/webui-deploy.sh` creates a timestamped release directory, extracts the
   build artifact, and updates the `current` symlink atomically.
2. `install/webui-rollback.sh` re-points the symlink to a specified prior release.
3. Both scripts are idempotent: re-running does not corrupt an existing deployment.
4. The deploy runbook documents the expected directory layout on the LXC host.

---

## 9. Chunk P2-7 — Caddy Reverse Proxy + TLS + Rate Limiting (LAN Gate)

Status: Not Started

### Purpose

Install and configure Caddy as the front-door reverse proxy for the LXC container.
Caddy handles TLS (internal CA), security headers, rate limiting, static asset serving
from the versioned build directory, and reverse-proxying of `/api/` to Uvicorn on
`127.0.0.1:8000`. After this chunk, LAN exposure is permitted.

### Prerequisite gate

All mandatory Phase 2 code chunks (P2-1 through P2-6) must be complete and stable
before this chunk is activated for LAN exposure.

### Required inputs

- `design/web/web-control-plane-architecture-phase2.md` §3 (proxy topology, security
  headers, rate limiting, LAN exposure checklist §3.6)
- §4 (build artifact versioning — P2-6 must be done first)
- `install/webui-deploy.sh` from P2-6

### Expected output

```
conf/Caddyfile.example           — Template Caddyfile for the LXC deployment
                                   TLS: tls internal; static asset serve from current symlink;
                                   proxy /api/ to 127.0.0.1:8000; security headers; rate limits
install/caddy-install.sh         — Install Caddy binary, configure as systemd service,
                                   import internal CA cert into OS trust store
systemd/caddy.service.example    — Systemd unit override template for Caddy
```

**LAN exposure checklist (§3.6 sign-off required before activating):**

1. Caddy running as systemd service.
2. TLS: certificate issued from local CA; operator trust imported.
3. HTTPS-only: HTTP redirects to HTTPS.
4. Static assets served from versioned build directory via `current` symlink.
5. Security headers applied (HSTS, X-Content-Type-Options, X-Frame-Options, etc.).
6. Structured JSON access logs.
7. Rate limiting active on `/api/` paths.
8. Uvicorn remains bound to `127.0.0.1` only.
9. CORS allowlist updated to LAN hostname.
10. All mandatory Phase 2 code chunks signed off.

### Acceptance criteria

1. Caddy is running as a systemd service inside the LXC container.
2. HTTPS requests to the LAN hostname serve the SvelteKit SPA from the current build.
3. HTTPS requests to `/api/` are proxied to Uvicorn; bearer token auth works unchanged.
4. HTTP requests are redirected to HTTPS.
5. Security headers are present on all responses (verified with curl).
6. Rate limit policy is active; a burst of requests above the limit receives 429.
7. Uvicorn is not directly reachable from the LAN.
8. All existing integration tests pass (Uvicorn still accessible on localhost for tests).

---

## 10. Phase 2 Optional Items (Deferred)

The following items are documented in the Phase 2 architecture but are not scheduled
for implementation in the current Phase 2 roadmap. They may be adopted independently.

| Item | Condition for adoption | Architecture ref |
|------|----------------------|------------------|
| SSR capability | Multi-user access, FCP > 3s on LAN, or OIDC requirement | §7 |
| SQLite → Postgres migration | p95 write latency > 100ms under load | §8 |
| Background worker (sidecar/thumbnail) | Sidecar fetch or thumbnail generation needed | §9 |
| Task queue (Redis upgrade) | Background worker throughput bottleneck | §9.4 |
| OIDC/OAuth authentication | Multi-operator or MFA requirement | §10 |
| CDN / asset caching | WAN access or multi-site deployment | §12 |

---

## 11. Phase 2 Drift Log

### 11.1 Initial roadmap creation (2026-04-06)

- Phase 1 declared complete; Phase 2 roadmap created.
- Chunked Phase 2 Mandatory items into P2-1 through P2-7.
- Chunk P2-1 (API Client Retry/Backoff) is the first implementation target.

### 11.2 Chunk P2-1 sign-off (2026-04-06)

Chunk P2-1 is implemented and validated.

Changes applied:
- `webui/src/lib/api/client.ts` — added `RETRY_DELAYS_MS`, `jittered()`,
  `retryDelayMs()` helpers; rewrote `apiFetch` with a retry loop for GET/HEAD
  requests (status 0 and 503: up to 3 retries with exponential backoff; status 429:
  respects `Retry-After` header; all mutations fail-fast).
- `webui/src/lib/stores/health.svelte.js` — removed inline `fetch` call; now uses
  `getHealth()` from `$lib/api/health` and `ApiError` from `$lib/api/client`;
  tracks `consecutiveFailures` counter; surfaces error state only after
  `FAILURE_THRESHOLD` (3) consecutive failed polls; resets counter on success.

Test result at closure: 61 passed (full integration suite, no regressions).
