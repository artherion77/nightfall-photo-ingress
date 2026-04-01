# Web Control Plane Implementation Roadmap

Status: Proposed
Date: 2026-04-01
Owner: Systems Engineering

## 1. Scope

Deliver an operator-focused control plane for photo-ingress using FastAPI plus Svelte, while preserving existing ingest and registry invariants.

## 2. Delivery Principles

- Ship vertical slices that are usable at each phase.
- Keep all mutating actions idempotent and audit-first.
- Keep CLI parity for every operator action until web paths are proven.
- Gate each phase with explicit tests and acceptance checks.

## 3. Phase Plan

## Phase 1: Foundation

Goals:
- Create API service skeleton and Svelte shell.
- Add health, version, and capability endpoints.
- Establish shared domain service bindings.

Implementation:
- FastAPI app bootstrap, router layout, OpenAPI schema exposure.
- Svelte project scaffold with API proxy configuration.
- Config-driven API auth mode (off/local/token).

Exit criteria:
- `GET /api/v1/health` and `GET /api/v1/version` return stable responses.
- UI can render service status from API.
- CI runs API + UI unit tests.

Test gates:
- Backend unit tests for startup/config/auth mode wiring.
- Frontend unit tests for API client and health page rendering.

## Phase 2: Read-Only Visibility

Goals:
- Provide staging inventory and audit timeline visibility.
- Add item detail view and safe pagination/filtering.

Implementation:
- Read endpoints for staging list, item detail, audit log.
- UI pages for timeline and item inspection.
- Optional thumbnail endpoint with on-demand generation and cache.

Exit criteria:
- Operator can browse staging and audit history with filters.
- Pagination and sort order are deterministic.
- Read endpoints meet p95 latency target under staging load.

Test gates:
- API integration tests for pagination/filter semantics.
- UI e2e tests for timeline and item detail workflows.

## Phase 3: Safe Triage Actions

Goals:
- Enable accept/reject/defer actions from UI.
- Enforce idempotency and transaction-safe writes.

Implementation:
- Mutating triage endpoints requiring `X-Idempotency-Key`.
- Shared transaction wrapper: audit append then state transition.
- UI confirmation dialogs and action result surfacing.

Exit criteria:
- Repeated requests with same idempotency key produce same outcome.
- All triage actions create immutable audit events.
- CLI and UI produce equivalent registry state for same action.

Test gates:
- Concurrency tests for duplicate submissions.
- Integration parity tests against CLI behavior.

## Phase 4: Metadata And Blocklist Management

Goals:
- Add sidecar metadata fetch orchestration.
- Add blocklist rule management from UI.

Implementation:
- Sidecar async job table and worker loop.
- Blocklist CRUD API and Svelte management page.
- Validation for patterns and preview diagnostics.

Exit criteria:
- Sidecar jobs transition through queued/running/done/failed states.
- Blocklist changes are auditable and take effect in ingest decisions.
- UI can retry failed sidecar fetches.

Test gates:
- Worker reliability tests with retry backoff.
- Blocklist validation tests and ingestion effect tests.

## Phase 5: Workflow Automation

Goals:
- Introduce operator-assisted batch actions and dry-run simulation.
- Add policy preview before applying automation.

Implementation:
- Batch triage endpoint with preview and commit modes.
- UI simulation panel with impact summary.
- Safety constraints for max-batch size and rollback behavior.

Exit criteria:
- Dry-run outputs are reproducible and do not mutate state.
- Batch commit generates complete audit trails.
- Operator can cancel long-running operations safely.

Test gates:
- Integration tests for dry-run/commit separation.
- Performance tests for large staging sets.

## Phase 6: Hardening And Operations

Goals:
- Finalize security, performance, and operational readiness.
- Produce runbooks and deployment guidance.

Implementation:
- Token auth hardening, rate limits, CORS allowlist enforcement.
- Metrics and dashboards for API + worker health.
- Backup/restore drills for registry and new tables.

Exit criteria:
- Security checklist completed and validated in staging.
- p95 latency and error budget targets met.
- Runbook supports upgrade, rollback, and incident triage.

Test gates:
- Staging soak tests.
- Failure-injection tests for API, worker, and registry lock contention.

## 4. Cross-Phase Quality Gates

- Contract tests keep API schemas stable per minor version.
- Every mutating route has idempotency replay tests.
- Every operator-visible action has audit-log assertions.
- Phase completion requires docs updates and operator notes.

## 5. Rollout Order

1. Deploy read-only capability to staging operators.
2. Enable mutating triage for a small operator cohort.
3. Enable metadata and blocklist management.
4. Enable automation features last.
5. Promote to production after two clean staging cycles.

## 6. Risks And Controls

- Risk: API/UI drift from domain rules.
  - Control: shared domain service and parity tests.
- Risk: accidental duplicate action execution.
  - Control: strict idempotency key enforcement.
- Risk: operational complexity growth.
  - Control: runbook-first and phased enablement via feature flags.

## 7. Definition Of Done (Program Level)

- Operators can complete end-to-end triage in UI without violating ingest constraints.
- CLI fallback remains available and behavior-equivalent.
- Security and observability baselines are documented and validated.
- Architecture extension and roadmap remain synchronized with implementation reality.
