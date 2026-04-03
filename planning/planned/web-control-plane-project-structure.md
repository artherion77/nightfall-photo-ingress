# Project Structure — Web Control Plane Extension

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Context

This document describes the folder structure introduced by the Web Control Plane
extension and explains the rationale for each addition. The existing project structure
is preserved in full. All new directories are additive.

---

## 2. Repository Root Layout (Extended)

```
nightfall-photo-ingress/
│
├── src/                            # Existing: core Python package
│   └── nightfall_photo_ingress/
│       ├── adapters/
│       ├── domain/
│       ├── migrations/
│       ├── runtime/
│       ├── cli.py
│       ├── config.py
│       └── ...
│
├── api/                            # NEW: FastAPI application
│   ├── app.py
│   ├── auth.py
│   ├── rate_limit.py
│   ├── audit_hook.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── staging.py
│   │   ├── triage.py
│   │   ├── audit_log.py
│   │   ├── blocklist.py
│   │   ├── config.py
│   │   └── metadata.py
│   ├── services/
│   │   ├── staging_service.py
│   │   ├── triage_service.py
│   │   ├── audit_service.py
│   │   ├── blocklist_service.py
│   │   └── config_service.py
│   └── schemas/
│       ├── staging.py
│       ├── triage.py
│       ├── audit.py
│       ├── blocklist.py
│       └── health.py
│
├── webui/                          # NEW: SvelteKit single-page application
│   ├── src/
│   │   ├── lib/
│   │   │   ├── api/                # REST API fetch wrappers
│   │   │   ├── components/         # Shared Svelte components
│   │   │   ├── stores/             # Svelte stores (global state)
│   │   │   └── tokens/             # Design tokens (CSS custom properties)
│   │   ├── routes/
│   │   │   ├── +layout.svelte      # Root layout (header + footer)
│   │   │   ├── +layout.js
│   │   │   ├── +page.svelte        # Dashboard (/)
│   │   │   ├── staging/
│   │   │   │   └── +page.svelte    # Staging Queue / Photo Wheel
│   │   │   ├── audit/
│   │   │   │   └── +page.svelte    # Audit Timeline
│   │   │   ├── blocklist/
│   │   │   │   └── +page.svelte    # Blocklist / Rules
│   │   │   └── settings/
│   │   │       └── +page.svelte    # Settings / Config view
│   │   └── app.html
│   ├── static/
│   │   ├── favicon.svg
│   │   └── rapiddoc/               # RapiDoc static asset
│   │       └── rapidoc-min.js
│   ├── package.json
│   ├── svelte.config.js
│   └── vite.config.js
│
├── design/                         # EXISTING + EXTENDED: architecture and UI specs
│   ├── architecture.md
│   ├── web-control-plane-architecture-extension.md
│   ├── webui-architecture-phase1.md       # NEW
│   ├── webui-design-tokens-phase1.md            # NEW
│   ├── webui-component-mapping-phase1.md               # NEW
│   └── ui-mocks/
│       ├── Astronaut photo review interface.png
│       └── Photo-ingress dashboard with KPIs and audit.png
│
├── planning/                       # EXISTING + EXTENDED
│   ├── iterative-implementation-roadmap.md
│   ├── web-control-plane-integration-plan.md
│   ├── techstack-decision.md       # NEW
│   ├── project-structure.md        # NEW (this document)
│   └── integration-plan.md         # NEW
│
├── install/
├── systemd/
├── tests/
├── conf/
└── pyproject.toml
```

---

## 3. Module Boundaries and Rationale

### 3.1 `api/` — FastAPI Application

The `api/` directory is a separate top-level Python package (or sub-package under
`nightfall_photo_ingress`) that contains only the HTTP boundary layer. It does not
contain domain logic.

**Layering rule:** `api/` imports from `src/nightfall_photo_ingress/` (domain and
registry). Domain modules never import from `api/`. This preserves the existing
architecture's clean inward dependency direction.

**Subdirectories:**

| Directory    | Purpose |
|-------------|---------|
| `routers/`  | FastAPI router modules, one per resource group. Handles path/query validation, auth dependency injection, rate limit dependency injection. |
| `services/` | Application-level service objects. Translates validated HTTP requests into domain operations. Contains no repository calls; delegates to existing domain services. |
| `schemas/`  | Pydantic models for request bodies and JSON responses. No domain objects cross the API boundary directly. |
| `app.py`    | Application factory function and FastAPI lifespan context (connect registry, bind startup/shutdown hooks). |
| `auth.py`   | Bearer token validation dependency. Reads token from `X-Authorization` header, compares against config value. |
| `rate_limit.py` | Sliding window rate-limit dependency. In-process for Phase 1; upgradeable to Redis-backed in Phase 2. |
| `audit_hook.py` | Decorator/context manager that ensures audit log write precedes state mutation commit. |

### 3.2 `webui/` — SvelteKit SPA

The `webui/` directory is a fully self-contained Node.js project (SvelteKit). It builds
to static assets (`webui/build/`) which are served by the FastAPI application at the
`/` URL prefix.

**Why a top-level directory, not nested under `api/`:** The SvelteKit project has its
own `package.json`, `node_modules`, and build toolchain. Keeping it at the root of
the repository makes the build pipeline explicit and avoids confusion between Python
dependencies and Node.js dependencies.

**Build output:** `webui/build/` (gitignored). The FastAPI application mounts this
directory as a static files mount at `/`. The SvelteKit build target is
`@sveltejs/adapter-static` with a single-file fallback for SPA client-side routing.

### 3.3 `design/` Extensions

New design documents are added alongside existing architecture documents. No existing
documents are modified. New files are:

- `webui-architecture-phase1.md` — SvelteKit structure, stores, API layer, layout system.
- `webui-design-tokens-phase1.md` — Dark-mode design token catalogue.
- `webui-component-mapping-phase1.md` — Mockup analysis, component mapping, interaction logic.

### 3.4 `planning/` Extensions

New planning documents capture decisions and integration plans. No existing planning
documents are modified.

---

## 4. Deployment Topology Inside LXC Container

### 4.1 Service Layout

The `photo-ingress` LXC container will host three systemd services after the extension:

| Service unit                  | Process              | Listens on           |
|-------------------------------|----------------------|----------------------|
| `nightfall-photo-ingress.service`       | Python CLI poll      | — (background timer) |
| `nightfall-photo-ingress-trash.service` | Python CLI trash job | — (background timer) |
| `nightfall-photo-ingress-api.service`   | Uvicorn + FastAPI    | `127.0.0.1:8000` (Phase 1) |

The API service depends on the registry database being available. It does not depend on
the poll or trash services.

### 4.2 Static Asset Serving

The SvelteKit build output (`webui/build/`) is owned by the `nightfall-photo-ingress-api` service.
FastAPI serves the built static files at the root URL. No separate web server (Nginx,
Caddy) is required in Phase 1.

In Phase 2, a reverse proxy (Nginx or Caddy) may be placed in front for:
- TLS termination.
- Serving static assets with cache headers.
- LAN exposure hardening.

### 4.3 Build and Deploy Flow

```
Development machine:
  1. cd webui && npm run build        → produces webui/build/
  2. pip install -e .                 → installs photo-ingress-core + api

LXC container (deploy target):
  3. rsync webui/build/ → container:/opt/photo-ingress/webui/build/
  4. pip install -e .    → ensures api deps present
  5. systemctl restart nightfall-photo-ingress-api
```

For initial deployment and ongoing operator use, static assets are considered a
deployment artifact — they are not served from a separate Node.js process at runtime.

### 4.4 Registry Access

The FastAPI application opens the SQLite registry database in read-write mode using the
same database path configured in `photo-ingress.conf`. The existing registry module
provides the connection factory. A connection-per-request or connection-pool-of-one
model is used; SQLite WAL mode supports concurrent reads from the CLI and the API.

### 4.5 No Docker Compose

Docker Compose is not used. The LXC container already provides process isolation.
systemd unit files replace Docker Compose's service orchestration role for this project.

---

## 5. Development Workflow (Local)

When developing locally (outside LXC):

1. Run `uvicorn api.app:app --reload --port 8000` from the repo root.
2. Run `cd webui && npm run dev` to start the Vite dev server (default port 5173).
3. The Vite dev server proxies `/api/` requests to `localhost:8000` via `vite.config.js`
   proxy configuration.
4. The browser loads the SvelteKit SPA from Vite; API calls reach the Python server.

This two-process dev setup is standard for SvelteKit + backend combinations and requires
no additional tooling.

---

## 6. gitignore Additions

The following paths should be added to `.gitignore`:

```
webui/node_modules/
webui/.svelte-kit/
webui/build/
api/__pycache__/
```

---

## 7. Dependency Manifests

**Python side (`pyproject.toml` additions):**

```
fastapi
uvicorn[standard]
```

The `[standard]` extra adds `uvloop` and `httptools` for improved performance on Linux.

**Node.js side (`webui/package.json` devDependencies):**

```
@sveltejs/kit
@sveltejs/adapter-static
svelte
vite
@sveltejs/vite-plugin-svelte
```

No runtime Node.js process is required in production. `node_modules` and the build
toolchain are development-only.
