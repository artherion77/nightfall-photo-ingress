# Tech Stack Decision — Web Control Plane

Status: Decided
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
