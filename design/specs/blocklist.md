# Blocklist Write Path Specification

Status: active (Chunk 5 implemented)
Date: 2026-04-04
Owner: Systems Engineering

---

## 1. Scope

This specification defines the web control-plane blocklist write path for:

- `POST /api/v1/blocklist`
- `PATCH /api/v1/blocklist/{rule_id}`
- `DELETE /api/v1/blocklist/{rule_id}`

It also defines ingest enforcement semantics implemented in
`src/nightfall_photo_ingress/domain/ingest.py`.

---

## 2. API Contract

### 2.1 Authentication

All blocklist endpoints require:

- `Authorization: Bearer <token>`

### 2.2 Idempotency Header

All blocklist mutation endpoints require:

- `X-Idempotency-Key: <string>`

Missing header results in `422` (FastAPI validation error).

### 2.3 Request Schemas

`BlockRuleCreate`:

```json
{
  "pattern": "string",
  "rule_type": "filename|regex",
  "reason": "optional string or null",
  "enabled": true
}
```

`BlockRuleUpdate` (partial update):

```json
{
  "pattern": "optional string or null",
  "rule_type": "optional string or null",
  "reason": "optional string or null",
  "enabled": "optional boolean or null"
}
```

### 2.4 Response Schemas

`POST` / `PATCH` return `BlockRule`:

```json
{
  "id": 1,
  "pattern": "*.tmp",
  "rule_type": "filename",
  "reason": "Temporary files",
  "enabled": true,
  "created_at": "2026-04-04T00:00:00+00:00",
  "updated_at": "2026-04-04T00:00:00+00:00"
}
```

`DELETE` returns `BlockRuleDeleteResponse`:

```json
{
  "id": 1,
  "deleted": true
}
```

---

## 3. Status and Error Model

- `201` - create success (or idempotent replay of create)
- `200` - update/delete success (or idempotent replay of update/delete)
- `404` - update/delete target not found
- `409` - idempotency key reuse conflict or data constraint conflict
- `422` - missing `X-Idempotency-Key` or invalid request body

Conflict semantics:

- Reusing a key with different `{action, item_id}` returns `409`.
- DB uniqueness/constraint failures are surfaced as `409`.

---

## 4. Idempotency Replay Semantics

Storage table: `ui_action_idempotency`.

Action mapping used by service layer:

- create -> `blocklist_create` with `item_id = payload.pattern`
- update -> `blocklist_update` with `item_id = str(rule_id)`
- delete -> `blocklist_delete` with `item_id = str(rule_id)`

Replay rules:

1. First successful write persists response status/body for the key.
2. Duplicate key with matching action/item replays stored status/body.
3. Duplicate key with different action/item returns `409`.

Retention metadata:

- `created_at` and `expires_at` are persisted.
- Current implementation sets `expires_at = created_at + 24h`.
- Cleanup of expired rows is out of scope for this chunk.

---

## 5. Ingest Enforcement Semantics

Chunk 5 extends ingest policy to enforce enabled blocklist rules before unknown-file
persistence.

Behavior in `IngestDecisionEngine._process_one`:

1. Compute authoritative SHA-256.
2. Evaluate enabled rules from `blocked_rules` in `id ASC` order.
3. Rule matching:
- `rule_type = filename`: `fnmatch(filename, pattern)`
- `rule_type = regex`: `re.search(pattern, filename)` (invalid regex patterns are skipped)
4. If a rule matches:
- staged file is deleted,
- `files` row is created/updated with `status = rejected`,
- metadata and origin indexes are upserted,
- audit event is appended with `action = rejected` and `reason = block_rule:<rule_type>:<pattern>`,
- ingest outcome is returned as `discard_rejected`.

Replay behavior:

- Re-ingesting the same SHA-256 after a blocklist rejection follows known-hash discard
  semantics (`discard_rejected`) and does not return the file to `pending`.

---

## 6. Frontend Behavior Contract

Client and store modules:

- `webui/src/lib/api/blocklist.ts`
- `webui/src/lib/stores/blocklist.svelte.js`

UI behavior:

- Create/update/delete operations generate idempotency keys client-side.
- Store actions apply optimistic UI updates.
- On API failure, pre-action snapshot is restored and an error toast is pushed.

Confirm/cancel delete behavior:

- Delete is guarded by `ConfirmDialog` on `blocklist/+page.svelte`.
- Cancel path performs no API call and leaves state unchanged.

---

## 7. Test Strategy (Chunk 5)

Chunk 5 uses pytest integration tests (API + UI-flow simulation).

- API: `tests/integration/api/test_blocklist.py`
- UI-flow simulation: `tests/integration/ui/test_blocklist_crud.py`

No Playwright/browser DOM harness is required for this chunk.

Coverage includes:

- create replay via idempotency key,
- update/toggle behavior,
- hard delete behavior,
- ingest honoring newly created rules,
- confirm/cancel semantics represented as execute-delete vs no-delete paths.
