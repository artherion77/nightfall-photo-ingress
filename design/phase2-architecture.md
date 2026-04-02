# Phase 2 Architecture

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering
Depends on: phase1-re-evaluation.md, integration-plan.md, techstack-decision.md

---

## 1. Purpose and Scope

This document defines the Phase 2 architecture for the photo-ingress Web Control Plane.
Phase 2 begins only after Phase 1 (Phases 0–4 in integration-plan.md) is stable and
validated in production use.

Phase 2 has two tiers:

- **Phase 2 Mandatory:** Items that must be completed before LAN exposure is permitted.
  These are prerequisites for any operator access outside localhost.
- **Phase 2 Optional:** Items that improve the system but do not gate LAN exposure.
  They may be adopted independently in any order based on operational need.

---

## 2. Phase 2 Mandatory vs Optional Summary

| Item | Tier | Rationale |
|------|------|-----------|
| Reverse proxy (Nginx or Caddy) | Mandatory | TLS, compression, access logs, rate limiting |
| TLS termination | Mandatory | Operator credentials must not transit LAN in cleartext |
| Proxy-level rate limiting | Mandatory | Replaces in-process Phase 1 rate limiting |
| API versioning policy | Mandatory | Required before any breaking API change |
| Build artifact versioning and rollback | Mandatory | Enables safe re-deployment |
| Retry/backoff for read-only API client | Mandatory | Reduces transient error noise |
| SSR capability | Optional | Only if load time or auth complexity warrants it |
| SQLite → Postgres migration | Optional | Only under concurrency pressure |
| Background worker architecture | Optional | For sidecar/thumbnail processing |
| Task queue (lightweight or Redis) | Optional | Depends on background worker adoption |
| OIDC/OAuth authentication | Optional | For multi-operator environments |
| CDN / asset caching | Optional | For remote access or multi-site deployment |

---

## 3. Reverse Proxy

### 3.1 Decision: Caddy over Nginx

| Factor | Caddy | Nginx |
|--------|-------|-------|
| TLS with automatic cert | Built-in (ACME, internal CA) | Requires certbot or manual config |
| Configuration complexity | Single `Caddyfile`, minimal syntax | `nginx.conf` with multiple blocks |
| Dynamic reload | Built-in | Requires `nginx -s reload` |
| Brotli compression | Built-in | Requires `ngx_brotli` module (often not in distro packages) |
| Structured access logs | JSON logs natively | Requires log format config |
| Systemd socket activation | Supported | Supported |

**Decision:** Caddy is preferred for a single-server LXC deployment. Its automatic TLS
from a local CA (`tls internal`) is a significant operational simplification compared
to manual certificate management. If the operator's environment mandates Nginx for
policy or familiarity reasons, Nginx is an acceptable alternative with equivalent
capability.

### 3.2 Proxy Topology (Phase 2)

```
Internet / LAN operator browser
        │
        │  HTTPS (443)
        ▼
  Caddy (systemd service, :443)
        │
        ├── /           → Static file serve from versioned build directory
        │                 (Cache-Control: immutable for hashed assets)
        │
        ├── /api/       → Reverse proxy to Uvicorn (127.0.0.1:8000)
        │                 (X-Forwarded-For, X-Real-IP forwarded)
        │
        └── /api/docs   → Reverse proxy to Uvicorn (no auth bypass needed;
                          Caddy passes bearer token through)
```

Static assets are served by Caddy directly from the versioned build directory. This
removes static file I/O from the Uvicorn process entirely, improving API response
latency.

### 3.3 Uvicorn Binding Change for Phase 2

In Phase 1, Uvicorn binds to `127.0.0.1:8000` (localhost only).
In Phase 2, this is unchanged. Uvicorn continues to bind to localhost. Caddy is the
only process that accepts external connections. This provides defence-in-depth: even
if Caddy is misconfigured, Uvicorn is not directly reachable from the LAN.

### 3.4 Security Headers at Proxy Level

In Phase 2, security headers move from FastAPI middleware to the Caddy configuration.
Caddy adds these on all responses:

| Header | Value |
|--------|-------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` |

FastAPI middleware that previously set these headers is removed in Phase 2 to avoid
duplication.

### 3.5 Rate Limiting at Proxy Level

In Phase 2, Caddy's rate limiting module (`caddy-ratelimit` or equivalent) replaces the
in-process FastAPI dependency. This provides:

- Rate limiting before requests reach the Python process (lower CPU cost for abusive
  traffic).
- Shared limits for static and API endpoints from a single configuration point.
- Log visibility for rate-limited requests in the access log.

Phase 1 in-process rate limiting is removed when the proxy rate limiting is verified.
Decommissioning the Phase 1 dependency is a mandatory Phase 2 step listed in §3.6.

### 3.6 Phase 2 Mandatory Reverse Proxy Checklist

Before LAN exposure is enabled:

1. Caddy (or Nginx) running as a systemd service in the LXC container.
2. TLS: certificate issued from local CA or self-signed, with operator trust imported.
3. HTTPS-only: HTTP redirects to HTTPS.
4. Static asset serving from versioned build directory (see §4).
5. Security headers applied.
6. Access logs in structured JSON format, written to a log file or journald.
7. Rate limiting active for `/api/` path.
8. Uvicorn remains on `127.0.0.1` only.
9. Phase 1 in-process rate limiting dependency removed.
10. CORS allowlist updated to match the LAN hostname (e.g., `https://photo-ingress.lan`).

---

## 4. Build Artifact Versioning and Rollback

### 4.1 Strategy

In Phase 1, `webui/build/` is overwritten on each deployment. In Phase 2, builds are
versioned using a timestamp or release tag, enabling atomic rollback.

**Directory layout on the LXC host:**

```
/opt/photo-ingress/
  webui/
    releases/
      2026-04-03T1200/     ← named by deployment timestamp or tag
        index.html
        _app/
        200.html
      2026-04-10T0900/     ← newer release
        ...
    current → releases/2026-04-10T0900/   ← symlink; Caddy serves from this path
```

### 4.2 Deployment Procedure

1. Build `webui/build/` locally.
2. Upload `webui/build/` to a new timestamped release directory on the host.
3. Verify the new build directory is complete.
4. Update the `current` symlink atomically.
5. Caddy picks up the new directory on the next request (no restart required if
   symlink resolution is fresh per request — or a Caddy reload is issued).
6. Keep the previous two releases for rollback.

### 4.3 Rollback

To roll back:
1. Re-point the `current` symlink to the previous release directory.
2. No Uvicorn restart required (API is separate from UI assets).
3. No user sessions are lost (the SPA is stateless).

### 4.4 API Release Correlation

Each static build embeds the API version string it was built against (as a
build-time environment variable baked into the SPA). On startup, the SPA can verify
that the API version it expects matches the running API. Version mismatch renders a
banner prompting a page refresh rather than failing silently.

---

## 5. API Versioning Policy

### 5.1 Current State (Phase 1)

All endpoints are under `/api/v1/`. No formal versioning policy exists yet.

### 5.2 Phase 2 Policy

**Version prefix:** All routes carry a major version prefix (`/api/v1/`, `/api/v2/`,
etc.). Minor changes that are backwards compatible do not require a new prefix.

**Breaking vs non-breaking change classification:**

| Change type | Classification |
|-------------|---------------|
| Adding a new field to a response body | Non-breaking |
| Adding a new optional query parameter | Non-breaking |
| Adding a new endpoint | Non-breaking |
| Removing a field from a response body | Breaking |
| Changing a field name or type | Breaking |
| Removing an endpoint | Breaking |
| Changing required headers or auth scheme | Breaking |
| Changing pagination cursor format | Breaking |

**Deprecation timeline:**
- Breaking changes require a new version prefix (e.g., `/api/v2/`).
- The prior version is supported for a minimum of 60 days after the new version
  is available, unless a security issue requires immediate removal.
- Deprecated endpoints return a `Deprecation: true` response header and a
  `Sunset: {date}` header indicating removal date.
- The SPA is updated to use the new version before the old version is sunset.

**Intra-version stability guarantee:**
- Within a single major version, the response shape is stable.
- Additive changes (new optional fields) are permitted without a version bump.
- The OpenAPI schema for each version is snapshotted at release and kept in
  `docs/api/` for reference.

### 5.3 v2 Trigger Conditions

A v2 is warranted when:
- A response shape change requiring a breaking transition is needed (field rename,
  restructure, cursor format migration).
- The authentication scheme migrates from static bearer token to OIDC/OAuth.
- The pagination strategy changes incompatibly.

---

## 6. API Client Retry and Backoff (Phase 2 Mandatory)

### 6.1 Scope of Retry

Retry is applied only to read-only (GET) requests. Mutating requests (POST, PATCH,
DELETE) remain fail-fast with idempotency-key replay as the only retry mechanism.

### 6.2 Retry Policy

| Condition | Retry behaviour |
|-----------|----------------|
| Network failure (status 0) | Retry up to 3 times with exponential backoff |
| HTTP 503 (Service Unavailable) | Retry up to 3 times with exponential backoff |
| HTTP 429 (Rate Limit) | Retry after the `Retry-After` header value |
| HTTP 5xx (other) | No silent retry; show error banner |
| HTTP 4xx | No retry; show error banner |

**Backoff schedule:** initial 500ms, doubling with ±10% jitter. Maximum wait: 8
seconds. If all retries fail, the `ApiError` is surfaced as in Phase 1.

### 6.3 Health Polling Resilience

The `health.svelte.js` store polling interval survives transient failures silently using
the retry policy above. A visible error indicator in the header badge appears only when
three consecutive polls fail after retries.

### 6.4 Mutating Endpoint Retry Pattern

For mutating endpoints, the operator triggers the retry manually via a "Retry" button
on the error banner. The same idempotency key is reused on a manual retry (safe because
the server replays the prior result on a duplicate key). No automatic retry is performed
on mutations.

---

## 7. SSR as Optional Future Mode

### 7.1 Current State (Phase 1)

The SPA uses `@sveltejs/adapter-static`. SSR is disabled. This is an operator-only
tool served from localhost.

### 7.2 Conditions for SSR Adoption (Phase 2 Optional)

SSR is worth revisiting if one of the following becomes true:

1. **Multi-user access:** More than one simultaneous operator session is needed.
   SSR enables server-side auth guard and session isolation without exposing auth state
   to the client.
2. **Load time requirement:** On degraded LAN conditions, a pre-rendered HTML first
   paint is measurably better (threshold: FCP > 3s on nominal LAN connection).
3. **Auth complexity:** The OIDC/OAuth migration (see §10) requires per-request
   server-side cookie validation more naturally handled in a SvelteKit server context.

### 7.3 Upgrade Path

If SSR is adopted:

1. Switch from `@sveltejs/adapter-static` to `@sveltejs/adapter-node`.
2. The SvelteKit Node.js server process runs as a second systemd service
   (`photo-ingress-ui.service`) on `127.0.0.1:3000` (or similar port).
3. Caddy proxies `/` → `127.0.0.1:3000` instead of serving static files directly.
4. API calls in `+page.server.js` load functions use server-side fetch with the
   bearer token in server environment variable (never exposed to client).
5. The Caddy static asset path is removed; Caddy proxies all requests.

### 7.4 Compatibility

The FastAPI API layer is unaffected by the frontend adapter change. The REST API
contract does not change. The SPA upgrade from adapter-static to adapter-node
is a frontend-only migration.

---

## 8. SQLite → Postgres Migration Path (Phase 2 Optional)

### 8.1 Current State

Phase 1 uses SQLite in WAL mode. The registry and all new tables
(`ui_action_idempotency`, `blocked_rules`) are in a single SQLite database.

### 8.2 Migration Trigger Conditions

Migration to Postgres is warranted only if:

- Sustained concurrent write contention produces measurable latency (threshold:
  p95 write latency > 100ms on triage actions under normal operational load).
- Multiple operator sessions require isolation for long-running read transactions.
- The background worker (§9) produces write throughput that starves the CLI poll cycle.

### 8.3 Migration Strategy

If migration is triggered:

1. Introduce a database abstraction layer in the existing domain modules (repository
   pattern). This is a prerequisite for safe migration without changing business logic.
2. Export the SQLite database schema to a Postgres-compatible schema.
3. Migrate existing data with a one-time export/import script.
4. Run the new Postgres instance as a containerised service inside the existing LXC
   container (Postgres in LXC is well-supported and avoids introducing a new container).
5. Update the connection factory in `config.py` to accept a `database_url` configuration
   key; existing SQLite path remains the default.
6. Run the two databases in parallel under a feature flag until validation is complete.
7. Switch to Postgres; keep SQLite as read-only archive for 30 days, then decommission.

### 8.4 Impact on API Layer

The FastAPI application service layer is unaffected if the repository pattern is
correctly implemented. No router, schema, or service logic changes during DB migration.

---

## 9. Background Worker Architecture (Phase 2 Optional)

### 9.1 Scope

The background worker covers:
- Sidecar/XMP metadata fetch jobs.
- On-demand thumbnail generation and disk cache.

Both were deferred from the integration-plan Phase 5 scope.

### 9.2 Architecture

The background worker runs as a third systemd service
(`photo-ingress-worker.service`) inside the same LXC container.

**Job queue:** In the lightweight Phase 2 model, the job queue is a SQLite table
(`sidecar_jobs`, `thumbnail_jobs`) polled at a configurable interval by the worker
process. This requires no new process or dependency beyond SQLite.

The worker is a Python process that:
1. Queries the `sidecar_jobs` table for items with `state = 'queued'`.
2. Claims a batch (updates `state = 'running'`).
3. Executes the job.
4. Updates `state = 'done'` or `state = 'failed'` with error captured.
5. Sleeps for the configured poll interval.

This is a pull-model queue using SQLite as a durable message store. It is simple,
observable, and requires no additional infrastructure.

### 9.3 Worker / API Interaction

- The API enqueues jobs by inserting rows into `sidecar_jobs` table.
- The worker reads and updates those rows.
- SQLite WAL mode accommodates the concurrent access.
- The API exposes job status via `GET /api/v1/items/{item_id}` (sidecar state field).

### 9.4 Upgrade to Redis (Phase 2+ Optional)

If the SQLite-backed queue becomes a bottleneck (high job throughput or many parallel
workers), Redis can replace it. The queue abstraction in the worker service must be
designed as an interface with two implementations (SQLite and Redis) so the switch does
not require changes to the job logic. This is deferred to a phase 2+ iteration.

---

## 10. Enhanced Authentication: OIDC/OAuth (Phase 2 Optional)

### 10.1 Current State

Phase 1 uses a single static bearer token. This is adequate for a solo operator on a
trusted LAN.

### 10.2 Migration Trigger Conditions

- More than one human operator requires individual identity tracking in audit events
  (currently `actor` is always the single configured token name).
- The operator's organisation requires MFA.
- The deployment is exposed beyond the local LAN (e.g., VPN-accessible server).

### 10.3 Proposed Auth Architecture

**Provider:** An existing Authentik, Keycloak, or similar OIDC provider already present
in the operator's infrastructure. No new auth service is introduced specifically for
photo-ingress.

**Integration method:** Caddy handles the OIDC redirect flow via the `caddy-auth-portal`
module or a forward-auth sidecar. The FastAPI backend validates the JWT issued after
successful OIDC login. No session state is stored in the API backend.

**Audit integration:** The `actor` field in audit events transitions from a static token
name to the authenticated user identity (sub claim from JWT). This is a non-breaking
change to the audit_log table (the column already exists).

**Fallback:** Static bearer token auth is preserved as a fallback for automated tooling
(e.g., maintenance scripts that call the API directly). OIDC is the interactive operator
path.

### 10.4 Impact on Phase 1 API Layer

The FastAPI `auth.py` dependency is updated to accept both OIDC JWTs and the static
bearer token. No router, schema, or service logic changes. This is a drop-in replacement
of the auth dependency.

---

## 11. Proxy-Level Rate Limiting

### 11.1 Phase 1 vs Phase 2

Phase 1 implements in-process rate limiting as a FastAPI dependency (token bucket per
route, per source IP, in-memory). This is simple but has limitations:
- State is lost on Uvicorn restart.
- Rate limit state is not shared if multiple Uvicorn workers are used.
- Requests consume Python thread/event loop time before being rejected.

### 11.2 Phase 2 Approach

Caddy's rate limiting module intercepts requests before they reach Python. Benefits:
- Rate limit state survives Uvicorn restarts (Caddy is a separate process).
- Requests are rejected with no Python overhead.
- Rate limit logs appear in Caddy's structured access log alongside all other requests.

### 11.3 Rate Limit Policy (Phase 2)

| Path pattern | Limit | Window |
|-------------|-------|--------|
| `POST /api/` | 30 req/min | Per IP |
| `PATCH /api/` | 30 req/min | Per IP |
| `DELETE /api/` | 20 req/min | Per IP |
| `GET /api/` | 120 req/min | Per IP |
| All paths (global) | 300 req/min | Per IP |

These replace the Phase 1 in-process limits. After Caddy rate limiting is verified,
the Phase 1 FastAPI rate limiting dependency is removed from all routers.

---

## 12. CDN and Asset Caching (Phase 2 Optional)

### 12.1 Applicability

CDN integration is only relevant if:
- The UI is accessed over WAN (not just LAN).
- Static asset load time is a measured operator pain point.
- The deployment is multi-site.

For the standard single-LAN-server LXC deployment, Caddy's local caching headers
on static assets are sufficient.

### 12.2 Caching Strategy for Static Assets

Caddy serves the SvelteKit static build. SvelteKit's Vite build outputs files with
content-hash filenames (e.g., `_app/immutable/entry-abc123.js`). Caddy sets:

```
Cache-Control: public, max-age=31536000, immutable
```

for all files under `_app/immutable/` (never change for a given filename).

For `index.html` and `200.html`:

```
Cache-Control: no-cache
```

This ensures the SPA shell is always fresh while hashed assets are cached aggressively
by the browser.

### 12.3 CDN Integration (Optional, Phase 2+)

If a CDN is warranted, the versioned build directory content is uploaded to the CDN
origin bucket. The CDN is configured to respect `Cache-Control` headers. The Caddy
reverse proxy continues to handle API requests; only static assets are served from CDN.
This requires a configuration step to update the SvelteKit build's `paths.assets` base
to the CDN origin URL.

---

## 13. Phase 2 Deployment Topology

### 13.1 Service Inventory (Phase 2 Mandatory)

```
LXC Container: photo-ingress
┌────────────────────────────────────────────────────────┐
│                                                        │
│  caddy.service               :443 (LAN-facing)         │
│    ↓ /              → webui/current/ (static files)    │
│    ↓ /api/          → 127.0.0.1:8000 (Uvicorn)         │
│                                                        │
│  photo-ingress-api.service   127.0.0.1:8000            │
│    ↓ FastAPI + Uvicorn                                 │
│    ↓ Imports domain modules from nightfall_photo_ingress│
│    ↓ SQLite registry (WAL mode)                        │
│                                                        │
│  photo-ingress-poll.timer    (no socket)               │
│  photo-ingress-trash.timer   (no socket)               │
│    ↓ CLI processes, read/write SQLite registry         │
│                                                        │
│  webui/                                                │
│    releases/                                           │
│      {timestamp}/  ← built artifacts                   │
│    current → releases/{latest}/  ← symlink             │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 13.2 Service Inventory (Phase 2 Optional — Background Worker)

```
│  photo-ingress-worker.service   127.0.0.1 (no socket)  │
│    ↓ Poll sidecar_jobs / thumbnail_jobs tables          │
│    ↓ Executes fetch/generation jobs                    │
│    ↓ SQLite registry (WAL mode, shared)                │
```

### 13.3 Phase 2 Deployment Flow

```
Build machine:
  1. cd webui && npm run build
  2. Tag the build: RELEASE=$(date -u +%Y-%m-%dT%H%M)
  3. Compress: tar -czf photo-ingress-ui-${RELEASE}.tar.gz build/

LXC Container (deploy):
  4. Upload tarball
  5. Expand into: /opt/photo-ingress/webui/releases/${RELEASE}/
  6. Symlink: ln -sfn releases/${RELEASE} current
  7. Perform Caddy config reload (if Caddyfile changed)
  8. Run any pending DB migrations: python -m nightfall_photo_ingress.migrations
  9. Restart photo-ingress-api.service if Python code changed
```

Rollback:
```
  10. ln -sfn releases/${PREVIOUS_RELEASE} current
      (no Uvicorn restart, no data change)
```

---

## 14. Phase 2 Component Dependency Graph

The following graph shows build-time and runtime dependencies between components.
Arrows point from dependent to dependency.

```
Phase 2 Deployment Dependencies
────────────────────────────────

[Operator Browser]
      │
      │ HTTPS
      ▼
[Caddy]
  │           │
  │ /          │ /api/
  ▼           ▼
[webui/current/]   [Uvicorn / FastAPI]
(static files)          │
                        │ Python import
                        ▼
              [nightfall_photo_ingress]
               (domain, registry, config)
                        │
                        ▼
                   [SQLite DB]
                   (WAL mode)
                        ▲
                        │ read/write
              [photo-ingress-poll]
              [photo-ingress-trash]
              [photo-ingress-worker] (optional)
```

**Build-time dependencies:**

```
[SvelteKit build]
  depends on → [API OpenAPI schema] (for type generation, optional)
  depends on → [Design tokens] (tokens.css)
  depends on → [node_modules] (Vite, SvelteKit, TypeScript)
  produces  → [webui/build/]  → deployed to [webui/releases/{tag}/]
```

---

## 15. Phase 1 → Phase 2 Compatibility Guarantees

Phase 2 must not break any Phase 1 operator workflow. The following constraints apply:

| Constraint | How maintained |
|-----------|----------------|
| `/api/v1/` endpoints unchanged | No endpoint is removed or renamed in Phase 2 |
| Auth token still works | Static bearer token remains valid in Phase 2; OIDC is additive |
| CLI ingest unaffected | CLI has no dependency on Caddy, Uvicorn, or the web UI |
| SQLite schema stable | Phase 2 migrations are additive only |
| Feature-flag rollback | UI/API can be stopped without affecting CLI ingest timers |
| RapiDoc docs still accessible | `/api/docs` continues to be proxied through Caddy |

Phase 2 is complete when all mandatory items in §2 are operational and the LAN exposure
checklist in §3.6 is signed off.
