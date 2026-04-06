# Integration Plan — Web Control Plane

Status: Local control plane baseline implemented through Phase 4; hardening and LAN-exposure phases remain planned
Date: 2026-04-06
Owner: Systems Engineering

## Implementation status (as of 2026-04-06)

| Phase | Name | Status |
|-------|------|--------|
| 0 | Foundation | Implemented |
| 1 | Read-only API | Implemented |
| 2 | Read-only UI | Implemented |
| 3 | Triage write path | Implemented |
| 4 | Blocklist management | Implemented |
| 5 | Sidecar and metadata | Deferred / not started |
| 6 | Hardening | Partial foundations only |
| 7 | Reverse proxy | Not started |

This plan originally described the entire web control plane build-out from zero. The
current repository has already delivered the local-control-plane baseline through
Phase 4: FastAPI API routes, static SPA serving, read-only pages, triage writes, and
blocklist CRUD are in place. Remaining work is now about closing the hardening gap,
preparing LAN exposure under the Phase 2 architecture, and deferring worker/metadata
capabilities until that foundation is stable. All CLI and ingest pipeline functionality
remain independent of the control plane.

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
| 6 | Hardening | Structured audit, redaction, CORS, security headers |
| 7 | Reverse proxy | Optional Nginx/Caddy integration for TLS and static asset caching |

Phases 0–3 constitute the minimum viable control plane. Phases 4–7 are progressive
enhancements.

### 2.1 Drift review summary

- **Implemented in code:** Phases 0 through 4 are already shipped.
- **Not yet implemented:** Phase 5 sidecar/metadata, Phase 7 reverse proxy/LAN exposure.
- **Partially implemented:** Phase 6 has some foundations only: bearer-token auth,
  config redaction, same-origin SPA/API serving, and additive schema support for web
  tables. Auth-failure audit events, CORS allowlist policy, and security-header
  enforcement are not yet complete. Request throttling remains deferred to Phase 2
  proxy controls.
- **Superseding design note:** LAN exposure is no longer just an optional finishing
  step. `design/web/web-control-plane-architecture-phase2.md` makes reverse proxy,
  TLS, proxy-level headers, and proxy-level rate limiting mandatory before any
  operator access outside localhost.

### 2.2 Recommended execution sequence from the current state

Recommended order to reach the intended design end state:

1. **Phase 6A — finish hardening on the current localhost topology.**
   - Close the baseline security gaps that are independent of proxy choice: auth-failure
     audit, explicit CORS policy, input-validation audit, and documented header policy.
   - Do not spend effort building a throwaway in-process rate limiter first; the Phase 2
     architecture already makes proxy-level limiting the durable target.
2. **Phase 7A / Phase 2 mandatory LAN-exposure platform work.**
   - Introduce Caddy, TLS, versioned static build releases, structured access logging,
     and proxy-level security headers.
   - Keep Uvicorn bound to `127.0.0.1`.
3. **Phase 7B / remaining Phase 2 mandatory UX/runtime work.**
   - Complete API/client retry and backoff behavior, filter sidebar, audit infinite
     scroll, and threshold-management work that the Phase 2 architecture marks as
     required before broader operator use.
4. **Stability gate.**
   - Run the LAN-exposed control plane in stable use and verify rollback, logs,
     and operator workflows before introducing background-worker complexity.
5. **Only then reopen Phase 5 as a later-phase worker/metadata program.**
   - Sidecar/thumbnail/metadata work should follow the stronger sequencing in
     `design/web/web-control-plane-architecture-phase3.md`, not jump ahead of the
     hardening and LAN-exposure gate.

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

Current runtime note: request-scoped dependencies read `AppConfig` and the registry
connection from `request.app.state`, populated during FastAPI lifespan startup.

### 4.5 Auth Dependency

All `/api/v1/` routes require a valid `Authorization: Bearer {token}` header.
The token value is read from `photo-ingress.conf` under a new `[web]` section:
`api_token`. Requests without or with an invalid token receive HTTP 401.

`GET /api/docs` and `GET /api/openapi.json` are exempt from auth to allow browser
access.

### 4.6 Database Migrations

- Introduce `blocked_rules` table (for `GET /api/v1/blocklist`).
- Introduce `ui_action_idempotency` table (for Phase 3).
- In the current runtime, both are additive optional tables created idempotently by
  `_ensure_optional_tables()` during `Registry.initialize()`.
- Standalone files may exist under `src/nightfall_photo_ingress/migrations/`, but there
  is no active numbered migration runner for these tables.

### 4.7 Acceptance

- All six read-only endpoints return well-formed JSON with correct HTTP status codes.
- Auth rejection (missing/invalid token) returns 401.
- RapiDoc UI loads at `/api/docs` and points to `/api/openapi.json`.
- Existing CLI and unit tests still pass (no changes to domain modules).

---

## 5. Phase 2: Read-Only UI

Implementation status: Implemented, then extended by later phases

### 5.1 Goals

Wire the SvelteKit SPA to the Phase 1 read-only API. Produce a deployable static
build. Dashboard and audit pages are fully functional.

### 5.2 Component Build Order

Build components in dependency order (dependencies first):

1. **Design tokens** — `tokens.css` with all tokens from `design/web/webui-design-tokens-phase1.md`.
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
- Health polling is owned by the `health.svelte.js` store via `connect()` /
  `disconnect()`, called from the root layout.

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
  load(): fetches GET /api/v1/staging?limit=20
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
- Staging page shows photo wheel with items from the pending queue.
- Blocklist page remains functional as a read-only view at this phase, though later
  phases now extend it with write controls in the current implementation.
- AppHeader health badge updates live.
- AppFooter last-poll timestamp is accurate.
- Dark-mode design tokens are applied consistently across all pages.

---

## 6. Phase 3: Triage Write Path

Implementation status: Implemented

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
2. Add `TriageControls` with inline action buttons and CTA buttons.
3. On Accept or Reject action:
   a. Generate idempotency key (UUID v4).
   b. Apply optimistic update (remove item from wheel).
   c. Call `api/triage.ts` with idempotency key.
   d. On success: wheel advances, health/KPI stores invalidated.
   e. On error: item restored, toast notification shown.
4. Defer: no file system change; item is re-queued for later operator review.

Current implementation note:
- Drag-and-drop zones were deferred. The shipped interaction model is keyboard/button
  driven, with defer available through the staging page interaction model rather than
  a dedicated drag/drop surface.

### 6.5 Acceptance

- Accept transitions item from pending to accepted; item disappears from staging queue.
- Reject transitions item to rejected; item disappears from staging queue.
- Duplicate idempotency key returns the same prior result without double-applying.
- Audit log shows the triage event with actor and timestamp.
- Rolling back (disabling API service) has no impact on timer-driven ingest.

---

## 7. Phase 4: Blocklist Management

Implementation status: Implemented

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

Current sequencing note:
- This phase is intentionally **not** the next recommended implementation step.
- The more recent Phase 2 and Phase 3 architecture documents move worker/sidecar work
  behind the hardening and LAN-exposure gate.
- Any future implementation of this phase should be aligned with
  `design/web/web-control-plane-architecture-phase3.md`, which supersedes the earlier
  single-process sketch below.

Scope:
- `POST /api/v1/metadata/{item_id}/sidecar-fetch` — Enqueues a sidecar fetch job.
- `sidecar_jobs` table tracks queue state.
- A background task (asyncio task or SQLite-polled loop inside Uvicorn lifespan) picks
  up queued jobs and executes the XMP/sidecar fetch.
- UI: detail view shows sidecar status; manual trigger button.

Precondition: Phase 6 completed, Phase 2 mandatory LAN-exposure work signed off, and
post-LAN stabilization complete.

---

## 9. Phase 6: Security Hardening

Applies after write-path validation is complete.

Current status note:
- Foundations present today: bearer-token auth, config redaction, same-origin serving,
  and structured/redacted logging support in the broader application.
- Not yet complete for the control plane: auth-failure audit entries, explicit CORS
  allowlist enforcement, and security headers. Request throttling remains deferred
  to the mandatory Phase 2 proxy-level LAN gate.

### 9.1 Items

| Item | Description |
|------|-------------|
| Request throttling | Deferred to mandatory proxy-level controls in Phase 2 before LAN exposure; no Phase 1 throttling implementation gate. |
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

## 10. Phase 7: Reverse Proxy / LAN Exposure Gate

For localhost-only usage, this phase remains optional. For any LAN exposure, it is
mandatory and is governed by `design/web/web-control-plane-architecture-phase2.md`.

For LAN exposure with TLS:

1. Add Caddy (preferred) or Nginx as a systemd service in the LXC container.
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
3. **New components register in `design/web/webui-architecture-phase1.md`.** Before creating a new
   component, check if an existing one can be composed. Document additions.
4. **New design tokens are added to `design/web/webui-design-tokens-phase1.md` first.** No new custom
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

Current implemented API integration suite lives under `tests/integration/api/`:

- `test_health.py`
- `test_staging.py`
- `test_audit_log.py`
- `test_config.py`
- `test_auth.py`
- `test_api_triage.py`
- `test_blocklist.py`

Tests use `httpx.AsyncClient` with `ASGITransport` pointing at the FastAPI application
factory (same pattern as FastAPI's testing documentation). No live Uvicorn server
required.

### 13.2 UI Tests (Phase 2+)

Current implemented UI-facing integration suite lives under `tests/integration/ui/`:

- `test_dashboard.py`
- `test_audit.py`
- `test_settings.py`
- `test_staging_display.py`
- `test_triage.py`
- `test_triage_error_recovery.py`
- `test_blocklist_crud.py`
- `test_error_states.py`

These are pytest integration tests against the ASGI app and a stubbed static SPA shell.
They validate route/data contracts and mutation flows, but they are **not** a real
browser DOM/Playwright harness yet.

Future browser automation remains useful, but it is a separate follow-up rather than a
current implementation fact.

### 13.3 Parity Test

This remains a recommended future regression test. No dedicated CLI/API parity test is
currently checked in.

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
