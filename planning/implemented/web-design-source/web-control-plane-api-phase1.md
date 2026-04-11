# Phase 1 REST API Specification

Status: Implemented


**Date:** 2026-04-06  
**Owner:** Systems Engineering

---

## 1. Overview

This document specifies the Phase 1 REST API for the photo-ingress web control plane.
Chunks 1, 4, and 5 provide read models plus triage and blocklist write endpoints. They provide operator access to:
- System health and status
- Pending ingestion queue with pagination
- Audit log with action filtering
- Effective runtime configuration
- Current blocklist rules
- Triage write actions (accept, reject, defer)
- Blocklist write actions (create, update, delete)

All endpoints require bearer token authentication (except docs endpoints).
Pagination uses cursor-based semantics: SHA-256 cursors for staging and numeric
event-id cursors for audit.

Write-path idempotency uses `X-Idempotency-Key` with response replay from
`ui_action_idempotency`.

---

## 2. Authentication

### 2.1 Bearer Token

All `/api/v1/*` endpoints require the `Authorization: Bearer {token}` header.
The token value is read from `photo-ingress.conf` under the `[web]` section as `api_token`.

**Token validation:**
- Header must be present and well-formed: `Authorization: Bearer {token_value}`.
- Token value must match the configured `[web] api_token` value exactly.
- On mismatch or missing header: HTTP 401 Unauthorized.

**Exemptions:**
- `GET /api/docs` (RapiDoc documentation)
- `GET /api/openapi.json` (OpenAPI schema)

### 2.2 Error Response (401)

```json
{
  "detail": "Human-readable error message"
}
```

Current implementation returns specific 401 detail strings such as missing header,
invalid scheme, token not configured, or invalid token.

---

## 3. Common Response Envelope

All endpoints return JSON responses in one of two shapes:

### 3.1 Success Response (2xx)

For most endpoints, the response body is the typed JSON object directly (Pydantic model).

### 3.2 Error Response (4xx, 5xx)

```json
{
  "detail": "Human-readable error message"
}
```

---

## 4. Endpoint Reference

### 4.1 Health Status

**Path:** `GET /api/v1/health`

**Auth:** Required

**Description:** Poll status of key system subsystems and last update timestamp.

**Response schema:**

```typescript
interface HealthResponse {
  polling_ok: ServiceStatus;
  auth_ok: ServiceStatus;
  registry_ok: ServiceStatus;
  disk_ok: ServiceStatus;
  last_updated_at: string;   // ISO-8601 UTC timestamp of last status update
  error: string | null;      // Error message if any subsystem failed; null if all ok
}

interface ServiceStatus {
  ok: boolean;
  message: string;
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  http://localhost:8000/api/v1/health
```

```json
{
  "polling_ok": { "ok": true, "message": "Ingest process is running" },
  "auth_ok": { "ok": true, "message": "Auth OK" },
  "registry_ok": { "ok": true, "message": "Registry OK" },
  "disk_ok": { "ok": true, "message": "Disk OK" },
  "last_updated_at": "2026-04-03T14:32:00Z",
  "error": null
}
```

---

### 4.2 Staging Queue (Pending Items)

**Path:** `GET /api/v1/staging`

**Auth:** Required

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max items per page (capped at 100) |
| `after` | string | null | Cursor (SHA-256) for pagination; omit for first page |

**Description:** Retrieve paginated list of files with `status='pending'` in the registry.
Results are ordered by `sha256` ascending. Pagination uses SHA-256 cursor semantics,
where `after=<sha256>` returns rows with `sha256 > after`.

**Response schema:**

```typescript
interface StagingItem {
  sha256: string;           // SHA-256 hash (canonical file identity)
  filename: string;         // Original filename or "unknown"
  size_bytes: number;       // File size in bytes
  first_seen_at: string;    // ISO-8601 UTC timestamp
  updated_at: string;       // ISO-8601 UTC timestamp
  account: string | null;   // OneDrive account name if available
  onedrive_id: string | null; // OneDrive item ID if available
}

interface StagingPage {
  items: StagingItem[];     // List of pending items
  cursor: string | null;    // Next cursor (sha256 of last returned item)
  has_more: boolean;        // True if more items exist beyond this page
  total: number;            // Total count of pending items
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  'http://localhost:8000/api/v1/staging?limit=20'
```

```json
{
  "items": [
    {
      "sha256": "abc123def456...",
      "filename": "photo_2026-04-03.jpg",
      "size_bytes": 2048000,
      "first_seen_at": "2026-04-03T10:00:00Z",
      "updated_at": "2026-04-03T10:00:00Z",
      "account": "personal",
      "onedrive_id": "abc!123"
    }
  ],
  "cursor": "abc123def456...",
  "has_more": false,
  "total": 1
}
```

---

### 4.3 Single Item Detail

**Path:** `GET /api/v1/items/{item_id}`

**Auth:** Required

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `item_id` | string | SHA-256 hash of the file |

**Description:** Retrieve detailed information for a single file by SHA-256 hash.

**Response schema:** Same as `StagingItem` (see §4.2).

**Status codes:**

- `200`: File found.
- `404`: File not found in registry.

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  'http://localhost:8000/api/v1/items/abc123def456'
```

---

### 4.4 Audit Log

**Path:** `GET /api/v1/audit-log`

**Auth:** Required

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Max events per page (capped at 500) |
| `after` | string | null | Cursor for pagination (audit event ID) |
| `action` | string | null | Filter by action type (e.g., `accepted`, `rejected`, `pending`) |

**Description:** Retrieve paginated audit log entries. Optional action filter to show only
events of a specific type.

Audit results are ordered by `id DESC` (newest first). The `after` cursor is a numeric
audit event id encoded as a string, and follow-up pages fetch older records using
`id < after`.

**Response schema:**

```typescript
interface AuditEvent {
  id: number;               // Unique audit event ID
  sha256: string | null;    // SHA-256 hash if file-related
  account_name: string | null; // Account name if relevant
  action: string;           // E.g., 'pending', 'accepted', 'rejected', 'ingested'
  reason: string | null;    // Human-readable reason for state change
  details: object | null;   // Additional JSON metadata
  actor: string;            // Who triggered action: 'ingest', 'cli', 'ui', 'trash_watch'
  ts: string;               // ISO-8601 UTC timestamp
}

interface AuditPage {
  events: AuditEvent[];     // List of audit events
  cursor: string | null;    // Next cursor (id of last returned event, as string)
  has_more: boolean;        // True if more events exist
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  'http://localhost:8000/api/v1/audit-log?limit=50&action=accepted'
```

---

### 4.5 Effective Configuration

**Path:** `GET /api/v1/config/effective`

**Auth:** Required

**Description:** Retrieve the effective runtime configuration with secrets redacted.
Used by the UI settings page to display current operator-visible configuration.

**Response schema:**

```typescript
interface EffectiveConfig {
  // Config values (varies by [section] in photo-ingress.conf)
  // All sensitive fields (api_token, passwords) shown as "[redacted]"
  // Example structure:
  polling_interval_minutes: number;
  // ... other config fields from AppConfig ...
  
  // KPI thresholds for operator display
  kpi_thresholds: {
    pending_warning: number;
    pending_error: number;
    disk_warning_percent: number;
    disk_error_percent: number;
  };
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  'http://localhost:8000/api/v1/config/effective'
```

```json
{
  "polling_interval_minutes": 15,
  "api_token": "[redacted]",
  "kpi_thresholds": {
    "pending_warning": 100,
    "pending_error": 500,
    "disk_warning_percent": 80,
    "disk_error_percent": 95
  }
}
```

---

### 4.6 Blocklist Rules

**Path:** `GET /api/v1/blocklist`

**Auth:** Required

**Description:** List all block rules currently in effect (enabled and disabled).

**Response schema:**

```typescript
interface BlockRule {
  id: number;               // Unique rule ID
  pattern: string;          // Glob or regex pattern
  rule_type: string;        // Current implementation: 'filename' or 'regex'
  reason: string;           // Human-readable reason for block
  enabled: boolean;         // Is rule currently active
  created_at: string;       // ISO-8601 UTC timestamp
  updated_at: string;       // ISO-8601 UTC timestamp of last modification
}

interface BlockRuleList {
  rules: BlockRule[];       // List of all blocklist rules
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  'http://localhost:8000/api/v1/blocklist'
```

```json
{
  "rules": [
    {
      "id": 1,
      "pattern": "*.tmp",
      "rule_type": "filename",
      "reason": "Temporary files",
      "enabled": true,
      "created_at": "2026-04-03T09:00:00Z",
      "updated_at": "2026-04-03T09:00:00Z"
    }
  ]
}
```

---

### 4.7 Blocklist Mutations

**Auth:** Required

**Paths:**

- `POST /api/v1/blocklist`
- `PATCH /api/v1/blocklist/{rule_id}`
- `DELETE /api/v1/blocklist/{rule_id}`

**Required headers:**

- `Authorization: Bearer <token>`
- `X-Idempotency-Key: <string>`

**Request schemas:**

```typescript
interface BlockRuleCreate {
  pattern: string;
  rule_type: string; // current implementation accepts 'filename' or 'regex'
  reason?: string | null;
  enabled?: boolean; // defaults to true
}

interface BlockRuleUpdate {
  pattern?: string | null;
  rule_type?: string | null;
  reason?: string | null;
  enabled?: boolean | null;
}
```

**Response schemas:**

```typescript
interface BlockRuleDeleteResponse {
  id: number;
  deleted: boolean;
}
```

`POST` and `PATCH` return `BlockRule`; `DELETE` returns `BlockRuleDeleteResponse`.

**Status codes:**

- `201` - create success or idempotent replay of create
- `200` - update/delete success, or idempotent replay of update/delete
- `404` - update/delete target rule not found
- `409` - idempotency key reuse conflict, or uniqueness/constraint conflict
- `422` - required header/body validation failure

**Idempotency replay semantics (`ui_action_idempotency`):**

- Each write persists `{action, item_id, response_status, response_body_json}`.
- A duplicate request with the same key and matching action/item replays the stored response body and status.
- A duplicate key reused with a different action or item returns `409` (`Idempotency key reuse conflict`).
- `expires_at` is persisted as `created_at + 24h`; cleanup is out of scope for this chunk.

**Conflict handling details:**

- `POST /blocklist`: duplicate pattern or invalid rule_type constraints surface as `409`.
- `PATCH /blocklist/{rule_id}`: uniqueness or constraint violations surface as `409`.
- `DELETE /blocklist/{rule_id}`: no-op replay is returned only via idempotency replay; non-existent rule is `404`.

---

### 4.8 Triage Mutations

**Auth:** Required

**Paths:**

- `POST /api/v1/triage/{item_id}/accept`
- `POST /api/v1/triage/{item_id}/reject`
- `POST /api/v1/triage/{item_id}/defer`

**Required headers:**

- `Authorization: Bearer <token>`
- `X-Idempotency-Key: <string>`

**Request schema:**

```typescript
interface TriageRequest {
  reason?: string | null;
}
```

**Response schema:**

```typescript
interface TriageResponse {
  action_correlation_id: string;
  item_id: string;
  state: 'accepted' | 'rejected' | 'pending';
}
```

**Action mapping:**

- `accept` -> `accepted`
- `reject` -> `rejected`
- `defer` -> `pending`

**Status codes:**

- `200` - mutation success or idempotent replay
- `404` - item id not found
- `409` - idempotency key reused with conflicting action/item
- `422` - required header/body validation failure
- `500` - unexpected mutation failure

**Audit-first semantics:**

- pre-event: `triage_<action>_requested`
- success event: `triage_<action>_applied`
- error event (inside mutation block): `triage_<action>_compensating`

---

### 4.9 API Documentation

**Path:** `GET /api/docs`

**Auth:** Not required

**Description:** Serve the RapiDoc interactive API documentation interface.
This is a self-contained HTML page with embedded OpenAPI spec.

**Response:** HTML page with RapiDoc component.

---

### 4.10 OpenAPI Schema

**Path:** `GET /api/openapi.json`

**Auth:** Not required

**Description:** Serve the OpenAPI v3.1 schema for all endpoints.
Automatically generated by FastAPI.

**Response:** JSON according to OpenAPI 3.1 specification.

---

## 5. Pagination Semantics

### 5.1 Cursor-Based Pagination

All list endpoints (`/staging`, `/audit-log`) use cursor-based pagination:

1. **First page:** Omit the `after` parameter.
2. **Subsequent pages:** Include the `after` parameter with the cursor value from the previous response.
3. **`/staging` ordering:** `sha256 ASC`; follow-up pages apply `sha256 > after`.
4. **`/audit-log` ordering:** `id DESC`; follow-up pages apply `id < after`.
5. **Cursor format:** SHA-256 hash (for `/staging`) or numeric ID string (for `/audit-log`).
6. **Consumer rule:** Treat cursors as opaque continuation tokens.
7. **Termination:** When `has_more` is `false`, no further pages exist.

### 5.2 Load-More behavior for audit timeline

Chunk 3 UI uses explicit load-more pagination on `/audit`:
- Initial request: `GET /api/v1/audit-log?limit=50`
- Follow-up request: `GET /api/v1/audit-log?limit=50&after=<cursor>`
- Append returned events to the existing list in UI order (newest-to-oldest within each page).

### 5.3 Limit Parameter

The `limit` parameter controls page size:
- Default limit is endpoint-specific (20 for `/staging`, 50 for `/audit-log`).
- Limits are capped for protection (100 for `/staging`, 500 for `/audit-log`).
- Requests exceeding the cap are silently reduced to the cap.

---

## 6. Error Handling

### 6.1 Standard Error Codes

| Code | Reason | Example |
|------|--------|---------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid query parameter |
| 401 | Unauthorized | Missing or invalid auth token |
| 404 | Not Found | Item ID does not exist |
| 409 | Conflict | Idempotency key reused with different item/action |
| 422 | Validation Error | Missing required `X-Idempotency-Key` on triage/blocklist mutation |
| 500 | Server Error | Unexpected internal error |

### 6.3 Ingest Enforcement Note (Chunk 5)

Blocklist rules are now enforced by the ingest engine before unknown-file persistence:

- `src/nightfall_photo_ingress/domain/ingest.py` loads enabled rules from `blocked_rules`.
- Matching files are persisted as `rejected` with `action='rejected'` and reason `block_rule:<rule_type>:<pattern>`.
- Outcome is returned as `discard_rejected`, and the staged file is removed.
- Replays of the same content hash continue to follow known-hash discard semantics and do not re-enter `pending`.

### 6.2 Error Response Format

All errors return a JSON object with a `detail` message:

```json
{
  "detail": "Human-readable error description"
}
```

---

## 7. Configuration

### 7.1 Photo-ingress.conf

The API is configured via the `[web]` section in `photo-ingress.conf`:

```ini
[web]
api_token = secret-bearer-token-value
bind_host = 127.0.0.1
bind_port = 8000
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_token` | string | (required) | Bearer token for authentication |
| `bind_host` | string | 127.0.0.1 | Server bind address (localhost only in Phase 1) |
| `bind_port` | integer | 8000 | Server bind port |

---

## 8. Database Dependencies

The Phase 1 API requires the following tables in the registry SQLite database:

| Table | Purpose | Introduced |
|-------|---------|------------|
| `files` | Existing: file status and metadata | v2 schema |
| `audit_log` | Existing: all state transitions | v2 schema |
| `file_origins` | Existing: account/onedrive mappings | v2 schema |
| `blocked_rules` | New: blocklist patterns and rules | v3 (Chunk 1) |
| `ui_action_idempotency` | New: idempotency key tracking and replay for triage write path | v3 (Chunk 1) |

See [design/specs/registry.md](../specs/registry.md) for full schema details.

---

## 9. Service Layer Architecture

The API is layered as follows:

```
HTTP Request
    ↓
Router (path validation, parameter extraction)
    ↓
Dependency Injection (auth verification, connection access)
    ↓
Service (business logic, query construction, schema mapping)
    ↓
Registry / Domain (SQLite queries)
    ↓
Response
```

**Key design principles:**

- **No domain modification:** All API code is additive; no existing domain modules are modified.
- **Schema separation:** Pydantic response schemas are independent of domain models.
- **Service encapsulation:** Query logic is isolated in service classes.
- **Testability:** Each layer can be tested independently.

### 9.1 Dependency Injection Pattern

FastAPI's `Depends()` framework is used for:
- **Auth verification:** Bearer token validation via dependency injection.
- **SQLite connection access:** Registry connection injected at route-level dependencies.

Runtime dependency resolution accesses app-global state (set during lifespan startup):
- `_app_config: AppConfig` — configuration loaded from `photo-ingress.conf`
- `_registry_conn: sqlite3.Connection` — SQLite connection to the registry database

Dependencies use `Request` context to access these globals at runtime, enabling proper
lifespan management and test isolation.

### 9.2 SQLite Threading Model

- **Production (Phase 1):** SQLite connections use WAL mode (write-ahead logging) and
  are single-threaded. The Uvicorn process runs on a single thread.
- **Testing:** Connections use `check_same_thread=False` to allow async test execution
  via TestClient (which runs handlers in a thread pool). This is safe because each test
  is isolated and no concurrent writes occur.
- **Phase 2+:** If multi-worker scaling is needed, SQLite should be replaced with a
  multi-writer database (e.g., Postgres) as outlined in Phase 2 optional features.

---

## 10. Testing

The shipped API surface is covered by the integration suites under `tests/integration/api/`.

Relevant files include:
- `test_auth.py`
- `test_health.py`
- `test_staging.py`
- `test_audit_log.py`
- `test_config.py`
- `test_api_triage.py`
- `test_blocklist.py`

Test coverage includes:
- Auth validation (missing/invalid token → 401)
- Schema validation (response types, required fields)
- Pagination correctness (cursor advancement, item ordering)
- Action filtering (audit log `action` parameter)
- Redaction (api_token shown as `[redacted]` in config endpoint)
- No-auth endpoints (docs endpoints accessible without auth)
- Triage mutation idempotency and state transitions
- Blocklist CRUD and ingest-enforcement behavior

---

## 11. Related Documentation

- **Frontend integration:** [webui-architecture-phase1.md](webui-architecture-phase1.md) §7 (API Client Layer)
- **Database schema:** [design/specs/registry.md](../specs/registry.md)
- **Implementation roadmap:** [roadmaps/web-control-plane-phase1-implementation-roadmap.md](roadmaps/web-control-plane-phase1-implementation-roadmap.md) (Chunk 1 specification)

---

## 12. SPA Static Serving Contract (Chunk 3)

Static SPA assets are served by FastAPI from `webui/build` at `/`.

Fallback behavior for non-API routes is:
1. Serve requested file when present.
2. If route is not found, serve `200.html` when available.
3. If `200.html` is missing, serve `index.html`.

This preserves client-side routing for direct navigation to routes such as `/audit`
or `/staging`.

