# API Versioning Checklist (Phase 2 C5)

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

Purpose:
- Prevent uncontrolled `/api/v1` schema/path drift.
- Classify each API change as additive or breaking/deprecated before merge.

Use this checklist for every API change:

## 1. Path and Routing Checks

1. Does the change keep existing `/api/v1` paths intact?
2. If a path is added, is it under `/api/v1` and non-conflicting?
3. If a path is renamed/removed, is it classified as breaking and documented with transition plan?
4. Are existing compatibility alias paths still present where applicable (for example `/api/v1/audit/log` and `/api/v1/audit-log`)?

## 2. Request Contract Checks

1. Are new request fields/params optional with safe defaults?
2. Are existing required fields unchanged?
3. If validation was tightened, is this documented as breaking or covered by deprecation window?
4. Are path/query/body constraints backward-compatible for existing clients?

## 3. Response Contract Checks

1. Are existing response fields still present?
2. Are existing field types and semantic meanings unchanged?
3. Are added fields optional/non-breaking for existing clients?
4. Are status-code semantics unchanged for established successful flows?

## 4. Change Classification

1. Change classification selected:
   - additive
   - breaking
   - deprecated
2. If breaking/deprecated:
   - rationale documented in `design/web/api.md`
   - operator impact documented in plan/tracking artifacts
   - transition/rollback notes recorded

## 5. Validation Evidence

1. OpenAPI path coverage confirms canonical `/api/v1` surfaces remain present.
2. Relevant integration tests pass for unchanged endpoints.
3. Any new endpoint tests are added or existing tests extended.
4. `planning/planned/phase-2-implementation-plan.md` is updated if the change is part of a Phase 2 chunk.
