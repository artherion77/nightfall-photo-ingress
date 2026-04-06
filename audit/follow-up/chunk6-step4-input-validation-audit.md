# Chunk 6 Step 4 — Input Validation Audit

Status: Completed
Date: 2026-04-06
Owner: Systems Engineering

## Scope

Step 4 audit for API boundary validation and unsafe input propagation risk:

- Router path/query/header validation coverage
- Request body validation coverage via Pydantic schemas
- Use of parameterized SQL for user-influenced values
- Any direct file-system usage from raw request input

## Files reviewed

- `api/routers/health.py`
- `api/routers/staging.py`
- `api/routers/audit_log.py`
- `api/routers/config.py`
- `api/routers/blocklist.py`
- `api/routers/triage.py`
- `api/services/staging_service.py`
- `api/services/audit_service.py`
- `api/services/blocklist_service.py`
- `api/services/triage_service.py`
- `api/schemas/*.py`

## Findings

### Resolved in this step

1. Query/path/header boundary constraints were incomplete on multiple endpoints.
- Added explicit FastAPI constraints:
  - Staging `limit` now constrained to `1..100`
  - Audit-log `limit` now constrained to `1..1000`
  - Cursor-like query params constrained with min/max length
  - `rule_id` path constrained to positive integers (`>=1`)
  - `X-Idempotency-Key` constrained to `8..128` chars on mutating routes

2. Blocklist payload type validation relied on DB `CHECK` constraints.
- Added schema-level validation in `api/schemas/blocklist.py`:
  - `rule_type` now `Literal["filename", "regex"]`
  - pattern/reason length bounds added

### No high-risk gaps identified

- SQL usage in API services uses parameterized queries (`?` placeholders).
- No direct file-system operations in routers from raw user input.
- Mutation flows delegate to service/domain layers; no string interpolation into SQL.

## Validation evidence

Integration tests added/extended:

- `tests/integration/api/test_staging.py`
  - rejects invalid staging `limit=0` with 422
- `tests/integration/api/test_audit_log.py`
  - rejects invalid audit-log `limit=0` with 422
- `tests/integration/api/test_blocklist.py`
  - rejects invalid `rule_type`
  - rejects too-short idempotency key
  - rejects invalid rule_id path (`0`)

## Residual risk

- `item_id` path format remains intentionally permissive (length-bounded) due to existing
  test/fixture identifiers that are not strictly normalized to fixed hash format.
  Tracking issue: #1 (`Chunk6 Step4 residual risk: item_id path remains permissive`)
  - https://github.com/artherion77/nightfall-photo-ingress/issues/1
- If/when canonical SHA-256 normalization becomes mandatory across fixtures/runtime,
  path pattern can be tightened in a dedicated follow-up change.
  Tracking issue: #2 (`Follow-up: enforce canonical SHA-256 item_id normalization across fixtures/runtime`)
  - https://github.com/artherion77/nightfall-photo-ingress/issues/2
