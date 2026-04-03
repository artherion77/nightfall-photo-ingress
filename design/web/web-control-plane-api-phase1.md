# Phase 1 REST API Specification

**Status:** Implemented (Chunk 1)  
**Date:** 2026-04-03  
**Owner:** Systems Engineering

---

## 1. Overview

This document specifies the Phase 1 REST API for the photo-ingress web control plane.
All endpoints are read-only in Phase 1. They provide operator access to:
- System health and status
- Pending ingestion queue with pagination
- Audit log with action filtering
- Effective runtime configuration
- Current blocklist rules

All endpoints require bearer token authentication (except docs endpoints).
Pagination uses cursor-based semantics with SHA-256 identifiers.

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
  "detail": "Invalid authentication credentials"
}
```

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
  polling_ok: boolean;      // Ingest poll cycle last completed without error
  auth_ok: boolean;          // OneDrive auth tokens valid
  registry_ok: boolean;      // SQLite registry accessible
  disk_ok: boolean;          // /nightfall ZFS pool and mount accessible
  last_updated_at: string;   // ISO-8601 UTC timestamp of last status update
  error: string | null;      // Error message if any subsystem failed; null if all ok
}
```

**Example:**

```bash
curl -H "Authorization: Bearer test-token-12345" \
  http://localhost:8000/api/v1/health
```

```json
{
  "polling_ok": true,
  "auth_ok": true,
  "registry_ok": true,
  "disk_ok": true,
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
Pagination uses SHA-256-based cursor semantics.

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
  cursor: string | null;    // Next cursor for pagination (sha256 of last item)
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
  cursor: string | null;    // Next cursor for pagination
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
    polling_interval_warning: number;
    pending_queue_warning: number;
    // ... other threshold values ...
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
    "pending_queue_warning": 100,
    "poll_runtime_warning_seconds": 300
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
  rule_type: string;        // E.g., 'filename', 'sha256', 'account'
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

### 4.7 API Documentation

**Path:** `GET /api/docs`

**Auth:** Not required

**Description:** Serve the RapiDoc interactive API documentation interface.
This is a self-contained HTML page with embedded OpenAPI spec.

**Response:** HTML page with RapiDoc component.

---

### 4.8 OpenAPI Schema

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
3. **Cursor format:** SHA-256 hash (for `/staging`) or numeric ID string (for `/audit-log`).
4. **Termination:** When `has_more` is `false`, no further pages exist.

### 5.2 Limit Parameter

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
| 500 | Server Error | Unexpected internal error |

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
| `ui_action_idempotency` | New: idempotency key tracking (Phase 3 write path) | v3 (Chunk 1) |

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

All Phase 1 endpoints are covered by the test suite: `tests/test_api_chunk1.py`.

Test coverage includes:
- Auth validation (missing/invalid token → 401)
- Schema validation (response types, required fields)
- Pagination correctness (cursor advancement, item ordering)
- Action filtering (audit log `action` parameter)
- Redaction (api_token shown as `[redacted]` in config endpoint)
- No-auth endpoints (docs endpoints accessible without auth)

---

## 11. Related Documentation

- **Frontend integration:** [webui-architecture-phase1.md](webui-architecture-phase1.md) §7 (API Client Layer)
- **Database schema:** [design/specs/registry.md](../specs/registry.md)
- **Implementation roadmap:** [planning/planned/web-control-plane-phase1-implementation-roadmap.md](../../planning/planned/web-control-plane-phase1-implementation-roadmap.md) (Chunk 1 specification)

