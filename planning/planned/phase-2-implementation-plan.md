# Web Control Plane — Phase 2 Implementation Plan

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Chunked Execution Plan (C1–C8)

### C1 — Reverse Proxy Baseline (Caddy)

Status:
- Implemented (2026-04-11)

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

Validation steps:
1. Verify documented route ownership for static and /api paths.
2. Verify Uvicorn remains localhost-bound in documented topology.

Stop-gates:
1. Do not proceed if topology documentation conflicts with architecture.md.
2. Do not proceed if ingress boundary ownership is ambiguous.

Validation evidence:
1. Route ownership and ingress topology are documented in `../../design/web/architecture.md`:
	- `## 3. Reverse Proxy`
	- `### 3.2 Proxy Topology (Phase 2)`
2. Localhost-only application binding is documented in `../../design/web/architecture.md`:
	- `### 3.3 Uvicorn Binding Change for Phase 2`
3. Mandatory gate checklist is documented in `../../design/web/architecture.md`:
	- `### 3.6 Phase 2 Mandatory Reverse Proxy Checklist`

### C2 — TLS Termination (Internal CA)

Status:
- Implemented (2026-04-11)

Goal:
- Establish TLS termination requirements and trust flow for LAN operators.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C1 complete.

Deliverables:
- TLS trust and certificate handling runbook section.
- Operator trust-import checklist.

Validation steps:
1. Validate certificate lifecycle and trust chain steps are deterministic.
2. Validate HTTPS-only expectations are explicit.

Stop-gates:
1. Do not proceed with LAN gate milestones until TLS runbook is complete.

Validation evidence:
1. TLS trust model and certificate handling are documented in `../../design/web/architecture.md`:
	- `### 3.1 Decision: Caddy over Nginx`
	- `### 3.6 Phase 2 Mandatory Reverse Proxy Checklist` (item 2)
2. HTTPS-only boundary requirement is documented in `../../design/web/architecture.md`:
	- `### 3.6 Phase 2 Mandatory Reverse Proxy Checklist` (item 3)

### C3 — Proxy-Level Rate Limiting

Status:
- Implemented (2026-04-11)

Goal:
- Define and activate proxy-layer rate limiting policy as mandatory LAN gate control.

Inputs:
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C1 and C2 complete.

Deliverables:
- Rate limit policy matrix by endpoint class.
- Validation checklist for threshold behavior and log visibility.

Validation steps:
1. Confirm policy applies before requests reach application process.
2. Confirm observability and policy rollback procedure are documented.

Stop-gates:
1. No LAN gate sign-off without rate limiting evidence artifact.

Validation evidence:
1. Proxy-layer rate-limiting design and policy intent are documented in `../../design/web/architecture.md`:
	- `### 3.5 Rate Limiting at Proxy Level`
2. Mandatory LAN-gate requirement is documented in `../../design/web/architecture.md`:
	- `### 3.6 Phase 2 Mandatory Reverse Proxy Checklist` (item 7)
3. Observability expectation is documented in `../../design/web/architecture.md`:
	- `### 3.5 Rate Limiting at Proxy Level` (access-log visibility)

### C4 — Build Artifact Versioning and Rollback

Goal:
- Formalize versioned release artifact flow and rollback-safe operation.

Inputs:
- ../../design/web/architecture.md
- ../planned/phase-2-architecture-roadmap.md

Preconditions:
- C1 baseline complete.

Deliverables:
- Release directory strategy.
- Rollback runbook and validation checklist.

Validation steps:
1. Validate forward deploy and rollback sequence are deterministic.
2. Validate release mapping can be audited.

Stop-gates:
1. No production LAN gate closure without tested rollback path.

### C5 — API Versioning Policy Enforcement

Goal:
- Enforce operational API versioning discipline for /api/v1 and additive-change posture.

Inputs:
- ../../design/web/api.md
- ../../design/web/architecture.md
- ../../design/web/design-decisions.md

Preconditions:
- C1-C4 in place for stable operations baseline.

Deliverables:
- Policy enforcement checklist.
- Versioning traceability artifact for Phase 2 changes.

Validation steps:
1. Confirm all Phase 2 API changes are additive or formally classified.
2. Confirm deprecation/breaking criteria are documented.

Stop-gates:
1. No feature-chunk closure without versioning check completion.

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
- Documented behavior contract for filter state, options, and scoped effects.

Validation steps:
1. Validate scope and acceptance criteria match Phase 2 architecture.
2. Validate no conflict with Phase 1.5 interaction invariants.

Stop-gates:
1. No completion without acceptance criteria evidence in plan tracking.

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
3. Proxy controls (TLS/rate limiting) are mandatory before LAN gate closure.
4. Phase 1.5 interaction invariants remain preserved.
5. Every chunk output must be traceable to architecture sections and acceptance checks.

## 3. Rollback Strategy

1. Operational rollback uses release-versioned artifact switching.
2. Proxy policy rollback must be documented with safe fallback behavior.
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

### T2 — TLS termination (internal CA)

Status:
- Completed (2026-04-11)

Description:
- Define and operationalize TLS termination with internal CA trust model.

Rationale:
- Mandatory security baseline before LAN exposure.

Dependencies:
- T1 (C1), C2.

Acceptance Criteria:
1. Trust import/runbook complete.
2. HTTPS boundary enforced in planning artifacts.

Completion evidence:
1. Trust-import and TLS requirement documented in `../../design/web/architecture.md` section `3.6` (item 2).
2. HTTPS-only boundary documented in `../../design/web/architecture.md` section `3.6` (item 3).

### T3 — Rate limiting at proxy level

Status:
- Completed (2026-04-11)

Description:
- Apply proxy-level rate policy for API protection and resilience.

Rationale:
- Phase 2 mandatory gate requirement.

Dependencies:
- T1, T2, C3.

Acceptance Criteria:
1. Policy matrix documented.
2. Validation checklist confirms pre-application throttling behavior.

Completion evidence:
1. Proxy-level throttling requirement documented in `../../design/web/architecture.md` section `3.5`.
2. Mandatory `/api/` rate-limiting gate documented in `../../design/web/architecture.md` section `3.6` (item 7).

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
