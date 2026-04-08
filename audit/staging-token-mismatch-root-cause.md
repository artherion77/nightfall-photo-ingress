# Staging Dashboard "Something went wrong — Internal error" Root Cause Analysis

**Date:** 2026-04-07
**Analyst:** Automated (GitHub Copilot)
**Scope:** Post-Issue-#17 dashboard failure in staging-photo-ingress
**Related:** https://github.com/artherion77/nightfall-photo-ingress/issues/17

---

## 1. Symptom Analysis

After manual recovery of Issue #17 (SPA build artifacts synced from dev container
to staging), the dashboard at http://192.168.200.242:8000 exhibits:

- Menu bar: renders correctly, navigation links clickable
- Footer: renders correctly, shows version and status badges
- Middle pane: **"Something went wrong — Internal error"**
- No JavaScript console errors related to static asset loading

The layout shell loads because `+layout.svelte` renders `AppHeader` and `AppFooter`
independently of page data. The middle pane fails because `+page.js` executes a
`Promise.all()` of 4 API calls during SvelteKit page load. If any call throws,
the entire page load fails and `+error.svelte` renders the error message.

The 4 API calls made on dashboard load:
- `GET /api/v1/staging?limit=20`
- `GET /api/v1/audit-log?limit=5`
- `GET /api/v1/config/effective`
- `GET /api/v1/health`

---

## 2. Hypothesis Tree

```
Dashboard renders "Something went wrong — Internal error"
├── H1: API service not running (connection refused, all calls fail)
│   ├── H1a: No systemd unit for API/uvicorn in staging
│   └── H1b: API crashed and was not restarted
├── H2: Bearer token mismatch (all calls return 401)
│   ├── H2a: Frontend build-time token differs from backend config
│   ├── H2b: [web] section missing from staging config (api_token defaults to "")
│   └── H2c: Token manually patched in container but not in config template
├── H3: CORS blocking (OPTIONS preflight rejected)
│   └── H3a: cors_allowed_origins doesn't include browser origin
├── H4: Backend internal error (500 on startup or request handling)
│   └── H4a: Registry DB missing or corrupt
└── H5: Stale build artifacts (wrong API paths)
    └── H5a: Old SPA build calling different API routes
```

---

## 3. Evidence Collection and Hypothesis Validation

### H1: API Service Not Running — CONFIRMED (Primary Root Cause)

**Evidence:**
- `ps aux` in staging container shows NO uvicorn/python process for the API
- No systemd unit file exists for the API: `nightfall-photo-ingress-api.service`
  is NOT installed in the staging container
- The only nightfall systemd units are:
  - `nightfall-photo-ingress.service` — one-shot poll cycle (CLI ingress)
  - `nightfall-photo-ingress.timer` — timer trigger for poll
  - `nightfall-photo-ingress-trash.service` — trash processor
  - `nightfall-photo-ingress-trash.path` — path watcher for trash
- `stagingctl install` does NOT install an API systemd service
- `stagingctl install` does NOT start uvicorn
- After manually starting uvicorn (`cd /opt && uvicorn api.app:app --host 0.0.0.0 --port 8000`),
  all 4 API endpoints return HTTP 200 with correct data
- The API process exits silently when the parent `lxc exec` session ends

**Conclusion:** The API was never started as a persistent service. The SPA tried
to reach a non-existent backend, all `fetch()` calls failed with connection refused,
`apiFetch()` retried 3 times each (with exponential backoff), then threw `ApiError`,
which caused SvelteKit to render `+error.svelte`.

### H2: Bearer Token Mismatch — REJECTED (Not Root Cause)

**Evidence:**
- Frontend build-time token: `PUBLIC_API_TOKEN=inspect-chunk3-token`
  (verified in `webui/.env`, `_app/env.js`, and minified JS chunk)
- Backend runtime token: `api_token = inspect-chunk3-token`
  (verified in `/etc/nightfall/photo-ingress.conf` inside staging container)
- Direct API test with token: `Authorization: Bearer inspect-chunk3-token` returns HTTP 200
- Direct API test without token: returns HTTP 401 "Missing Authorization header"
- Direct API test with wrong token: returns HTTP 401 "Invalid token"
- `hmac.compare_digest()` in `auth.py` performs constant-time comparison — correct

**However — architectural vulnerability confirmed:**
The staging config template (`staging/container/photo-ingress.conf`) does NOT
contain a `[web]` section. The `[web]` section with `api_token` was added
manually to the running container. Any `stagingctl install` or `stagingctl reset`
will overwrite the running config, removing the `[web]` section and causing
`WebConfig.api_token` to default to `""`. In that state, `verify_api_token()`
raises 401 "API token not configured" for every request.

This is a latent time bomb: the token works now but will break on next reset.

### H3: CORS Blocking — REJECTED

**Evidence:**
- `cors_allowed_origins = http://192.168.200.242:8000` in staging config
- Browser accesses dashboard at `http://192.168.200.242:8000`
- SPA and API are served from the same origin — no CORS preflight needed
- CORS middleware handles cross-origin cases correctly

### H4: Backend Internal Error — REJECTED

**Evidence:**
- Lifespan test executed successfully: config loads, registry DB initializes
- All API endpoints return correct JSON responses when uvicorn is running
- No 500 errors observed in trace-level uvicorn logs

### H5: Stale Build Artifacts — REJECTED

**Evidence:**
- SPA build artifacts were synced from dev container (Issue #17 fix)
- `_app/` directory present with correct JS chunks
- API routes in built JS match backend route definitions

---

## 4. Root Cause Chain

```
                    ┌───────────────────────────────┐
                    │  stagingctl install            │
                    │  - installs wheel + pip deps   │
                    │  - pushes config (NO [web])    │
                    │  - enables timer + trash path  │
                    │  - does NOT install API unit   │
                    │  - does NOT start uvicorn      │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────▼────────────────┐
                    │  Container running with:       │
                    │  - poll timer: enabled          │
                    │  - trash watcher: enabled       │
                    │  - API (uvicorn): NOT RUNNING   │
                    │  - SPA served by: NOTHING       │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────▼────────────────┐
                    │  Manual workaround applied:    │
                    │  - [web] added to config       │
                    │  - uvicorn started manually    │
                    │  - SPA assets synced (Issue#17)│
                    │  BUT: not persistent           │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────▼────────────────┐
                    │  After session/reboot:          │
                    │  - uvicorn dies with session    │
                    │  - config reset removes [web]   │
                    │  - browser requests → refused   │
                    │  - "Something went wrong"       │
                    └───────────────────────────────┘
```

---

## 5. Most Probable Root Cause

**Primary:** The staging deployment pipeline (`stagingctl`) does not install or
manage a systemd service for the FastAPI/uvicorn web control plane. The API was
only available when manually started in a foreground session, which terminates
when the `lxc exec` parent process exits.

**Secondary (Latent):** The staging config template lacks the `[web]` section.
Even if a systemd service existed, the API would reject all authenticated requests
because `api_token` defaults to `""` when `[web]` is absent, causing
`verify_api_token()` to raise HTTP 401 "API token not configured".

**Tertiary (Architectural):** Token injection is split across two unrelated
mechanisms with no synchronization:
- Frontend: `PUBLIC_API_TOKEN` in `webui/.env` → baked into JS at build time
- Backend: `[web] api_token` in `photo-ingress.conf` → read at uvicorn startup
These are managed by different scripts (devctl vs stagingctl) with no cross-check.

---

## 6. Why This Issue Surfaced Only After Issue #17 Fix

Before Issue #17 was fixed, the SPA HTML shell contained no JavaScript bundles.
The browser loaded a blank page with `<div id='app'>dashboard-shell</div>` and
no JS executed. The page never tried to call any API endpoints.

After Issue #17 was fixed (real SPA assets synced), the JavaScript loaded
correctly and SvelteKit initialized. On page mount, `+page.js` executed
`Promise.all()` with 4 API calls. These all failed because:
1. uvicorn was not running (primary), OR
2. the `[web]` section was missing so tokens mismatched (secondary)

The error was always latent but was masked by the stale SPA build artifacts.

---

## 7. Impact Assessment

| Dimension            | Impact |
|----------------------|--------|
| User-facing          | Complete dashboard failure — no content rendered in main area |
| Data integrity       | None — read-only API calls, no mutations attempted |
| Security             | Low — token is not exposed; 401 responses are correct behavior |
| Recurrence risk      | **High** — any `stagingctl reset` or `install` will reproduce |
| Blast radius         | Staging only — production uses separate deployment |

---

## 8. Architecture Drift Violations

| Invariant | Status | Detail |
|-----------|--------|--------|
| Token identical across frontend and backend | PASS (currently) | Both use `inspect-chunk3-token` |
| Token injected consistently at build/runtime | VIOLATION | Frontend: build-time env var; Backend: config file. No cross-check. |
| No stale token artifacts in frontend build | PASS | `_app/env.js` contains current token |
| Backend rejects invalid tokens with explicit codes | PASS | Returns 401 with descriptive detail |
| Frontend surfaces backend errors gracefully | PARTIAL | `+error.svelte` shows error but loses specificity (shows "Internal error" not "401 Unauthorized") |
| Dev container and host config do not diverge | VIOLATION | Host config template has no `[web]`; container config was manually patched |
| API service managed by systemd | VIOLATION | No systemd unit exists for the API |
| Config template matches deployed config | VIOLATION | `staging/container/photo-ingress.conf` missing `[web]` section |

---

## 9. Reproduction Steps

1. Run `stagingctl reset` to restore clean snapshot
2. Observe: no uvicorn process running, no API systemd unit
3. Navigate to http://192.168.200.242:8000
4. SPA loads (HTML + JS), menu bar and footer render
5. Middle pane shows "Something went wrong — Internal error"
6. Network tab shows 4 failed fetch requests to `/api/v1/*` (ERR_CONNECTION_REFUSED)

---

## 10. Immediate Mitigation (Applied)

1. Manually started uvicorn: `cd /opt && /opt/ingress/bin/uvicorn api.app:app --host 0.0.0.0 --port 8000`
2. Verified `[web]` section present in running config with matching token
3. Confirmed all 4 API endpoints return HTTP 200 with correct data
4. Dashboard renders correctly

This is NOT persistent and will be lost on container restart.

---

## 11. Fix Recommendations Summary

See `/planning/planned/staging-token-hardening-plan.md` for the complete fix plan.

1. **Quick Win:** Add `[web]` section to `staging/container/photo-ingress.conf` template;
   create and install `nightfall-photo-ingress-api.service` systemd unit
2. **Long-Term:** Token synchronization strategy with build-time validation,
   config template linting, and E2E regression tests
3. **Architectural:** Single source of truth for token, injected from config into both
   frontend build and backend runtime
