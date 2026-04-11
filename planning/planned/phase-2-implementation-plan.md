# Web Control Plane — Phase 2 Implementation Plan

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Chunked Execution Plan (C1–C8)

### C1 — Reverse Proxy Baseline (Caddy)

Goal:
- Introduce Caddy as the required ingress boundary for Web Control Plane LAN exposure.

Inputs:
- ../../design/web/architecture.md (Phase 2 reverse-proxy sections)
- ../../design/web/design-decisions.md (Phase 2 mandatory posture)
- ../planned/phase-2-architecture-roadmap.md

Preconditions:
- Phase 1 baseline stable.
- Phase 1.5 gate complete for Phase 2 progression.

Deliverables:
- Documented Caddy topology, route map, and service boundary.
- Operational checklist for Caddy process lifecycle and route verification.
- Phase-2 staging infra baseline contract documented in ../../design/infra/staging-invariants.md.
- C1.1 stagingctl rewrite: container-local runtime tmpfs with host-persistent evidence/log mounts.

Validation steps:
1. Verify documented route ownership for static and /api paths.
2. Verify Uvicorn remains localhost-bound in documented topology.
3. Verify runtime tmpfs surfaces are container-local.
4. Verify persistent evidence/log paths remain host-mounted and stable.
5. Verify future media-library read-only host mount is reserved in infra policy.

Stop-gates:
1. Do not proceed if topology documentation conflicts with architecture.md.
2. Do not proceed if ingress boundary ownership is ambiguous.
3. Do not proceed if runtime tmp/cache uses host-backed tmpfs or host-backed `/tmp`, `/var/tmp`, or cache devices.
4. Do not proceed if persistent host-mounted evidence/log paths are removed from the Phase-2 infra model.

Validation evidence:
1. Route ownership and ingress topology are documented in `../../design/web/architecture.md`:
	- `## 3. Reverse Proxy`
	- `### 3.2 Proxy Topology (Phase 2)`
2. Localhost-only application binding is documented in `../../design/web/architecture.md`:
	- `### 3.3 Uvicorn Binding Change for Phase 2`
3. Mandatory gate checklist is documented in `../../design/web/architecture.md`:
	- `### 3.6 Phase 2 Mandatory Reverse Proxy Checklist`
4. Corrected Phase-2 staging infra baseline is documented in `../../design/infra/staging-invariants.md`.
5. C1.1 stagingctl and staging contracts are implemented with runtime tmpfs local to container and host-persistent evidence/log mounts:
	- `../../dev/bin/stagingctl`
	- `../../tests/staging/test_stagingctl_policy_contracts.py`
	- `../../staging/README.md`

### C2 — TLS Termination (Internal CA)

Goal:
- Establish TLS termination requirements and trust flow for LAN operators.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md
- ../../design/infra/tls.md

Preconditions:
- C1 complete.

Deliverables:
- HTTPS-only Caddy staging ingress configuration.
- Container-local internal CA + leaf certificate lifecycle in stagingctl.
- TLS trust and certificate handling runbook section.
- Operator trust-import checklist.

Validation steps:
1. Validate certificate lifecycle and trust chain steps are deterministic.
2. Validate HTTPS-only expectations are explicit.
3. Validate staging smoke asserts HTTPS reachable and HTTP disabled.

Stop-gates:
1. Do not proceed with LAN gate milestones until TLS runbook is complete.
2. Do not proceed if TLS private keys leave container-local storage.

Validation evidence:
1. HTTPS-only Caddy config and cert/key binding are implemented in `../../staging/container/Caddyfile`.
2. Container-local TLS provisioning and Caddy config validation are implemented in `../../dev/bin/stagingctl`.
3. C2 contract checks are implemented in `../../tests/staging/test_stagingctl_policy_contracts.py`.
4. TLS runbook and trust-import flow are documented in `../../design/infra/tls.md`.

### C3 — Proxy-Level Rate Limiting

Status:
- Not applicable for current LAN deployment

Rationale:
- The Web Control Plane currently operates only on a trusted LAN with authenticated operators and no WAN exposure.
- There is no untrusted ingress or multi-tenant edge profile in the present deployment model.
- Adding proxy-level rate limiting now would increase configuration and operational complexity without meaningful risk reduction for this environment.

Decision:
- C3 is formally skipped for the current deployment profile.
- No proxy-level rate limiting is implemented for Phase 2 under the current LAN-only posture.

Impact:
- No Caddy rate-limiting plugin/module work is required for the current LAN deployment.
- No stagingctl or govctl rate-limiting extensions are required.
- No additional C3-specific tests or observability surfaces are required.
- Operator and architecture surfaces remain simpler while preserving current LAN security controls.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C1 and C2 complete.

Deliverables:
- C3 applicability decision and rationale documented for current LAN deployment.
- Re-entry criteria documented for future untrusted ingress profiles.

Validation steps:
1. Confirm C3 is explicitly marked as not applicable for current LAN deployment.
2. Confirm future re-evaluation trigger is documented for WAN or untrusted ingress introduction.

Stop-gates:
1. Do not introduce WAN or untrusted ingress without opening a dedicated rate-limiting chunk and implementation plan.

### C4 — Build Artifact Versioning and Rollback

Goal:
- Formalize versioned release artifact flow and rollback-safe operation.

Inputs:
- ../../design/web/architecture.md
- ../planned/phase-2-architecture-roadmap.md
- ../../design/infra/releases.md

Preconditions:
- C1 baseline complete.

Deliverables:
- Versioned release directory strategy for backend wheel and web build artifacts.
- Deterministic active-release mapping and rollback-safe operation flow.
- Rollback runbook and validation checklist.

Validation steps:
1. Validate forward deploy and rollback sequence are deterministic.
2. Validate release mapping can be audited.
3. Validate stagingctl install deploys from versioned release artifacts, not ad-hoc artifact paths.

Stop-gates:
1. No production LAN gate closure without tested rollback path.

Validation evidence:
1. Versioned release materialization, active mapping, and rollback commands are implemented in `../../dev/bin/stagingctl`.
2. C4 release and rollback contracts are documented in `../../design/infra/releases.md`.
3. C4 release mapping and rollback path contract tests are implemented in `../../tests/staging/test_stagingctl_policy_contracts.py`.

### C5 — API Versioning Policy Enforcement

Goal:
- Enforce operational API versioning discipline for /api/v1 and additive-change posture.

Inputs:
- ../../design/web/api.md
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md
- ../../design/infra/api-versioning-checklist.md

Preconditions:
- C1-C4 in place for stable operations baseline.

Deliverables:
- `/api/v1` stability policy with additive vs breaking/deprecated classification rules.
- API versioning checklist artifact for per-change validation.
- Versioning traceability references in architecture and design decision docs.

Validation steps:
1. Confirm all Phase 2 API changes are additive or formally classified.
2. Confirm deprecation/breaking criteria are documented.
3. Confirm integration test coverage guards canonical `/api/v1` path presence.

Stop-gates:
1. No feature-chunk closure without versioning check completion.

Validation evidence:
1. C5 policy is defined in `../../design/web/api.md` under `Phase 2 Addendum: C5 API Versioning Policy Enforcement`.
2. C5 architecture cross-reference is documented in `../../design/web/architecture.md` section `7. API Layer`.
3. C5 decision posture is documented in `../../design/web/design-decisions.md` under `Phase 2 Decision Addendum: C5 API Versioning Posture`.
4. Per-change checklist artifact is implemented in `../../design/infra/api-versioning-checklist.md`.
5. `/api/v1` route-presence guardrails are validated in `../../tests/integration/api/test_auth.py`.

### C6 — Dashboard Filter Sidebar

Goal:
- Deliver Phase 2 mandatory Dashboard file-type filtering behavior.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md
- ../../design/web/detailed-design/design-tokens.md


Preconditions:
- C5 policy enforcement active.

Deliverables:
- Dashboard filter sidebar component with session-local state.
- Client-side file-type filtering over already-loaded dashboard data.
- Design-token-driven file-type filter option accents.

Validation steps:
1. Validate scope and acceptance criteria match Phase 2 architecture.
2. Validate no conflict with Phase 1.5 interaction invariants.
3. Validate multi-filter selection and clear-all behavior in UI tests.

Stop-gates:
1. No completion without acceptance criteria evidence in plan tracking.

Validation evidence:
1. Sidebar component and dashboard wiring are implemented in `../../webui/src/lib/components/dashboard/FilterSidebar.svelte` and `../../webui/src/routes/+page.svelte`.
2. Session-local filter state and transitions are implemented in `../../webui/src/lib/stores/filterStore.ts`.
3. C6 filter token references are documented in `../../design/web/detailed-design/design-tokens.md`.
4. Dashboard filter state-machine documentation is updated in `../../design/web/architecture.md`.
5. C6 decision posture is documented in `../../design/web/design-decisions.md`.
6. Unit tests for filter state transitions are implemented in `../../webui/tests/component/filterStore.test.ts`.
7. E2E filter behavior coverage is implemented in `../../webui/tests/e2e/dashboard.filter-sidebar.spec.ts`.

### C7 — Audit Timeline Infinite Scroll

Goal:
- Deliver mandatory Audit Timeline interaction migration to infinite scroll.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C5 policy enforcement active.

Deliverables:
- Documented interaction contract and paging transition rules.

Validation steps:
1. Validate pagination semantics preservation under new interaction model.
2. Validate error and terminal-state behavior consistency.

Stop-gates:
1. No completion without explicit validation of load termination behavior.

### C6/C7 Drift Fix Summary — 2026-04-11

1. Canonical staging endpoint normalized to `https://staging-photo-ingress.home.arpa` for staging E2E and Playwright defaults.
2. Staging TLS SAN set expanded to include:
	- `staging-photo-ingress`
	- `staging-photo-ingress.home.arpa`
	- `npi.pohl-family.org`
	- `localhost`
	- `127.0.0.1`
	- `::1`

### C6/C7 Infrastructure Extension Summary — Cloudflare Tunnel

1. `stagingctl create` now enforces a single read-only host mount for the Cloudflare tunnel token:
	- source: `/home/chris/.cloudflare-secrets/npi-staging/tunnel-token`
	- container path: `/etc/cloudflared/token`
2. `stagingctl install` now validates the token mount, installs `cloudflared` if missing, and enables/restarts `cloudflared-tunnel.service`.
3. `stagingctl cloudflared-status` provides operator diagnostics for mount policy, runtime state, tunnel connectivity, and recent logs.
4. `govctl staging.validate` now fails fast unless both trust-sync (`export-ca`) and Cloudflare tunnel strict status checks pass.
5. Secret-handling policy is explicit: no Cloudflare credentials may persist in container-local writable filesystem paths.
3. Staging CORS allowlist normalized to HTTPS origins:
	- `https://staging-photo-ingress.home.arpa`
	- `https://npi.pohl-family.org`
4. E2E trust path aligned to staging internal CA bundle for strict TLS verification.
5. Drift-free CA synchronization enforced via `stagingctl export-ca`, exporting `/etc/caddy/tls/ca.pem` to `tests/ca/staging-ca.pem` for all E2E and Playwright trust.

### C8 — KPI Threshold Configuration + Read-Path Resilience

Goal:
- Deliver KPI threshold API configuration workflow and read-path retry/backoff resilience sign-off.

Inputs:
- ../../design/web/api.md
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C5 complete.
- C6/C7 either complete or in final validation.

Deliverables:
- KPI threshold config workflow plan artifact.
- Read-path retry/backoff validation record.

Validation steps:
1. Validate threshold management behavior against mandatory scope.
2. Validate retry/backoff policy behavior for read-only flows.

Stop-gates:
1. No Phase 2 exit if threshold config or retry/backoff validation is incomplete.

## 2. Cross-Chunk Invariants

1. /api/v1 path baseline remains stable unless explicitly versioned.
2. Uvicorn remains localhost-bound behind proxy boundary.
3. TLS controls are mandatory for current LAN gate closure; C3 rate limiting is deferred unless deployment exposure changes.
4. Phase 1.5 interaction invariants remain preserved.
5. Every chunk output must be traceable to architecture sections and acceptance checks.
6. Runtime tmpfs and runtime tmp/cache write paths are container-local.
7. Host-mounted persistent evidence/log paths are required in staging lifecycle operations.
8. Host-based tmpfs and host-backed `/tmp`, `/var/tmp`, or cache device bindings are prohibited.
9. No host-level systemd or host-level Caddy operations are part of the Phase-2 staging infra model.
10. Future media-library host mount support is reserved as read-only for hash import tests.

## 2.1 Phase-2 Infra Baseline

Phase-2 infra baseline requires:

1. container-local tmpfs only
2. host-mounted persistent evidence/log paths
3. no host-based tmpfs
4. no host-backed `/tmp`, `/var/tmp`, or cache device bindings
5. no host-level systemd or Caddy involvement
6. future media-library host mount reserved as read-only

Reference:
- ../../design/infra/staging-invariants.md

## 3. Rollback Strategy

1. Operational rollback uses release-versioned artifact switching.
2. Proxy policy rollback (TLS boundary) must be documented with safe fallback behavior.
3. Any chunk introducing deployment risk must include explicit rollback steps before sign-off.
4. Rollback validation is required for LAN gate closure.

## 4. Drift-Prevention Rules

1. No drift between roadmap and implementation plan: updates must be mirrored in both docs.
2. No drift between plan and architecture: architecture-affecting updates reflected in ../../design/web/architecture.md within 24h.
3. No edits to archival docs under ../implemented/.
4. All cross-references must remain relative.
5. All implementation work must cite chunk IDs C1–C8.
6. All completed chunks must be migrated to ../implemented/ with validation evidence.

## 5. Initial Phase-2 Tasks

### T1 — Reverse Proxy (Caddy) introduction

Status:
- Completed (2026-04-11)
- C1.1 stagingctl rewrite completed (2026-04-11)

Description:
- Establish Caddy as mandatory ingress boundary for Web Control Plane.

Rationale:
- Required LAN-exposure control and boundary enforcement.

Dependencies:
- C1.

Acceptance Criteria:
1. Topology and route ownership documented.
2. Uvicorn localhost-bound model preserved.

Completion evidence:
1. Topology and route ownership documented in `../../design/web/architecture.md` section `3.2`.
2. Uvicorn localhost-bound model documented in `../../design/web/architecture.md` section `3.3`.
3. Phase-2 staging infra baseline and reconciliation contract documented in `../../design/infra/staging-invariants.md`.
4. C1 infra summary confirms container-local runtime tmpfs and host-persistent evidence/log mounts, with future read-only media mount reserved.
5. C1.1 implementation artifacts:
	- `../../dev/bin/stagingctl`
	- `../../tests/staging/test_stagingctl_policy_contracts.py`

### T2 — TLS termination (internal CA)

Description:
- Define and operationalize TLS termination with internal CA trust model.

Rationale:
- Mandatory security baseline before LAN exposure.

Dependencies:
- T1 (C1), C2.

Acceptance Criteria:
1. Trust import/runbook complete.
2. HTTPS boundary enforced in planning artifacts.

### T3 — Rate limiting at proxy level

Status:
- Not applicable for current LAN deployment

Description:
- Deferred task placeholder for future untrusted ingress profiles.

Rationale:
- Current deployment remains LAN-only with trusted operators and no WAN exposure.

Dependencies:
- T1, T2, C3 decision record.

Acceptance Criteria:
1. C3 not-applicable decision remains documented and linked to LAN-only posture.
2. Re-evaluation trigger for WAN or untrusted ingress remains documented.

### T4 — Build artifact versioning + rollback

Description:
- Introduce versioned static build release model and rollback flow.

Rationale:
- Safe deployment and rapid recovery are mandatory for LAN gate.

Dependencies:
- T1, C4.

Acceptance Criteria:
1. Release and rollback runbook published.
2. Validation checklist covers rollback execution.

### T5 — API versioning policy enforcement

Description:
- Formalize and enforce /api/v1 compatibility policy for Phase 2 changes.

Rationale:
- Prevent uncontrolled schema/path drift.

Dependencies:
- C5.

Acceptance Criteria:
1. Versioning policy checklist in use for all Phase 2 API changes.
2. Additive/breaking classification captured per change.

### T6 — Filter Sidebar (Dashboard)

Description:
- Deliver Dashboard file-type filter behavior defined as Phase 2 mandatory.

Rationale:
- Deferred mandatory UX capability from Phase 1.

Dependencies:
- C6, C5.

Acceptance Criteria:
1. Scope and behavior contract documented and validated.
2. Acceptance criteria explicitly tracked in chunk evidence.

### T7 — Audit Timeline Infinite Scroll

Description:
- Deliver Audit timeline transition from explicit load-more flow to infinite scroll.

Rationale:
- Mandatory Phase 2 UX upgrade.

Dependencies:
- C7, C5.

Acceptance Criteria:
1. Behavior and terminal-load conditions validated.
2. No unresolved conflicts with existing pagination semantics.

### T8 — KPI Threshold Configuration API

Description:
- Deliver API-backed KPI threshold configuration workflow.

Rationale:
- Mandatory Phase 2 settings capability.

Dependencies:
- C8, C5.

Acceptance Criteria:
1. KPI threshold management workflow documented and validated.
2. Acceptance criteria traceability captured in chunk artifacts.

### T9 — Health Polling Resilience (retry/backoff)

Description:
- Confirm read-path retry/backoff resilience under Phase 2 policy.

Rationale:
- Required reliability behavior for read-only operator paths.

Dependencies:
- C8, C5.

Acceptance Criteria:
1. Retry/backoff policy validation record complete.
2. Read-path resilience checks pass against documented policy.

### T10 — Documentation normalization and link hygiene (Phase-2 ongoing)

Description:
- Continuous normalization of cross-file references and planning/design consistency.

Rationale:
- Prevent documentation drift during Phase 2 execution.

Dependencies:
- C1-C8 (ongoing).

Acceptance Criteria:
1. Relative links remain valid after each planning update.
2. No unresolved architecture-plan divergence at review points.
3. Completed items moved from ../planned to ../implemented.
