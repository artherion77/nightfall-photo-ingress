# E2E Suite Module 1: Auth, Artifact Integrity, and Staging Health

## 1. Purpose

This document defines the first end-to-end test module for the
nightfall-photo-ingress deployment pipeline. Module 1 covers:

1. API authentication handshake correctness.
2. Token consistency between the SPA build artifact and backend configuration.
3. Build artifact integrity from dev container through staging deployment.
4. Staging container health after a fresh `stagingctl install`.

The module answers one operational question:

After a clean `stagingctl install`, is the staging deployment functional and
internally consistent, with no token divergence, no artifact drift, and no
missing services?

This is a specification only. It intentionally does not include test code.

---

## 2. Module Boundaries

### In Scope

1. Bearer token authentication between the SPA frontend and the FastAPI backend.
2. Token consistency: the value baked into the SPA at build time matches the
   value in the staging backend configuration.
3. Artifact integrity: the SPA build directory and deployed SPA files are
   byte-identical to build outputs, and the Python wheel build artifact hash
   matches its recorded build fingerprint.
4. Staging container health: the API process is running, responsive, and
   serving authenticated requests.
5. Config template completeness: the staging config template contains all
   required sections and keys.

### Out Of Scope

1. Ingest pipeline behavior (covered by Module 2+).
2. Registry database correctness (covered by registry integration suite).
3. OneDrive Graph API interaction.
4. Token rotation procedures.
5. Network-level security (TLS, firewall rules).
6. Performance or load testing.
7. Multi-user or role-based access (single bearer token model only).
8. Byte-level equivalence between installed backend site-packages in staging
   and wheel file contents after `pip install` extraction.

---

## 3. Invariants Under Test

Each test case in this module validates one or more of the following invariants.
These invariants are defined in the build governor design (§15, §16, §17).

| ID | Invariant |
|----|-----------|
| T1 | Exactly one canonical token definition exists per environment. |
| T2 | The frontend consumes the token via `PUBLIC_API_TOKEN` in `webui/.env`, baked at build time. |
| T3 | The backend consumes the token via `[web] api_token` in the INI config file. |
| T4 | The staging config template contains a `[web]` section with a non-empty `api_token`. |
| T5 | Token values do not appear in build logs or JSONL events. |
| T6 | Token comparison uses constant-time comparison. |
| A1 | The SPA build is an immutable artifact. |
| A3 | Staging and production consume the same build artifact (no separate staging build). |
| A5 | Artifact identity is established by SHA-256 content hash. |
| P1 | Promotion never triggers a rebuild. |

---

## 4. Test Taxonomy

### 4.1 Auth Handshake Tests

These tests validate correct authentication behavior at the API boundary.

#### Case 1: Valid bearer token returns 200

Environment: Staging container after `stagingctl install`.

Preconditions:
1. API process is running (`nightfall-photo-ingress-api.service` active).
2. Staging config contains `[web] api_token` with a non-empty value.

Action:
1. Send `GET /api/v1/health` with `Authorization: Bearer <staging-token>`.

Expected outcome:
1. HTTP 200 with JSON health payload.
2. No audit_log entry for auth failure.

Invariants validated: T3, T6.

#### Case 2: Missing Authorization header returns 401

Preconditions: Same as Case 1.

Action:
1. Send `GET /api/v1/health` with no Authorization header.

Expected outcome:
1. HTTP 401.
2. Response detail: "Missing Authorization header".
3. Audit log contains an auth-failure row with `detail` matching the response.

Invariants validated: T3.

#### Case 3: Wrong token returns 401

Preconditions: Same as Case 1.

Action:
1. Send `GET /api/v1/health` with `Authorization: Bearer wrong-token-value`.

Expected outcome:
1. HTTP 401.
2. Response detail: "Invalid token".
3. Audit log contains an auth-failure row.
4. Response timing is indistinguishable from Case 2 (constant-time comparison).

Invariants validated: T3, T6.

#### Case 4: Empty api_token in config returns 401

Preconditions:
1. Deterministic misconfiguration fixture is active for this case.
2. Fixture config sets `[web] api_token` to empty string `""`.

Action:
1. Send `GET /api/v1/health` with any bearer token.

Expected outcome:
1. HTTP 401.
2. Response detail: "API token not configured".

Invariants validated: T3, T4.

#### Case 5: Missing [web] section in config returns 401

Preconditions:
1. Deterministic misconfiguration fixture is active for this case.
2. Fixture config omits the `[web]` section entirely.

Action:
1. Send `GET /api/v1/health` with any bearer token.

Expected outcome:
1. HTTP 401.
2. Response detail: "API token not configured".
3. `WebConfig.api_token` defaults to `""`.

Invariants validated: T4.

Normative execution rule for Cases 4-5:
1. Cases 4 and 5 MUST run using a deterministic config-fixture strategy, not
   by mutating a live shared staging container.
2. The fixture input files for these cases MUST be versioned test artifacts.
3. This rule is required for audit safety: each run is reproducible from the
   same committed inputs and does not depend on mutable container state.

### 4.2 Token Consistency Tests

These tests validate that the frontend and backend agree on the token value.

#### Case 6: SPA env.js token matches staging config token

Preconditions:
1. `web.build` has been executed (SPA artifact exists).
2. Staging config template exists with `[web] api_token`.

Action:
1. Extract `PUBLIC_API_TOKEN` from the built SPA (`webui/build/_app/env.js`).
2. Extract `api_token` from `staging/container/photo-ingress.conf` `[web]` section.
3. Compare values.

Expected outcome:
1. Values are identical.

Failure signal:
1. Token divergence between frontend artifact and backend config template.
2. This is a build-time defect: the template and `webui/.env` are out of sync.

Invariants validated: T1, T2, T3.

#### Case 7: webui/.env matches staging config template

Preconditions:
1. `webui/.env` exists with `PUBLIC_API_TOKEN` defined.
2. `staging/container/photo-ingress.conf` exists with `[web] api_token` defined.

Action:
1. Read `PUBLIC_API_TOKEN` from `webui/.env`.
2. Read `api_token` from `staging/container/photo-ingress.conf`.
3. Compare values.

Expected outcome:
1. Values are identical.

Failure signal:
1. Source-level divergence. Either file was edited independently.

Invariants validated: T1.

#### Case 8: Running staging API token matches deployed config

Preconditions:
1. `stagingctl install` has completed.
2. API process is running in the staging container.

Action:
1. Read `api_token` from `/etc/nightfall/photo-ingress.conf` inside the staging container.
2. Send an authenticated request using that token.

Expected outcome:
1. HTTP 200 (token extracted from the file is accepted by the running process).

Failure signal:
1. Deployment drift: the file on disk differs from what the process loaded at
   startup (process was not restarted after config change).

Invariants validated: T1, T3.

### 4.3 Artifact Integrity Tests

These tests validate that build artifacts are not modified between build and
deployment.

#### Case 9: SPA build artifact hash matches recorded fingerprint

Preconditions:
1. `web.build` completed and a `build_fingerprint` JSONL event was recorded.
2. `webui/build/` directory exists.

Action:
1. Compute SHA-256 of the `webui/build/` directory contents.
2. Compare against the `sha256` field in the `build_fingerprint` event.

Expected outcome:
1. Hashes match.

Failure signal:
1. Artifact was modified after build (manual edit, partial rebuild, stale cache).

Invariants validated: A1, A5.

#### Case 10: Python wheel hash matches recorded fingerprint

Preconditions:
1. `backend.build.wheel` completed and a `build_fingerprint` JSONL event was recorded.
2. Wheel file exists in `dist/`.

Action:
1. Compute SHA-256 of the wheel file.
2. Compare against the recorded fingerprint.

Expected outcome:
1. Hashes match.

Failure signal:
1. Wheel was rebuilt, replaced, or corrupted after the fingerprint was recorded.

Invariants validated: A1, A5.

Scope note for Case 10:
1. This case guarantees integrity of the wheel build artifact recorded at build
   time.
2. This case does not guarantee byte-for-byte equivalence of installed backend
   files after wheel installation in staging.

#### Case 11: Deployed SPA in staging matches build artifact

Preconditions:
1. `stagingctl install` has completed.
2. SPA files exist in the staging container's static file directory.

Action:
1. Compute SHA-256 of the SPA files in the staging container.
2. Compare against the SHA-256 of the source `webui/build/` directory.

Expected outcome:
1. Hashes match: the staging deployment is byte-identical to the build output.

Failure signal:
1. `stagingctl install` modified the artifact during deployment.
2. A separate staging-specific build was run.

Invariants validated: A1, A3, P1.

### 4.4 Staging Health Tests

These tests validate that the staging container is functional after a fresh
deployment.

#### Case 12: API systemd service is active

Preconditions:
1. `stagingctl install` has completed.

Action:
1. Query `systemctl is-active nightfall-photo-ingress-api.service` inside the
   staging container.

Expected outcome:
1. Output: `active`.

Failure signal:
1. Service unit not installed.
2. Service failed to start (missing dependency, config error, port conflict).

#### Case 13: All four SPA gateway endpoints return 200

Preconditions:
1. API process is running and authenticated.

Action:
1. Resolve the endpoint list from the canonical endpoint set defined in this
   section (Table: Case 13 canonical endpoint set).
2. Send authenticated requests to each endpoint in that set.

Expected outcome:
1. All four return HTTP 200 with valid JSON.

Failure signal:
1. Any single endpoint failure causes the SPA to render `+error.svelte`
   ("Something went wrong — Internal error") because `+page.js` uses
   `Promise.all()`.
2. This test detects the exact failure mode observed in the staging RCA.

Case 13 canonical endpoint set (authoritative for this specification):

| Method | Path |
|--------|------|
| GET | /api/v1/staging |
| GET | /api/v1/audit/log |
| GET | /api/v1/config/effective |
| GET | /api/v1/health |

Canonicalization rule:
1. This table is the single source of truth for Module 1 gateway endpoint
   paths.
2. Module 1 tests MUST derive their endpoint list from this table and MUST NOT
   duplicate endpoint literals elsewhere in the suite specification.
3. The path `/api/v1/audit-log` is non-canonical for Module 1 and must be
   treated as documentation drift unless this table is explicitly revised.

#### Case 14: SPA static files are served correctly

Preconditions:
1. API process is running.
2. SPA build was deployed correctly.

Action:
1. Send `GET /` (unauthenticated — static file serving does not require auth).

Expected outcome:
1. HTTP 200 with HTML content (SPA `200.html` fallback).

Failure signal:
1. `SPAStaticFiles` mount is not configured.
2. SPA build was not deployed to the correct directory.

#### Case 15: Config template sections are complete

Preconditions:
1. `staging/container/photo-ingress.conf` exists in the repository.

Action:
1. Parse the config template as INI.
2. Verify that the following sections exist: `[general]`, `[onedrive]`,
   `[paths]`, `[logging]`, `[web]`.
3. Verify that `[web]` contains: `api_token` (non-empty), `bind_host`,
   `bind_port`, `cors_allowed_origins`.

Expected outcome:
1. All sections present. All keys present with non-empty values.

Failure signal:
1. Template regression: a commit removed or broke the `[web]` section.
2. This is the root cause of the original staging auth failure.

---

## 5. Environment Contract

This section defines the contract between build artifacts, staging deployment,
and production promotion.

### 5.1 Build Phase Contract

| Property | Guarantee |
|----------|-----------|
| SPA build runs in the dev container only | No staging-specific or production-specific SPA build exists |
| Token is baked into the SPA at build time | The value of `PUBLIC_API_TOKEN` at build time is final and immutable |
| Wheel is built on the host from the working tree | `python -m build --wheel` in the repo root |
| Build fingerprints are recorded in JSONL | SHA-256 of each artifact is emitted as a `build_fingerprint` event |

### 5.2 Staging Phase Contract

| Property | Guarantee |
|----------|-----------|
| `stagingctl install` deploys the pre-built SPA artifact | No rebuild occurs during deployment |
| `stagingctl install` deploys the pre-built wheel | `pip install` installs the existing wheel file |
| Config template is pushed from the repository | `staging/container/photo-ingress.conf` is the source of truth |
| API service is enabled and started | `nightfall-photo-ingress-api.service` is active after install |
| Artifact hashes are verified before deployment | Mismatch between recorded and actual hashes blocks deployment |

### 5.3 Production Phase Contract (Future)

| Property | Guarantee |
|----------|-----------|
| Promotion deploys the same artifacts validated in staging | No rebuild, no re-bake, no content modification |
| Promotion requires a passing staging smoke suite | A failed smoke invalidates the artifact's promotion eligibility |
| Config uses a production-specific INI file with the same schema | Schema is identical; values differ (token, bind_host, cors) |

---

## 6. Failure Semantics

### 6.1 Hard Failures (Promotion-Blocking)

A hard failure means the deployment is broken and must not be promoted.

| Test Case | Failure Type | Blocking Reason |
|-----------|-------------|-----------------|
| Case 2, 3, 4, 5 | Auth handshake rejection with correct token | Token misconfiguration or code defect |
| Case 6, 7 | Token divergence between frontend and backend sources | Source-level inconsistency |
| Case 8 | Running API rejects its own config token | Deployment drift or stale process |
| Case 9, 10 | Build artifact hash mismatch | Artifact integrity violation |
| Case 11 | Deployed artifact differs from build output | Deployment corruption |
| Case 12 | API service not active | Service installation failure |
| Case 13 | Any gateway endpoint returns non-200 | SPA will fail to render |
| Case 15 | Config template missing required sections/keys | Template regression |

### 6.2 Soft Failures (Warning, Non-Blocking)

| Test Case | Failure Type | Reason Non-Blocking |
|-----------|-------------|---------------------|
| Case 14 | Static file serving failure (unauthenticated) | May indicate SPAStaticFiles misconfiguration but does not affect authenticated API functionality |

### 6.3 Failure Cascade

If any Case 1-5 (auth handshake) fails, Cases 6-8 (token consistency) and
Case 13 (gateway endpoints) are expected to also fail. The test runner should
execute all cases regardless to maximize diagnostic evidence, but the root cause
is identified by the earliest failing case.

---

## 7. Observability Requirements

Each test case must capture enough evidence for post-mortem analysis.

### 7.1 Minimum Evidence Per Test

1. HTTP status code and response body (or first 1024 bytes).
2. Request URL and method.
3. Timestamp of request and response.
4. Relevant config values (redacted: token values replaced with
   `<REDACTED:len=N>` showing length only).
5. SHA-256 hashes where artifact integrity is under test.

### 7.2 Aggregate Evidence Per Run

1. Full test case results (pass/fail/skip per case).
2. Staging container `systemctl` status for the API service.
3. Staging container config file hash (not contents — to avoid token exposure).
4. Build fingerprint JSONL events from the preceding build phase.
5. Staging smoke JSONL events (if `staging.smoke` was run in the same
   govctl invocation).

---

## 8. Extensibility

### 8.1 Future Module Plugin Points

Module 1 covers auth, artifact integrity, and staging health. Future modules
extend coverage:

| Module | Scope | Dependency on Module 1 |
|--------|-------|------------------------|
| Module 2 | Ingest pipeline correctness | Requires Module 1 staging health (Case 12, 13) to pass |
| Module 3 | Metrics pipeline integrity | Independent of Module 1 |
| Module 4 | Config drift detection across environments | Extends Module 1 token consistency (Case 6-8) |
| Module 5 | Upgrade/rollback resilience | Requires Module 1 artifact integrity (Case 9-11) to pass |

### 8.2 Module Interface Contract

Each module declares:

1. **Precondition modules** — which prior modules must pass before this module
   runs. Module 1 has no preconditions (it is the foundation).
2. **Invariants under test** — references to the build governor design
   invariant table (§15, §16, §17).
3. **Failure semantics** — hard vs soft, with explicit blocking consequences.
4. **Evidence schema** — what evidence is collected and in what format.

### 8.3 Integration With govctl

Module 1 test execution maps to the govctl target framework:

| govctl Target | Module 1 Coverage |
|---------------|-------------------|
| `staging.install` | Precondition: successful deployment |
| `staging.smoke` | Cases 1, 12, 13, 14 (health and auth subset) |
| `staging.smoke-live` | Cases 6, 7, 8 (token consistency requiring live container) |

A future `staging.e2e.module1` target could run the full Module 1 suite with
declared dependency on `staging.install`.
