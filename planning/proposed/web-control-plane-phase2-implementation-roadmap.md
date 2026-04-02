# Web Control Plane — Phase 2 Implementation Roadmap

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering
Depends on: design/web-control-plane-architecture-phase2.md,
            planning/planned/web-control-plane-phase1-scope.md,
            planning/planned/web-control-plane-integration-plan.md

---

## 1. Purpose and Scope

This roadmap breaks Phase 2 of the Web Control Plane into small, independently
deliverable chunks. Prerequisites, migration steps, testing strategy, and rollback
procedures are defined for each chunk.

Phase 2 begins only after Phase 1 (Phases 0–4 of the integration plan) is stable and
validated in production use on localhost.

Phase 2 has two tiers:

- **Mandatory (M):** Must be complete before LAN exposure is permitted.
- **Optional (O):** May be adopted independently in any order based on operational need.

---

## 2. Chunk Inventory and Dependency Order

```
Phase 2 Mandatory Track
───────────────────────

P2-A: Reverse Proxy + TLS           (no prerequisite beyond Phase 1)
P2-B: Build Artifact Versioning     (no prerequisite beyond Phase 1; can parallel P2-A)
P2-C: API Versioning Policy         (no prerequisite beyond Phase 1; documentation only)
P2-D: Rate Limiting Migration       (P2-A required: needs Caddy running)
P2-E: API Client Retry/Backoff      (P2-A preferred: realistic error conditions on LAN)
P2-F: Filter Sidebar                (Phase 1 stable; P2-A preferred)
P2-G: Pagination → Infinite Scroll  (Phase 1 Audit Timeline pagination stable)
P2-H: KPI Threshold Config UI       (Phase 1 config endpoint stable; P2-A preferred)

Phase 2 Optional Track (any order)
───────────────────────────────────

P2-OPT-1: SQLite → Postgres Migration
P2-OPT-2: Background Worker (Sidecar / Thumbnail)
P2-OPT-3: OIDC/OAuth Authentication
P2-OPT-4: SSR Migration
P2-OPT-5: CDN / Advanced Asset Caching
```

**Minimum viable Phase 2 sequence (LAN-exposure gate):**

```
Phase 1 validated
     │
     ├─┬─ P2-B (can run in parallel with P2-A)
     │ └─ P2-C (documentation; run in parallel)
     │
     └── P2-A  →  P2-D  →  LAN exposure gate
              ↘   P2-E
```

All of P2-A through P2-H must be complete and validated before the operator exposes
the system to the LAN. Optional chunks may be adopted after LAN exposure.

---

## 3. Chunk Definitions

---

### P2-A: Reverse Proxy + TLS (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §3

**Goal:** Introduce Caddy as a reverse proxy in front of Uvicorn, terminating TLS,
serving static UI assets, and providing access logging. This chunk is the gate before
any LAN exposure.

**Prerequisites:**
- Phase 1 stable and validated on localhost.
- Caddy available on the LXC host (`apt install caddy` or manual install).

**Tasks:**
1. Write `Caddyfile` for the LXC container:
   - `/api/` proxied to `http://127.0.0.1:8000`.
   - `/` serving static files from `webui/current/` (Phase 1: `webui/build/`).
   - TLS with `tls internal` (self-signed via Caddy's local CA).
   - Security headers (HSTS, X-Content-Type-Options, X-Frame-Options, etc.).
   - Structured JSON access logging to `/var/log/caddy/photo-ingress.access.log`.
2. Install and enable `caddy.service` as a systemd unit.
3. Update CORS allowlist in `photo-ingress.conf` from `http://localhost:8000` to the
   LAN hostname (e.g., `https://photo-ingress.lan`).
4. Verify Uvicorn continues to bind to `127.0.0.1` only.

**Testing:**
- HTTPS connectivity from the operator machine.
- Valid certificate trust (operator imports CA cert once).
- API calls proxied correctly (`GET /api/v1/health` returns 200 via Caddy).
- HTTP 301 redirect to HTTPS (not needed for internal CA TLS).
- Security headers present on all responses.
- RapiDoc accessible at `https://photo-ingress.lan/api/docs`.

**Acceptance criteria:**
- All items in web-control-plane-architecture-phase2.md §3.6 (proxy checklist) are verified.
- Caddy access log contains structured JSON entries for API calls.

**Rollback:**
- Stop and disable `caddy.service`.
- Revert CORS allowlist to `http://localhost:8000`.
- Uvicorn on `127.0.0.1:8000` continues to work unchanged.

---

### P2-B: Build Artifact Versioning (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §4

**Goal:** Switch from overwrite deployment to versioned release directories with
symlink-based rollback. This chunk is independent of P2-A and can be done in parallel.

**Prerequisites:**
- Phase 1 deployment script exists (simple `rsync`).

**Tasks:**
1. Create the releases directory structure on the LXC host:
   ```
   /opt/photo-ingress/webui/releases/
   /opt/photo-ingress/webui/current -> (symlink)
   ```
2. Update the deployment script to:
   - Create `releases/$(date -u +%Y-%m-%dT%H%M)/` from the built `webui/build/` output.
   - Update the `current` symlink atomically after verifying the directory.
   - Retain the previous two releases; prune older ones.
3. Update the Caddyfile `root` path from `webui/build/` to `webui/current/` (or add
   this step to P2-A if P2-A runs first).
4. Embed the release tag in the SPA build (`PUBLIC_API_VERSION` build environment
   variable) for API version mismatch detection.

**Testing:**
- Deploy version A, verify it serves correctly.
- Deploy version B, verify it serves correctly.
- Rollback: re-point symlink to version A, verify it serves version A.
- Rollback requires no Uvicorn restart (API is independent of static assets).

**Acceptance criteria:**
- `current` symlink is updated atomically.
- Two prior releases are retained on disk.
- Rollback completes in under 5 seconds (symlink swap only).

**Rollback:**
- Re-point `current` symlink to the previous release directory.
- No service restarts required.

---

### P2-C: API Versioning Policy (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §5

**Goal:** Document and operationalise the API versioning policy before any endpoint
leaves experimental status or a breaking change is needed.

**Prerequisites:**
- Phase 1 API endpoints stable.

**Tasks:**
1. Snapshot the current OpenAPI schema: `docs/api/v1-snapshot-{date}.json`.
2. Add a response header utility in `api/middleware.py` to emit `Deprecation` and
   `Sunset` headers on deprecated routes.
3. Write a brief internal guide in `docs/api/versioning-guide.md` summarising the
   policy from web-control-plane-architecture-phase2.md §5.2 (breaking vs non-breaking classification,
   deprecation timeline, v2 triggers).

**Testing:**
- Schema snapshot file exists and is parseable.
- Deprecation header utility emits correct headers when enabled on a test route.

**Acceptance criteria:**
- OpenAPI schema snapshot committed under `docs/api/`.
- Versioning guide committed.
- Header utility verified.

**Rollback:** N/A — this is purely documentation and a utility. No rollback needed.

---

### P2-D: Rate Limiting Migration to Proxy (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §11

**Goal:** Move rate limiting from the in-process FastAPI dependency (Phase 1) to
Caddy-level rate limiting. Remove the in-process dependency once the proxy limits
are verified.

**Prerequisites:** P2-A (Caddy running).

**Tasks:**
1. Install the `caddy-ratelimit` plugin or equivalent Caddy rate limiting module.
2. Add rate limit directives to the Caddyfile per the policy in
   web-control-plane-architecture-phase2.md §11.3.
3. Reload Caddy with the updated config.
4. Verify rate limits fire at the proxy layer (test at 31 POST req/min → 429).
5. Remove the Phase 1 FastAPI rate limiting decorator/dependency from all API routers.
6. Restart `photo-ingress-api.service` to apply the removal.

**Testing:**
- Rate limit fires at Caddy before the request reaches Python.
- Removal of in-process limiter does not affect normal request processing.
- 429 response from Caddy includes `Retry-After` header.

**Acceptance criteria:**
- No rate limiting code in the Python API layer.
- Caddy access log shows 429 entries for limit-exceeded requests.

**Rollback:**
- Re-add the FastAPI rate limiting dependency.
- Remove rate limit directives from Caddyfile and reload.

---

### P2-E: API Client Retry and Backoff (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §6

**Goal:** Add retry with exponential backoff to read-only API client calls in the SPA.
Mutating endpoints remain fail-fast.

**Prerequisites:** Phase 1 API client stable; P2-A preferred (proxy error conditions
are more realistic for testing on LAN).

**Tasks:**
1. Add a `withRetry(fn, opts)` wrapper in `src/lib/api/client.js`:
   - Retries up to 3 times on 503 and network failure (status 0).
   - Respects `Retry-After` header on 429.
   - Exponential backoff: initial 500ms, ×2 with ±10% jitter, max 8s.
   - Does not retry 4xx (other than 429) or 5xx (other than 503).
2. Apply the wrapper to all GET functions in the API modules (`health.js`, `kpi.js`,
   `audit.js`, `staging.js`, `blocklist.js`, `config.js`).
3. Update the `health.svelte.js` store so that three consecutive poll failures after
   retries trigger the error indicator in the header badge.

**Testing:**
- Mock 503 → retry → succeed: component shows no error.
- Mock three consecutive 503 after retries: `ErrorBanner` is shown.
- POST request with a 503: fail-fast, no retry, `ErrorBanner` shown immediately.

**Acceptance criteria:**
- GET calls retry silently on transient failures.
- POST/PATCH/DELETE calls never retry automatically.
- Health badge shows degraded state only after three consecutive failed polls.

**Rollback:**
- Feature-flag the retry wrapper: `RETRY_ENABLED` build variable. Setting it to `false`
  at build time bypasses the wrapper and restores fail-fast behaviour everywhere.

---

### P2-F: Filter Sidebar (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §13

**Goal:** Add the `FilterSidebar` component to the Dashboard, enabling file-type
filtering of KPI counts and the audit preview.

**Prerequisites:** Phase 1 Dashboard stable and in use. P2-A preferred (proxy provides
cleaner baseline for UI testing).

**Tasks:**
1. Build `FilterSidebar.svelte` component:
   - Props: `options: string[]` (from `config.allowed_types`), `selected: string`,
     `onChange: (type: string) => void`.
   - Displays checkbox list with "All Files" as the default/reset option.
   - Uses `--surface-raised` background, standard spacing tokens.
2. Update the Dashboard page CSS grid to include the sidebar column.
3. Add `filterType` state to the Dashboard page (`$state`). Pass to `FilterSidebar`.
4. Propagate `filterType` as `?type=` query parameter to all Dashboard data loads
   (`KpiCard` counts, `AuditPreview`).
5. Implement responsive collapse:
   - Tablet: slide-out drawer triggered by a filter icon button.
   - Mobile: modal sheet triggered by a button.
6. Update `GET /api/v1/config` response to include `allowed_types: string[]` (additive
   non-breaking change).

**Testing:**
- Selecting `Images` changes all KPI counts to image-only values.
- "All Files" resets to unfiltered state.
- Sidebar collapses correctly at ≤1023px.
- Drawer/modal behaviour verified on tablet and mobile viewport.

**Acceptance criteria:**
- Filter affects KPI counts shown on screen.
- Responsive collapse functions correctly at tablet and mobile breakpoints.
- Phase 1 API endpoints unchanged except for the additive `allowed_types` field.

**Rollback:**
- Hide `FilterSidebar` with a CSS `display: none` feature flag driven by a build
  variable. The grid column reverts to full-width.

---

### P2-G: Pagination → Infinite Scroll (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §14

**Goal:** Replace the explicit `LoadMoreButton` in the Audit Timeline with an
IntersectionObserver-based automatic scroll trigger.

**Prerequisites:** Phase 1 Audit Timeline cursor pagination working correctly.

**Tasks:**
1. Add a sentinel `<div>` as the last element in the `AuditTimeline` list.
2. Attach an `IntersectionObserver` to the sentinel in `onMount`; disconnect in
   `onDestroy`.
3. When sentinel enters viewport (within 200px of bottom), fire the next-page fetch
   if more pages are available.
4. Show `<LoadingSkeleton>` rows while the next page loads.
5. Remove the sentinel from the DOM when no more pages are available.
6. Ensure filter changes reset the cursor and clear the appended list.
7. Keep `LoadMoreButton` in `src/lib/components/common/` — it continues to be used
   by other paginated lists.

**Testing:**
- Slow-scroll to bottom of a multi-page list triggers automatic next-page load.
- Filter change → list resets to first page correctly.
- `LoadingSkeleton` appears during fetch and disappears on completion.
- Sentinel is absent from DOM when list is exhausted.
- Keyboard accessibility: Tab and Enter still work for filter tab bar.

**Acceptance criteria:**
- Operator can scroll through the entire audit history without manual clicks.
- Backend API endpoint unchanged.

**Rollback:**
- Re-render `<LoadMoreButton>` in `AuditTimeline.svelte` and remove the
  IntersectionObserver code. Single component change.

---

### P2-H: KPI Threshold Configuration UI (Mandatory)

**Reference:** web-control-plane-architecture-phase2.md §15

**Goal:** Add a Settings page section for editing KPI thresholds in-browser. Operator
no longer needs SSH to change thresholds.

**Prerequisites:** Phase 1 config API endpoint returning `kpi_thresholds`. P2-A
preferred (Settings page accessed over HTTPS).

**Tasks:**

**Backend:**
1. Add `config_overrides` table to the SQLite database (migration script, applied on
   API start).
2. Implement `PATCH /api/v1/config/thresholds` endpoint with Pydantic validation:
   - `warning < error` enforced for all metrics.
   - All values non-negative.
   - Unknown metric keys rejected (422).
   - Overrides persisted to `config_overrides` table.
3. Update `GET /api/v1/config` to merge `kpi_thresholds` from config file baseline
   and `config_overrides` table (overrides take precedence).

**Frontend:**
4. Add "KPI Thresholds" section to the Settings page.
5. One row per metric: label, warning input, error input, unit indicator.
6. Inline validation (warning < error) before enabling the Save button.
7. "Save" calls `PATCH /api/v1/config/thresholds`; success toasts confirmation.
8. "Reset to defaults" calls `DELETE /api/v1/config/thresholds` (drops override row).

**Testing:**
- Change Pending threshold warning to 30 → KPI card changes to amber at 31 items.
- Invalid input (warning ≥ error) → Save button disabled, inline error shown.
- Reset to defaults → thresholds revert to values from config file.
- `GET /api/v1/config` after PATCH reflects updated values.

**Acceptance criteria:**
- Threshold changes take effect on next KPI card render without page reload.
- No SSH required to change thresholds.

**Rollback:**
- Drop the `config_overrides` table row for thresholds; API falls back to config-file
  values on next API restart.
- The Settings UI form can be hidden with a build variable.

---

### P2-OPT-1: SQLite → Postgres Migration (Optional)

**Reference:** web-control-plane-architecture-phase2.md §8

**Trigger conditions:** See web-control-plane-architecture-phase2.md §8.2 (write contention, multi-user,
or background worker write throughput).

**Tasks:**
1. Introduce a repository pattern (abstraction layer) in all domain modules as a
   prerequisite. This must be done before swapping the database engine.
2. Write a `postgres_schema.sql` from the existing SQLite schema.
3. Write a migration script (Python) to export SQLite data and import to Postgres.
4. Run both databases in parallel under a `database_backend` feature flag.
5. Validate under normal operational load.
6. Switch to Postgres; keep SQLite as read-only archive for 30 days, then decommission.

**Prerequisites:** P2-B (artifact versioning), Phase 1 stable for ≥ 4 weeks.

**Rollback:**
- Flip `database_backend` feature flag back to SQLite.
- No data loss (SQLite archive retained for 30 days).

---

### P2-OPT-2: Background Worker (Optional)

**Reference:** web-control-plane-architecture-phase2.md §9

**Trigger conditions:** Sidecar/XMP metadata fetching or thumbnail generation demand
arises in operator use.

**Tasks:**
1. Define `sidecar_jobs` and `thumbnail_jobs` SQLite tables (migration added to
   existing schema).
2. Implement `photo-ingress-worker.service` (Python process, systemd unit file).
3. Add API endpoints to enqueue and query job status.
4. Write worker pull-model loop (poll, claim, execute, update state).
5. Test with synthetic job workload.

**Prerequisites:** P2-OPT-1 preferred if write throughput is expected to be high;
SQLite acceptable for low job rates.

**Rollback:**
- Disable and stop `photo-ingress-worker.service`. Job tables remain but are inert.

---

### P2-OPT-3: OIDC/OAuth Authentication (Optional)

**Reference:** web-control-plane-architecture-phase2.md §10

**Trigger conditions:** Multiple human operators, MFA requirement, or WAN exposure.

**Tasks:**
1. Configure Caddy forward-auth or `caddy-auth-portal` for OIDC redirect flow toward
   an existing Authentik/Keycloak instance.
2. Update `api/auth.py` to validate OIDC JWTs alongside the static bearer token.
3. Update audit_log `actor` field population to use JWT `sub` claim for interactive
   operator sessions.
4. Validate that static bearer token auth continues to work for automated tooling.
5. Document the OIDC configuration in `docs/web/oidc-setup.md`.

**Prerequisites:** P2-A (Caddy reverse proxy). OIDC provider already operational in
operator's infrastructure.

**Rollback:**
- Remove OIDC configuration from Caddyfile.
- Revert `auth.py` to static-bearer-token-only acceptance.
- Static bearer token access unaffected throughout.

---

### P2-OPT-4: SSR Migration (Optional)

**Reference:** web-control-plane-architecture-phase2.md §7

**Trigger conditions:** FCP > 3s on nominal LAN connection, multi-user requirement, or
OIDC adoption requiring server-side cookie handling.

**Tasks:**
1. Switch `svelte.config.js` from `@sveltejs/adapter-static` to
   `@sveltejs/adapter-node`.
2. Write/adjust `photo-ingress-ui.service` systemd unit (Node.js process on
   `127.0.0.1:3000`).
3. Update Caddyfile: remove static file `root`, add `reverse_proxy /` to
   `127.0.0.1:3000`.
4. Move bearer token from client-side store to server environment variable.
5. Migrate `+page.js` load functions to `+page.server.js` where API calls now happen
   server-side.
6. Verify all routes render correctly.

**Prerequisites:** P2-A (Caddy reverse proxy). Performance measurement justifying the
migration.

**Rollback:**
- Stop `photo-ingress-ui.service`.
- Revert Caddyfile to static file serving from `webui/current/`.
- Revert `svelte.config.js` to adapter-static.
- The FastAPI API layer is unaffected throughout.

---

### P2-OPT-5: CDN / Advanced Asset Caching (Optional)

**Reference:** web-control-plane-architecture-phase2.md §12

**Trigger conditions:** WAN access, static asset load time is a measured pain point,
or multi-site deployment.

**Tasks:**
1. Verify Caddy `Cache-Control: public, max-age=31536000, immutable` on all
   `_app/immutable/` assets and `Cache-Control: no-cache` on `index.html`.
2. If CDN warranted: configure CDN (Cloudflare, BunnyCDN, etc.) as origin pull from
   the Caddy server.
3. Update SvelteKit `paths.assets` to the CDN origin URL.
4. Rebuild and redeploy.
5. Verify hashed assets are served from CDN with `HIT` cache status.
6. Verify `index.html` remains uncached (always fetched from origin).

**Prerequisites:** P2-A + P2-B.

**Rollback:**
- Revert `paths.assets` to empty string (relative URLs, served from Caddy directly).
- CDN can be left in place but will no longer be used.

---

## 4. Testing Strategy

### 4.1 Per-Chunk Testing

Each chunk has acceptance criteria listed in §3. Testing is done in the LXC development
environment before applying changes to production.

### 4.2 System Integration Validation

After all mandatory chunks are complete, the following system-level tests are run:

| Test | Checks |
|------|-------|
| Phase 1 API endpoints unchanged | All Phase 1 routes respond correctly through Caddy |
| Operator triage workflow end-to-end | Accept/Reject/Defer an item, verify audit log |
| Blocklist CRUD end-to-end | Add, edit, disable, delete a rule |
| Rate limit verification | 31 POST req/min returns 429 at proxy level |
| Rollback drill | Deploy two versions, roll back to v1, verify v1 is served |
| TLS certificate trust | No certificate warnings in operator browser |
| Security headers audit | All required headers verified via curl |

### 4.3 No-Regression Requirement

The CLI ingest timers (`photo-ingress-poll.timer`, `photo-ingress-trash.timer`) must
continue to function correctly throughout all Phase 2 changes. These are independent of
the web layer; no Phase 2 change touches the CLI ingest code path.

---

## 5. Rollout Strategy

### 5.1 Sequencing

Phase 2 mandatory chunks are deployed in the following order to minimise risk:

1. P2-C (API versioning documentation; no risk, no service change).
2. P2-B (artifact versioning; deploy script change, no service restart).
3. P2-A (Caddy introduction; the biggest single change; validates on localhost first).
4. P2-D (rate limiting migration; runs after P2-A).
5. P2-E (retry/backoff in the SPA; deploy via P2-B versioned build process).
6. P2-F, P2-G, P2-H (UI enhancements; deployable in any order after P2-E).

### 5.2 LAN Exposure Gate

LAN exposure is not enabled until every item in the Phase 2 mandatory checklist
(web-control-plane-architecture-phase2.md §3.6) is signed off by the operator. This checklist is
reproduced here as a gate:

- [ ] Caddy running as a systemd service.
- [ ] TLS certificate trusted by the operator machine.
- [ ] HTTP → HTTPS redirect in place.
- [ ] Static assets served from versioned `webui/current/` directory.
- [ ] Security headers verified.
- [ ] Structured JSON access logs operational.
- [ ] Rate limiting active at proxy level.
- [ ] Uvicorn bound to `127.0.0.1` only.
- [ ] Phase 1 in-process rate limiting dependency removed.
- [ ] CORS allowlist updated to LAN hostname.

### 5.3 Operational Readiness

Before enabling LAN exposure:
- The operator has a working rollback procedure (symlink swap, verified by drill).
- The operator machine trusts the Caddy-issued TLS certificate.
- The access log path is rotated by logrotate or journald.

---

## 6. Rollback Summary

| Chunk | Rollback procedure | Data risk |
|-------|-------------------|-----------|
| P2-A  | Stop Caddy, revert CORS | None |
| P2-B  | Re-point symlink | None |
| P2-C  | Delete snapshot files | None |
| P2-D  | Re-add FastAPI limiter, remove Caddy limits | None |
| P2-E  | Set `RETRY_ENABLED=false` build var, redeploy | None |
| P2-F  | Hide sidebar via build var, redeploy | None |
| P2-G  | Swap IntersectionObserver for LoadMoreButton in one component | None |
| P2-H  | Drop `config_overrides` table row, restart API | Overrides lost; reverts to defaults |
| P2-OPT-1 | Flip `database_backend` flag to SQLite | SQLite archive kept 30d |
| P2-OPT-2 | Disable `photo-ingress-worker.service` | Jobs in queue lost |
| P2-OPT-3 | Remove OIDC Caddyfile config, revert `auth.py` | None |
| P2-OPT-4 | Stop Node.js service, revert Caddyfile | None |
| P2-OPT-5 | Revert `paths.assets` to relative, redeploy | None |
