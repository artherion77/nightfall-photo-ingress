# Staging Token Hardening — Implementation Roadmap

**Date:** 2026-04-07  
**Revision:** 2 (re-engineered from design documents)  
**Status:** planned  
**Design Authority:**
- `design/infra/build-governor-design.md` §15 (Token Authority), §16 (Artifact Immutability), §17 (Enforcement)
- `testspecs/e2e-suite-module-01-auth-artifact-staging.md` (E2E Module 1)

**Related RCA:** `audit/staging-token-mismatch-root-cause.md`  
**Related Issue:** https://github.com/artherion77/nightfall-photo-ingress/issues/17

---

## Scope

This roadmap implements the token authority model, artifact immutability
enforcement, and E2E test suite defined in the referenced design documents.

### In Scope

- Config template remediation (invariants T1, T4)
- API systemd service unit (staging health prerequisite)
- stagingctl install integration (deployment contract)
- govctl preflight checks (invariants T1-T4, A5, P1)
- govctl JSONL event extensions (build_fingerprint, artifact_verified, artifact_rejected)
- govctl target manifest updates (§17.5)
- E2E Module 1 test implementation (testspec Cases 1-15)
- govctl target for E2E Module 1 execution

### Explicit Exclusions

- Runtime guardrails (no systemd ExecStartPre validation)
- Manual operational steps (no runbooks, no ad-hoc procedures)
- Ad-hoc fixes (no one-off container edits)
- Token rotation protocol (§15.4 non-goal)
- Secret management integration (§15.4 non-goal)
- Production promotion automation (§16.5 non-goal, future scope)
- Image-based promotion (§16.5 non-goal)

---

## Dependency Graph

```
Chunk 1 (Config Template)
    │
    ├──► Chunk 2 (API Service Unit)
    │        │
    │        ├──► Chunk 3 (stagingctl install integration)
    │        │        │
    │        │        ├──► Chunk 7 (E2E: Staging Health — Cases 12-15)
    │        │        │
    │        │        └──► Chunk 8 (E2E: Auth Handshake — Cases 1-5)
    │        │                 │
    │        │                 └──► Chunk 9 (E2E: Token Consistency — Cases 6-8)
    │        │
    │        └──► Chunk 6 (govctl Manifest Update)
    │
    ├──► Chunk 4 (govctl Preflight: token-source-consistent, config-template-complete)
    │        │
    │        └──► Chunk 6
    │
    └──► Chunk 5 (govctl Preflight: artifact-hash-recorded, artifact-hash-verified)
             │
             ├──► Chunk 6
             │
             └──► Chunk 10 (E2E: Artifact Integrity — Cases 9-11)

Chunk 6 ──► Chunk 11 (govctl target: staging.e2e.module1)

Chunks 7-10 ──► Chunk 11

Chunk 11 ──► Chunk 12 (Final Gate)
```

---

## Chunk 1: Config Template Remediation

**Purpose:** Establish invariant T4 — staging config template contains `[web]`
section with all required keys.

**Dependencies:** None.

**Deliverables:**
1. Updated `staging/container/photo-ingress.conf` with `[web]` section
   containing: `api_token`, `bind_host`, `bind_port`, `cors_allowed_origins`.
2. Token value in `[web] api_token` matches `PUBLIC_API_TOKEN` in `webui/.env`
   (establishes invariant T1 at the source level).

**Acceptance Criteria:**
1. `configparser.ConfigParser()` parses the template without error.
2. `parser.has_section('web')` returns `True`.
3. `parser.get('web', 'api_token')` returns a non-empty string.
4. `parser.get('web', 'bind_host')` returns a non-empty string.
5. `parser.get('web', 'bind_port')` returns a non-empty string.
6. `parser.get('web', 'cors_allowed_origins')` returns a non-empty string.
7. Token value matches `PUBLIC_API_TOKEN` from `webui/.env`.

**Stop-Gate:** Template parses correctly and all six keys are present and
non-empty. Token matches `webui/.env`. Proceed only when verified.

---

## Chunk 2: API Systemd Service Unit

**Purpose:** Provide a persistent API process in staging that survives session
disconnects. Prerequisite for all staging health and auth tests.

**Dependencies:** Chunk 1 (config template must exist with `[web]` section
so the API can load a valid token at startup).

**Deliverables:**
1. `systemd/nightfall-photo-ingress-api.service` — service unit file.
2. `staging/systemd/nightfall-photo-ingress-api.service.d/override.conf` —
   staging-specific override (if needed).

**Acceptance Criteria:**
1. Unit file passes `systemd-analyze verify`.
2. Unit declares `After=network.target`.
3. `ExecStart` invokes uvicorn with the correct module path (`api.app:app`).
4. `Restart=on-failure` is set.
5. `WorkingDirectory` is set to the correct path for module imports.

**Stop-Gate:** Unit file exists, passes static analysis. Proceed only when
verified.

---

## Chunk 3: stagingctl install Integration

**Purpose:** Update `stagingctl install` to deploy the API service unit, push
config, and enable the service. Establishes the staging phase contract (§5.2
of the testspec).

**Dependencies:** Chunk 1 (config template), Chunk 2 (service unit).

**Deliverables:**
1. Updated `dev/bin/stagingctl` `cmd_install()` function:
   - Pushes API service unit to container.
   - Pushes staging override (if applicable).
   - Runs `systemctl daemon-reload`.
   - Runs `systemctl enable --now nightfall-photo-ingress-api.service`.
2. Config template push includes the `[web]` section (already present from
   Chunk 1).

**Acceptance Criteria:**
1. `stagingctl install` completes with exit 0.
2. `lxc exec staging-photo-ingress -- systemctl is-active nightfall-photo-ingress-api`
   returns `active`.
3. `curl -s -H "Authorization: Bearer <token>" http://<staging-host>:8000/api/v1/health`
   returns HTTP 200.
4. `stagingctl install` is idempotent: running it twice produces the same
   end state.

**Stop-Gate:** Fresh `stagingctl install` produces a staging container where
the API is running and responds to authenticated requests. Proceed only when
verified.

---

## Chunk 4: govctl Preflight — Token Authority Checks

**Purpose:** Implement the `token-source-consistent` and
`config-template-complete` preflight checks defined in §17.2 of the build
governor design.

**Dependencies:** Chunk 1 (config template must exist to test against).

**Deliverables:**
1. `token-source-consistent` preflight check implementation in `dev/bin/govctl`.
   - Reads `PUBLIC_API_TOKEN` from `webui/.env`.
   - Reads `api_token` from staging config template `[web]` section.
   - Fails if values differ.
   - Does not emit token values in output (invariant T5).
2. `config-template-complete:<file>` preflight check implementation.
   - Parses the named INI file.
   - Verifies `[web]` section exists.
   - Verifies `api_token` key exists and is non-empty.
   - Does not emit the token value (invariant T5).

**Acceptance Criteria:**
1. `govctl check web.build` passes when tokens match and template is complete.
2. `govctl check web.build` fails with `preflight_failed` JSONL event when
   tokens diverge.
3. `govctl check web.build` fails with `preflight_failed` JSONL event when
   `[web]` section is missing from template.
4. Neither check emits the actual token value in any output stream.

**Stop-Gate:** Both preflight checks pass against the current repo state.
Both correctly fail when given a deliberately broken input. Proceed only when
both positive and negative cases verified.

---

## Chunk 5: govctl Preflight — Artifact Integrity Checks

**Purpose:** Implement the `artifact-hash-recorded` and
`artifact-hash-verified` preflight checks defined in §17.2. Implement the
`build_fingerprint` JSONL event defined in §17.4.

**Dependencies:** Chunk 1 (needed for end-to-end validation only; the
implementation is independent).

**Deliverables:**
1. `build_fingerprint` JSONL event emission after successful `web.build`
   and `backend.build.wheel` targets.
   - Computes SHA-256 of `webui/build/` directory contents (for SPA).
   - Computes SHA-256 of the wheel file in `dist/` (for backend).
   - Emits event with `target`, `sha256`, `artifact_path`, `timestamp`.
2. `artifact-hash-recorded:<target>` preflight check.
   - Reads the current run's JSONL log for a `build_fingerprint` event
     matching the named target.
   - Fails if no matching event found.
3. `artifact-hash-verified:<artifact-path>` preflight check.
   - Computes SHA-256 of the artifact at the given path.
   - Compares against the most recent `build_fingerprint` event for that path.
   - Fails on mismatch.
4. `artifact_verified` and `artifact_rejected` JSONL events emitted during
   verification.

**Acceptance Criteria:**
1. After `govctl run web.build`, the JSONL log contains a `build_fingerprint`
   event for `web.build`.
2. After `govctl run backend.build.wheel`, the JSONL log contains a
   `build_fingerprint` event for `backend.build.wheel`.
3. `artifact-hash-recorded:web.build` passes after `web.build` runs.
4. `artifact-hash-recorded:web.build` fails if `web.build` has not run in
   the current session.
5. `artifact-hash-verified:webui/build/` passes when artifact is unmodified.
6. `artifact-hash-verified:webui/build/` fails (emits `artifact_rejected`)
   when artifact content has changed.

**Stop-Gate:** All six acceptance criteria pass. Both positive and negative
cases verified. Proceed only when confirmed.

---

## Chunk 6: govctl Target Manifest Update

**Purpose:** Update `dev/govctl-targets.yaml` with the new preflight
declarations from §17.5 and add the `staging.e2e.module1` target.

**Dependencies:** Chunk 4 (token authority checks must exist), Chunk 5
(artifact integrity checks must exist).

**Deliverables:**
1. Updated `web.build` target preflight list to include:
   - `token-source-consistent`
   - `config-template-complete:staging/container/photo-ingress.conf`
2. Updated `staging.install` target preflight list to include:
   - `artifact-hash-recorded:web.build`
   - `artifact-hash-recorded:backend.build.wheel`
   - `artifact-hash-verified:webui/build/`
   - `artifact-hash-verified:dist/*.whl`
   - `token-source-consistent`
3. New `staging.e2e.module1` target definition (placeholder command until
   Chunk 11 provides the test suite target).

**Acceptance Criteria:**
1. `govctl list` shows the new preflight entries for `web.build` and
   `staging.install`.
2. `govctl check web.build` runs the new token and template preflights.
3. `govctl check staging.install` runs the new artifact and token preflights.
4. `govctl list` shows `staging.e2e.module1`.
5. Manifest parses without error.

**Stop-Gate:** `govctl check web.build` and `govctl check staging.install`
both pass with all new preflights active. Proceed only when verified.

---

## Chunk 7: E2E Implementation — Staging Health (Cases 12-15)

**Purpose:** Implement testspec Cases 12-15 (staging health tests). These are
the foundation — if staging is not healthy, all other E2E tests are meaningless.

**Dependencies:** Chunk 3 (stagingctl install must produce a working staging
container with API service).

**Deliverables:**
1. `tests/e2e/__init__.py`
2. `tests/e2e/conftest.py` — session fixtures: `base_url`, `api_client`,
   `unauthenticated_client`, `container_config`.
3. `tests/e2e/test_staging_health.py` — implements:
   - Case 12: API systemd service is active.
   - Case 13: All four SPA gateway endpoints return 200.
   - Case 14: SPA static files served correctly.
   - Case 15: Config template sections are complete.

**Acceptance Criteria:**
1. `pytest tests/e2e/test_staging_health.py -v` passes against a freshly
   installed staging container.
2. Each test case maps to exactly one testspec case number (documented in
   docstring or test ID).
3. Test evidence captured per §7.1 of the testspec (HTTP status, URL, timestamp).
4. No token values appear in test output (invariant T5).

**Stop-Gate:** All four tests pass against a clean `stagingctl install`.
Proceed only when verified.

---

## Chunk 8: E2E Implementation — Auth Handshake (Cases 1-5)

**Purpose:** Implement testspec Cases 1-5 (auth handshake tests). Validates
the API authentication boundary defined by invariants T3 and T6.

**Dependencies:** Chunk 3 (staging must be running), Chunk 7 (staging health
must be confirmed first — Cases 12-15 passing is a precondition).

**Deliverables:**
1. `tests/e2e/test_auth_handshake.py` — implements:
   - Case 1: Valid bearer token returns 200.
   - Case 2: Missing Authorization header returns 401.
   - Case 3: Wrong token returns 401.
   - Case 4: Empty api_token in config returns 401.
   - Case 5: Missing [web] section in config returns 401.

**Acceptance Criteria:**
1. Cases 1-3 pass against a correctly configured staging container.
2. Cases 4-5 are validated against a deliberately misconfigured container
   (or via unit-level test with config override).
3. Audit log entries verified for failure cases (Cases 2, 3).
4. No token values appear in test output (invariant T5).

**Stop-Gate:** Cases 1-3 pass against staging. Cases 4-5 verification strategy
confirmed (live or unit-level). Proceed only when verified.

---

## Chunk 9: E2E Implementation — Token Consistency (Cases 6-8)

**Purpose:** Implement testspec Cases 6-8 (token consistency tests). Validates
invariant T1 (single canonical token source) across the build artifact, config
template, and running container.

**Dependencies:** Chunk 8 (auth handshake tests must pass — if auth is broken,
token consistency tests produce misleading results).

**Deliverables:**
1. `tests/e2e/test_token_consistency.py` — implements:
   - Case 6: SPA env.js token matches staging config token.
   - Case 7: webui/.env matches staging config template.
   - Case 8: Running staging API token matches deployed config.
2. Token extraction utilities in `conftest.py` (or helper module):
   - Extract `PUBLIC_API_TOKEN` from built SPA `_app/env.js`.
   - Extract `api_token` from INI config (template and deployed).

**Acceptance Criteria:**
1. All three cases pass against a correctly built and deployed staging.
2. Token values are compared but never emitted in output.
   Redaction format: `<REDACTED:len=N>` (per testspec §7.1).
3. Failure messages identify which source diverged without exposing values.

**Stop-Gate:** All three cases pass. Token redaction verified in output.
Proceed only when verified.

---

## Chunk 10: E2E Implementation — Artifact Integrity (Cases 9-11)

**Purpose:** Implement testspec Cases 9-11 (artifact integrity tests).
Validates invariants A1, A3, A5, P1 (immutable artifacts, no rebuild during
promotion).

**Dependencies:** Chunk 5 (govctl must emit `build_fingerprint` events for
hash comparison).

**Deliverables:**
1. `tests/e2e/test_artifact_integrity.py` — implements:
   - Case 9: SPA build artifact hash matches recorded fingerprint.
   - Case 10: Python wheel hash matches recorded fingerprint.
   - Case 11: Deployed SPA in staging matches build artifact.
2. SHA-256 hashing utility for directory contents and single files.
3. JSONL event parser to extract `build_fingerprint` events.

**Acceptance Criteria:**
1. Case 9 passes when `web.build` was the most recent SPA build.
2. Case 10 passes when `backend.build.wheel` was the most recent wheel build.
3. Case 11 passes after `stagingctl install` deploys unmodified artifacts.
4. Cases 9, 10 fail when artifact content is modified after build (negative
   test).

**Stop-Gate:** All three positive cases pass. At least one negative case
(modified artifact) demonstrated to fail. Proceed only when verified.

---

## Chunk 11: govctl Target — staging.e2e.module1

**Purpose:** Wire the E2E Module 1 test suite into the govctl target framework
so it can be invoked via `govctl run staging.e2e.module1`.

**Dependencies:** Chunks 7-10 (all E2E test files must exist), Chunk 6
(manifest must have placeholder target).

**Deliverables:**
1. Updated `staging.e2e.module1` target in `dev/govctl-targets.yaml`:
   - Command: `pytest tests/e2e/ -v --tb=short`
   - Requires: `staging.install`
   - Preflight: `container-running:staging-photo-ingress`
   - Timeout: 120s
2. Updated `staging.full` group to include `staging.e2e.module1` after
   `staging.smoke`.

**Acceptance Criteria:**
1. `govctl run staging.e2e.module1` executes all Module 1 tests.
2. `govctl run staging.e2e.module1 --json` produces JSONL events for the
   target (started, passed/failed).
3. `govctl run staging.full` includes the E2E module in execution order
   after `staging.smoke`.
4. Preflight `container-running:staging-photo-ingress` prevents execution
   when container is stopped.

**Stop-Gate:** `govctl run staging.e2e.module1` passes. JSONL output is
well-formed. Proceed only when verified.

---

## Chunk 12: Final Gate

**Purpose:** End-to-end validation of the full hardening chain. Proves that
the final guarantees hold.

**Dependencies:** All previous chunks (1-11).

**Deliverables:**
1. Evidence log of a full `govctl run staging.full` execution.
2. Verification report confirming the three final guarantees.

**Acceptance Criteria:**

Guarantee 1 — No token drift:
1. `govctl check web.build` passes `token-source-consistent`.
2. E2E Cases 6, 7, 8 all pass (token consistency across source, artifact,
   and running container).
3. Deliberate token divergence (edit `webui/.env` only) causes
   `token-source-consistent` preflight to fail and block `web.build`.

Guarantee 2 — No rebuild during promotion:
1. `govctl run web.build` records `build_fingerprint` event.
2. `govctl run staging.install` verifies artifact hash via
   `artifact-hash-verified` preflight.
3. Deliberate artifact modification after build causes `staging.install`
   to be refused with `artifact_rejected` event.

Guarantee 3 — Staging == production artifact integrity:
1. E2E Case 11 passes (deployed SPA byte-identical to build output).
2. E2E Case 10 passes (deployed wheel byte-identical to build output).
3. `build_fingerprint` SHA-256 from build phase matches
   `artifact_verified` SHA-256 from deploy phase in the JSONL log.

**Stop-Gate:** All three guarantees demonstrated with both positive (correct
state) and negative (deliberately broken state) evidence. Roadmap is complete.

---

## Execution Summary

| Chunk | Title | Depends On | Invariants |
|-------|-------|------------|------------|
| 1 | Config Template Remediation | — | T1, T4 |
| 2 | API Systemd Service Unit | 1 | — |
| 3 | stagingctl install Integration | 1, 2 | — |
| 4 | govctl Preflight: Token Authority | 1 | T1, T2, T3, T4, T5 |
| 5 | govctl Preflight: Artifact Integrity | 1 | A5, P1 |
| 6 | govctl Target Manifest Update | 4, 5 | — |
| 7 | E2E: Staging Health (Cases 12-15) | 3 | T4 |
| 8 | E2E: Auth Handshake (Cases 1-5) | 3, 7 | T3, T6 |
| 9 | E2E: Token Consistency (Cases 6-8) | 8 | T1, T2, T3 |
| 10 | E2E: Artifact Integrity (Cases 9-11) | 5 | A1, A3, A5, P1 |
| 11 | govctl Target: staging.e2e.module1 | 6, 7-10 | — |
| 12 | Final Gate | 1-11 | All |

Parallel execution paths:
- Chunks 4, 5 can execute in parallel with Chunks 2, 3.
- Chunks 7, 10 can execute in parallel (different test categories, independent
  dependencies).
- Chunks 8, 9 are sequential (auth before consistency).
