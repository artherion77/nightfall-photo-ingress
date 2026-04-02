# Integration Plan — Web Control Plane

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Purpose

This document explains how all the design artifacts, architectural decisions, and
implementation components come together into a coherent, step-by-step buildable system.
It is structured as an ordered set of phases that can be executed independently, tested
in isolation, and validated against acceptance conditions before proceeding.

The plan is modular by design. Each phase produces testable deliverables. Rollback
within any phase does not affect the upstream CLI or timer-driven ingest pipeline.

---

## 2. Phase Overview

| Phase | Name | Deliverable |
|-------|------|-------------|
| 0 | Foundation | Project scaffolding, config, CI-readiness |
| 1 | Read-only API | FastAPI app with read-only endpoints serving live data |
| 2 | Read-only UI | SvelteKit SPA wired to read-only API, deployable static build |
| 3 | Triage write path | Accept / reject / defer actions with idempotency and audit |
| 4 | Blocklist management | Blocklist CRUD through UI and API |
| 5 | Sidecar and metadata | Sidecar fetch job queue; metadata enrichment endpoint |
| 6 | Hardening | Rate limiting, structured audit, redaction, security headers |
| 7 | Reverse proxy | Optional Nginx/Caddy integration for TLS and static asset caching |

Phases 0–3 constitute the minimum viable control plane. Phases 4–7 are progressive
enhancements.

---

## 3. Phase 0: Foundation

### 3.1 Goals

- Establish the `api/` and `webui/` directory structures.
- Introduce no new runtime dependencies to the existing CLI.
- Confirm the FastAPI app can be imported and started.
- Scaffold the SvelteKit app with empty routes.

### 3.2 Tasks

1. Create `api/__init__.py`, `api/app.py` (empty FastAPI application factory).
2. Add `fastapi` and `uvicorn[standard]` to `pyproject.toml` as optional extras or a
   new dependency group `[web]`.
3. Add `photo-ingress-api.service` systemd unit template (bind address and port
   configurable via environment variables read from the config file).
4. Run `npx sv create webui` to scaffold the SvelteKit project with:
   - TypeScript enabled.
   - `@sveltejs/adapter-static` configured.
   - Empty routes for `/`, `/staging`, `/audit`, `/blocklist`, `/settings`.
5. Configure `vite.config.js` with `/api` proxy to `localhost:8000`.
6. Add `webui/` entries to `.gitignore`.
7. Validate: `uvicorn api.app:app` starts without errors; `npm run dev` in `webui/`
   serves the empty skeleton.

### 3.3 Acceptance

- `GET /` on Uvicorn returns 404 (no routes yet).
- `npm run build` in `webui/` produces a `build/` directory with `index.html`.
- No existing tests break.

---

## 4. Phase 1: Read-Only API

### 4.1 Goals

Expose all read-only API endpoints from the architecture extension doc. These must
produce correct, paginated data from the live SQLite registry.

### 4.2 Endpoints to Implement

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | Returns poll status, auth status, registry status, disk usage |
| `GET /api/v1/staging` | Paginated list of items with `status=pending`, cursor-based |
| `GET /api/v1/items/{item_id}` | Single item detail |
| `GET /api/v1/audit-log` | Paginated audit events with optional `action=` filter |
| `GET /api/v1/config/effective` | Read-only dump of effective runtime config (secrets redacted) |
| `GET /api/v1/blocklist` | List of current blocklist rules |
| `GET /api/docs` | RapiDoc static page |
| `GET /api/openapi.json` | FastAPI-generated schema |

### 4.3 Backend Integration Points

| API Service | Existing Domain/Registry Module |
|-------------|--------------------------------|
| `HealthService` | `status.py` (reads `/run/nightfall-status.d/photo-ingress.json`) |
| `StagingService` | Registry query layer (existing `domain/` modules) |
| `AuditService` | `audit_log` table in SQLite registry |
| `ConfigService` | `config.py` (reads `photo-ingress.conf`) |
| `BlocklistService` | `blocked_rules` table (new migration) |

### 4.4 Data Flow for Read-Only Endpoints

```
HTTP GET request
  → FastAPI router (path validation, auth dependency)
  → Application service (maps HTTP params to domain query params)
  → Existing registry/domain module (executes SQLite query)
  → Application service (maps domain result to Pydantic response schema)
  → FastAPI router (serialises Pydantic model → JSON response)
  → HTTP response
```

No domain module is modified. The router and service layers are additive.

### 4.5 Auth Dependency

All `/api/v1/` routes require a valid `Authorization: Bearer {token}` header.
The token value is read from `photo-ingress.conf` under a new `[web]` section:
`api_token`. Requests without or with an invalid token receive HTTP 401.

`GET /api/docs` and `GET /api/openapi.json` are exempt from auth to allow browser
access.

### 4.6 Database Migrations

- Introduce `blocked_rules` table (for `GET /api/v1/blocklist`).
- Introduce `ui_action_idempotency` table (for Phase 3).
- Both migrations are gated behind the existing migration runner and are no-ops if
  the table already exists.

### 4.7 Acceptance

- All six read-only endpoints return well-formed JSON with correct HTTP status codes.
- Auth rejection (missing/invalid token) returns 401.
- RapiDoc UI loads at `/api/docs` and lists all endpoints.
- Existing CLI tests still pass (no changes to domain modules).

---

## 5. Phase 2: Read-Only UI

### 5.1 Goals

Wire the SvelteKit SPA to the Phase 1 read-only API. Produce a deployable static
build. Dashboard and audit pages are fully functional.

### 5.2 Component Build Order

Build components in dependency order (dependencies first):

1. **Design tokens** — `tokens.css` with all tokens from `design-tokens.md`.
2. **Common primitives** — `StatusBadge`, `KpiCard`, `LoadingSkeleton`, `ErrorBanner`,
   `EmptyState`, `ActionButton`.
3. **Layout components** — `AppHeader`, `AppFooter`.
4. **Root layout** — `+layout.svelte`, `+layout.js` (health store load).
5. **Stores** — `health.svelte.js`, `kpis.svelte.js`, `auditLog.svelte.js`.
6. **API layer** — `api/client.ts`, `api/health.ts`, `api/staging.ts`, `api/audit.ts`,
   `api/config.ts`.
7. **Dashboard page** — `HealthBar`, `KpiGrid`, `PollRuntimeChart`, `FilterSidebar`,
   `AuditPreview`. Wire to KPI and audit API.
8. **Audit page** — `AuditTimeline`, `AuditEvent`. Wire to audit log API.
9. **Settings page** — `ConfigTable`. Wire to config API.
10. **Staging page skeleton** — `PhotoWheel` (display-only, no triage actions yet).

### 5.3 Header and Footer Integration

**AppHeader:**
- Renders logo, nav tabs (links to `/`, `/staging`, `/audit`, `/blocklist`, `/settings`).
- Active tab is highlighted using `page.url.pathname` from `$app/state`.
- Right side: `StatusBadge` for global health, driven by `health` store.
- Health store is polled every 30 seconds via `setInterval` in the root layout's
  `onMount`.

**AppFooter:**
- Renders: app version (from `+layout.js` data), last poll timestamp (from health
  store), registry status (from health store).
- Updates reactively as health store refreshes.

### 5.4 Page Data Flow (Load Functions)

Each page uses `+page.js` to load initial data:

```
Route: /
  load(): fetches GET /api/v1/staging?limit=0 (for counts) + GET /api/v1/audit-log?limit=5
  Returns: { kpis, recentEvents }
  Component: receives via `let { data } = $props()`
```

```
Route: /staging
  load(): fetches GET /api/v1/staging?limit=20&status=pending
  Returns: { items, cursor, total }
  Component: initialises PhotoWheel with items
```

```
Route: /audit
  load(): fetches GET /api/v1/audit-log?limit=50
  Returns: { events, cursor }
  Component: initialises AuditTimeline
```

```
Route: /blocklist
  load(): fetches GET /api/v1/blocklist
  Returns: { rules }
  Component: initialises BlockRuleList
```

```
Route: /settings
  load(): fetches GET /api/v1/config/effective
  Returns: { config }
  Component: renders ConfigTable
```

### 5.5 Deployment Validation

- `npm run build` in `webui/` produces `webui/build/`.
- FastAPI mounts `webui/build/` as a `StaticFiles` mount.
- Navigating to `http://localhost:8000/` serves the SPA.
- Navigating to `http://localhost:8000/staging` also returns `index.html` (SPA fallback
  handled by adapter-static's `200.html` fallback).

### 5.6 Acceptance

- Dashboard loads with live KPI data and recent audit events.
- Audit page loads with paginated event list.
- Settings page shows effective config (tokens redacted server-side).
- Staging page shows photo wheel with items from the pending queue (no triage yet).
- AppHeader health badge updates live.
- AppFooter last-poll timestamp is accurate.
- Dark-mode design tokens are applied consistently across all pages.

---

## 6. Phase 3: Triage Write Path

### 6.1 Goals

Enable accept, reject, and defer actions through the UI. All mutations must be
idempotent, audit-logged, and guarded by the existing domain invariants.

### 6.2 API Endpoints

| Endpoint | Action |
|----------|--------|
| `POST /api/v1/triage/{item_id}/accept` | Transitions item to accepted state |
| `POST /api/v1/triage/{item_id}/reject` | Transitions item to rejected state |
| `POST /api/v1/triage/{item_id}/defer`  | Returns item to pending without action  |

All mutating endpoints:
- Require `X-Idempotency-Key` header (UUID v4 from client).
- Return 200 with an `action_correlation_id` on success.
- Return the prior response on duplicate idempotency key (idempotent replay).
- Wrap the domain state transition in an audit-first transaction.

### 6.3 Backend Integration

Triage endpoints call the existing domain transition functions (accept, reject) via the
application service layer. The audit-first transaction wrapper ensures that the audit
event is committed before the file system move and registry update. On failure after
audit write, a compensating audit event is written.

### 6.4 UI Integration

1. Complete `PhotoWheel` component with keyboard navigation and mouse-wheel support.
2. Add `TriageControls` (button overlays + drop zones) with drag-and-drop.
3. On Accept or Reject action:
   a. Generate idempotency key (UUID v4).
   b. Apply optimistic update (remove item from wheel).
   c. Call `api/triage.ts` with idempotency key.
   d. On success: wheel advances, health/KPI stores invalidated.
   e. On error: item restored, toast notification shown.
4. Defer: no file system change; item is re-queued for later operator review.

### 6.5 Acceptance

- Accept transitions item from pending to accepted; item disappears from staging queue.
- Reject transitions item to rejected; item disappears from staging queue.
- Duplicate idempotency key returns the same prior result without double-applying.
- Audit log shows the triage event with actor and timestamp.
- Rolling back (disabling API service) has no impact on timer-driven ingest.

---

## 7. Phase 4: Blocklist Management

### 7.1 Goals

Enable operators to add, edit, enable/disable, and delete blocklist rules through the
UI.

### 7.2 API Endpoints

| Endpoint | Action |
|----------|--------|
| `POST /api/v1/blocklist` | Create new rule |
| `PATCH /api/v1/blocklist/{rule_id}` | Update rule (enabled/pattern/reason) |
| `DELETE /api/v1/blocklist/{rule_id}` | Delete rule |

All require `X-Idempotency-Key`. Delete requires confirmation from UI.

### 7.3 UI Integration

1. Complete `BlockRuleList` with toggle, edit, and delete controls.
2. Wire `BlockRuleForm` to `POST /api/v1/blocklist` and `PATCH` API.
3. Wire `ConfirmDialog` to delete flow.
4. Test: blocking a hash prevents future ingestion of that SHA-256.

### 7.4 Acceptance

- A new rule created via UI is persisted in `blocked_rules` table.
- CLI ingest respects blocklist rules from `blocked_rules` table.
- Toggling a rule updates `enabled` flag; disabled rules are not enforced.
- Deleted rules are removed from the database (hard delete for Phase 1).

---

## 8. Phase 5: Sidecar and Metadata (Deferred)

This phase introduces the optional background worker for sidecar fetching. It is not
required for minimum viable operator functionality.

Scope:
- `POST /api/v1/metadata/{item_id}/sidecar-fetch` — Enqueues a sidecar fetch job.
- `sidecar_jobs` table tracks queue state.
- A background task (asyncio task or SQLite-polled loop inside Uvicorn lifespan) picks
  up queued jobs and executes the XMP/sidecar fetch.
- UI: detail view shows sidecar status; manual trigger button.

Precondition: Phase 3 accepted and stable.

---

## 9. Phase 6: Security Hardening

Applies after write-path validation is complete.

### 9.1 Items

| Item | Description |
|------|-------------|
| Rate limiting | Per-route per-IP sliding window. `POST` routes: 30 req/min. `GET` routes: 120 req/min. |
| Structured audit for auth failures | Every 401 and 403 is written to the audit log with IP and requested path. |
| Credential redaction | Tokens, URLs with embedded credentials, and service passwords are redacted in all structured logs. |
| CORS allowlist | Only the configured UI origin is in the CORS allowlist. Default: `http://localhost:8000`. |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`. |
| Input validation coverage audit | Review all path/query/body parameters against schema; confirm no raw string is passed to file system or registry. |

### 9.2 Acceptance

- Auth failure audit entries appear in `/api/v1/audit-log`.
- Structured logs contain no raw token values.
- OWASP Top 10 checklist reviewed; findings documented.

---

## 10. Phase 7: Reverse Proxy (Optional)

For LAN exposure with TLS:

1. Add Nginx or Caddy as a systemd service in the LXC container.
2. Configure TLS termination (self-signed cert or Let's Encrypt via local CA).
3. Proxy `/` → Uvicorn on `127.0.0.1:8000`.
4. Move static file serving to Nginx/Caddy for cache-header control.
5. Update CORS allowlist to use the LAN hostname.

Uvicorn continues to handle only local-origin requests in this topology.

---

## 11. Design System Consistency Rules

To maintain visual consistency across all phases:

1. **No raw values in component styles.** All colours, spacing, radii, and shadows
   reference CSS custom properties from `tokens.css`. No `#hex` or `px` literals in
   component `<style>` blocks.
2. **New pages follow the pattern:** `+page.svelte` renders only layout-level composition
   of components from `$lib/components/`. No ad-hoc styles in page files.
3. **New components register in `design/webui-architecture.md`.** Before creating a new
   component, check if an existing one can be composed. Document additions.
4. **New design tokens are added to `design/design-tokens.md` first.** No new custom
   property is introduced in component code without first being defined in the token
   catalogue.

---

## 12. Cross-Cutting Data Flow Diagram

```
Browser (SvelteKit SPA)
  │
  │  HTTPS (Phase 1+2: HTTP on LAN)
  ▼
FastAPI (Uvicorn)
  │
  │  Import (same process)
  ├──► HealthService ──► status.json file read (read-only)
  ├──► StagingService ──► Registry SQLite (WAL read)
  ├──► AuditService ──► audit_log table (SQLite read)
  ├──► TriageService ──► domain transition functions (SQLite R/W + file system)
  ├──► BlocklistService ──► blocked_rules table (SQLite R/W)
  └──► ConfigService ──► photo-ingress.conf (read-only)

CLI (existing, unmodified)
  │
  └──► Registry SQLite (WAL write — poll and trash cycles)
```

The FastAPI process and CLI processes share the same SQLite file. WAL mode (Write-Ahead
Log) allows concurrent reads from the API while the CLI holds a write transaction.
The API never holds long write transactions — all triage writes are row-level and
complete in milliseconds.

---

## 13. Testing Strategy

### 13.1 API Tests

Extend the existing `tests/` directory with:

- `tests/test_api_health.py` — health endpoint returns expected schema.
- `tests/test_api_staging.py` — staging pagination, filtering, item detail.
- `tests/test_api_triage.py` — accept/reject/defer, idempotency key replay.
- `tests/test_api_blocklist.py` — CRUD operations, enabled toggle.
- `tests/test_api_auth.py` — missing/invalid token → 401.

Tests use `httpx.AsyncClient` with `ASGITransport` pointing at the FastAPI application
factory (same pattern as FastAPI's testing documentation). No live Uvicorn server
required.

### 13.2 UI Tests (Phase 2+)

Playwright integration tests for the SvelteKit UI (located in `tests/integration/ui/`):

- Dashboard loads with mocked API via Playwright route intercept.
- Photo Wheel keyboard navigation advances the wheel correctly.
- Accept action fires the correct API endpoint with idempotency key.
- Error banner appears when API returns 500.

### 13.3 Parity Test

A test that exercises both the CLI triage command and the API triage endpoint on the
same item (in separate runs) and asserts that the resulting registry state is identical.
This enforces the CLI/API behaviour parity invariant.

---

## 14. Rollback Procedure

At any phase, the Web Control Plane can be disabled without affecting the ingest
pipeline:

1. Stop `photo-ingress-api.service`.
2. Optionally remove the `api/` directory and reverse the `pyproject.toml` additions.
3. The `webui/build/` directory can be removed; it has no runtime dependency from the
   Python package.
4. Database tables introduced (`ui_action_idempotency`, `blocked_rules`, `sidecar_jobs`,
   `thumbnails`) are append-only additions. Their presence does not affect the existing
   ingest pipeline if the API service is not running.
5. CLI commands remain authoritative for all ingest operations at all times.
