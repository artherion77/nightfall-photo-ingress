# Web Control Plane — Phase 2 Architecture Roadmap

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Executive Summary

Phase 2 is now activated as the authoritative next design phase for the Web Control Plane.
The objective is to complete LAN-exposure readiness and deferred Phase 2 operator features
under deterministic, audit-ready governance.

This roadmap is derived from consolidated authoritative documents:
- ../../design/web/architecture.md
- ../../design/web/api.md
- ../../design/web/design-decisions.md
- ../../design/web/detailed-design/design-tokens.md
- ../../design/web/detailed-design/photowheel.md
- ../../design/web/detailed-design/staging-footer.md

Historical references are read-only:
- ../implemented/

## 2. Scope (Mandatory vs Optional)

### 2.1 Phase 2 Mandatory

1. Reverse proxy introduction (Caddy) for LAN exposure gate.
2. TLS termination at proxy layer.
3. Proxy-level rate limiting.
4. Build artifact versioning and rollback workflow.
5. API versioning policy formalization and enforcement discipline for /api/v1.
6. Retry/backoff resilience for read-only API client flows (health and read paths).
7. Dashboard Filter Sidebar (file-type filter behavior).
8. Audit Timeline migration from explicit pagination to infinite scroll.
9. KPI Threshold configuration via API and settings workflow.

### 2.2 Phase 2 Optional

1. SSR adoption path (conditional, non-gating).
2. SQLite to Postgres migration path.
3. Background worker architecture evolution.
4. OIDC/OAuth enhanced authentication model.
5. CDN and advanced static asset caching strategy.

### 2.3 Phase 2 Non-Goals

1. No redesign of established Phase 1/1.5 domain behavior.
2. No direct edits to archival documents under ../implemented/.
3. No expansion into Phase 3 sidecar/metadata program in this phase.
4. No breaking API path rename from /api/v1 during Phase 2 activation.

## 3. Architecture Changes

1. Deployment topology changes from localhost-only service access to LAN-safe proxy front-door.
2. Caddy becomes the ingress boundary for static assets and API routing.
3. Uvicorn remains bound to localhost; proxy is mandatory access surface.
4. Versioned release directory and rollback-safe symlink strategy become architecture baseline.
5. Architecture-document to implementation-plan chunk mapping becomes mandatory governance artifact.

## 4. API Changes

1. Formal API versioning policy becomes active and traceable.
2. Phase 2 additive API changes include configuration and filtering surfaces needed by mandatory UI features.
3. Mutating endpoint retry remains manual/idempotency-key driven; automatic retry remains GET-only scope.
4. Versioning policy requires additive compatibility for Phase 2 completion gate.

## 5. UI/UX Changes

1. Dashboard introduces Filter Sidebar for file-type scoping.
2. Audit Timeline transitions to infinite-scroll interaction model.
3. Settings flow includes KPI threshold management through API-backed controls.
4. Existing Phase 1.5 interaction and visual invariants remain preserved.

## 6. Operational Changes

1. Caddy introduction as Phase 2 mandatory ingress layer.
2. TLS termination (internal CA trust model for LAN operators).
3. Proxy-level rate limiting policy activated for /api paths.
4. Build artifact release versioning and rollback runbook activated before LAN gate sign-off.
5. Structured operational checks for proxy, cert trust, rate policy, and rollback integrity.

## 7. Phase 2 Dependencies

### 7.1 Upstream Dependencies

1. Phase 1 completed and stable.
2. Phase 1.5 completion gate applied for P2 chunks beyond retry/backoff baseline.
3. Consolidated design docs remain authoritative and current.

### 7.2 Internal Dependencies

1. Caddy + TLS + rate limiting must be complete before LAN exposure sign-off.
2. Build versioning/rollback must be complete before proxy gate closure.
3. API versioning policy must be in force before feature-level completion sign-off.
4. UI feature chunks depend on stable API contracts and documented acceptance checks.

## 8. Risks and Mitigations

1. Risk: Drift between architecture and implementation plan.
- Mitigation: Mandatory chunk ID traceability and 24h architecture sync rule.

2. Risk: Proxy/TLS misconfiguration blocks operator access.
- Mitigation: deterministic preflight checklist + rollback runbook.

3. Risk: Feature sequencing conflicts across UI/API/ops.
- Mitigation: chunk stop-gates and explicit preconditions per chunk.

4. Risk: Versioning policy declared but not operationalized.
- Mitigation: mandatory validation artifact in implementation chunk for API policy.

5. Risk: Archived document edits reintroduce divergence.
- Mitigation: archival immutability rule and planned-folder-only active planning updates.

## 9. Exit Criteria

Phase 2 activation is considered complete when:

1. All Phase 2 mandatory items are delivered and validated.
2. LAN exposure gate is signed off with Caddy, TLS, rate limiting, and rollback workflow active.
3. API versioning policy is published and enforced for all Phase 2 changes.
4. Mandatory UI feature set (Filter Sidebar, Infinite Scroll, KPI thresholds) is validated.
5. Architecture and implementation plan have no unresolved drift.

## 10. Milestones (M1–M5)

### M1 — Governance and Planning Activation

1. Phase 2 roadmap and implementation plan are active and synchronized.
2. Chunk map and task map are published with acceptance criteria.

### M2 — LAN Gate Foundation

1. Caddy introduced.
2. TLS termination active.
3. Proxy rate limiting baseline active.

### M3 — Release Safety

1. Build artifact versioning workflow active.
2. Rollback workflow validated.

### M4 — Application Feature Completion

1. API versioning policy enforcement artifact complete.
2. Filter Sidebar complete.
3. Audit infinite scroll complete.
4. KPI thresholds configuration complete.
5. Read-path retry/backoff resilience validated.

### M5 — Phase 2 Exit and Handover

1. All mandatory validations passed.
2. Drift audit passed.
3. Completed artifacts moved to ../implemented/.
4. Phase 3 readiness handoff documented.

## 11. Phase 2 Governance

1. Deterministic execution rules
- All Phase 2 work must map to explicit chunk IDs and acceptance checks.

2. No drift between architecture and implementation plan
- Any plan change that impacts design must be reflected in ../../design/web/architecture.md within 24 hours.

3. Allowed locations for new design work
- ../../design/web/*
- ../planned/*

4. Completion migration rule
- Completed tasks and completed plans must be moved to ../implemented/.

5. Archive immutability rule
- No direct edits to ../implemented/ artifacts.

6. Cross-reference rule
- All references use relative paths.

7. Architecture reflection SLA
- Design-impacting changes must be represented in architecture documentation within 24h.

8. Implementation traceability rule
- Every implementation change must reference roadmap chunk IDs.
