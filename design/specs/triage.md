# Triage Write Path Specification

Status: active (Chunk 4 implemented)
Date: 2026-04-04
Owner: Systems Engineering

---

## 1. Scope

This specification defines the web control-plane triage write path for:

- `POST /api/v1/triage/{item_id}/accept`
- `POST /api/v1/triage/{item_id}/reject`
- `POST /api/v1/triage/{item_id}/defer`

The implementation covers registry state transitions, idempotency replay semantics,
and audit-first write behavior.

---

## 2. API Contract

### 2.1 Authentication

All triage endpoints require:

- `Authorization: Bearer <token>`

Token validation is handled by `api/auth.py`.

### 2.2 Idempotency Header

All triage endpoints require:

- `X-Idempotency-Key: <string>`

Missing header results in `422` (FastAPI validation error).

### 2.3 Request Body

Schema (`TriageRequest`):

```json
{
  "reason": "optional string or null"
}
```

### 2.4 Success Response

Schema (`TriageResponse`):

```json
{
  "action_correlation_id": "<idempotency-key>",
  "item_id": "<sha256>",
  "state": "accepted|rejected|pending"
}
```

---

## 3. State Transition Semantics

The current Chunk 4 implementation updates only `files.status` and `files.updated_at`
in the registry and does not move physical files.

Action mapping:

- `accept` -> `files.status = 'accepted'`
- `reject` -> `files.status = 'rejected'`
- `defer` -> `files.status = 'pending'`

If `item_id` does not exist in `files`, the endpoint returns `404`.

---

## 4. Idempotency Semantics

Idempotency storage table: `ui_action_idempotency`.

For the first successful request with a key:

1. The mutation is applied.
2. Response payload and HTTP status are persisted with the key.

For a duplicate request with the same key, same action, and same `item_id`:

- Stored response is replayed (`200`) and no additional state change is applied.

For a duplicate key reused with a different action or `item_id`:

- Endpoint returns `409` conflict (`Idempotency key reuse conflict`).

Retention metadata:

- `created_at` and `expires_at` are persisted.
- Current implementation writes `expires_at = created_at + 24h`.
- Automatic cleanup of expired idempotency rows is not part of Chunk 4.

---

## 5. Audit-First Behavior

`api/audit_hook.py` provides `triage_audit_hook()`.

Within one DB transaction:

1. Pre-mutation event is appended:
   - `action = triage_<action>_requested`
2. Mutation is applied to `files.status`.
3. Applied event is appended:
   - `action = triage_<action>_applied`

If an exception occurs inside the audit hook block, a compensating event is appended:

- `action = triage_<action>_compensating`

The transaction is then rolled back by the service, preserving registry state.

---

## 6. Error Cases and HTTP Codes

- `200` - mutation succeeded or idempotent replay succeeded.
- `404` - `item_id` not found in registry.
- `409` - idempotency key reuse conflict (same key, different action or item).
- `422` - missing `X-Idempotency-Key` header or invalid request shape.
- `500` - unexpected service failure (`detail = "Triage action failed"`).

---

## 7. Test Strategy (Chunk 4)

Chunk 4 uses pytest integration tests for both API and UI-flow simulation.

- API: `tests/integration/api/test_api_triage.py`
- UI-flow simulation: `tests/integration/ui/test_triage.py`
- Failure rollback regression: `tests/integration/ui/test_triage_error_recovery.py`

Naming convention note:

- API test module uses `test_api_triage.py` to avoid import-name collision with
  `tests/integration/ui/test_triage.py` under pytest collection.

Playwright is deferred for this chunk; integration behavior is validated through
ASGI-backed pytest tests.
