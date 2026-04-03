# Registry Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §5  
**See also:** [specs/ingest.md](ingest.md), [architecture/storage-topology.md](../architecture/storage-topology.md), [architecture/schema-and-migrations.md](../architecture/schema-and-migrations.md)

---

## Overview

The registry is a SQLite database (`registry.db`) stored on the SSD dataset. It is the authoritative content ledger: every file SHA-256 identity and every state transition is recorded here. File paths stored in the registry are advisory; SHA-256 is the canonical identity key.

---

## Schema

**Current schema version:** v2 (`PRAGMA user_version = 2`)

Chunk 1 introduces web control plane support using additive optional tables created by
`_ensure_optional_tables()` on `initialize()`. These additions do not increment the
schema version in the current runtime.

**Core tables (schema version 2 — bootstrapped at first `initialize()` call):**

```sql
CREATE TABLE IF NOT EXISTS files (
    sha256            TEXT PRIMARY KEY,
    size_bytes        INTEGER NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected', 'purged')),
    original_filename TEXT,
    current_path      TEXT,           -- last known filesystem path (advisory; not canonical identity)
    first_seen_at     TEXT NOT NULL,  -- ISO-8601 UTC
    updated_at        TEXT NOT NULL   -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS metadata_index (
    account_name  TEXT NOT NULL,
    onedrive_id   TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    modified_time TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL,      -- ISO-8601 UTC
    updated_at    TEXT NOT NULL,      -- ISO-8601 UTC
    PRIMARY KEY (account_name, onedrive_id)
);

CREATE TABLE IF NOT EXISTS accepted_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256      TEXT NOT NULL,
    account     TEXT NOT NULL,
    source_path TEXT NOT NULL,        -- path at time of acceptance
    accepted_at TEXT NOT NULL,        -- ISO-8601 UTC
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS file_origins (
    account      TEXT NOT NULL,
    onedrive_id  TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    path_hint    TEXT,
    first_seen_at TEXT NOT NULL,      -- ISO-8601 UTC
    last_seen_at  TEXT NOT NULL,      -- ISO-8601 UTC
    PRIMARY KEY (account, onedrive_id),
    FOREIGN KEY (sha256) REFERENCES files(sha256)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256       TEXT,
    account_name TEXT,
    action       TEXT NOT NULL,       -- e.g. 'pending', 'accepted', 'rejected', 'purged', 'duplicate_skipped'
    reason       TEXT,
    details_json TEXT,
    actor        TEXT NOT NULL,       -- 'pipeline', 'cli', 'trash_watch'
    ts           TEXT NOT NULL        -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS live_photo_pairs (
    pair_id      TEXT PRIMARY KEY,
    account      TEXT NOT NULL,
    stem         TEXT NOT NULL,
    photo_sha256 TEXT NOT NULL,
    video_sha256 TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('paired', 'pending', 'accepted', 'rejected', 'purged')),
    created_at   TEXT NOT NULL,       -- ISO-8601 UTC
    updated_at   TEXT NOT NULL,       -- ISO-8601 UTC
    FOREIGN KEY (photo_sha256) REFERENCES files(sha256),
    FOREIGN KEY (video_sha256) REFERENCES files(sha256)
);
```

**External hash cache:**

```sql
CREATE TABLE IF NOT EXISTS external_hash_cache (
    account_name   TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    hash_algo      TEXT NOT NULL,
    hash_value     TEXT NOT NULL,
    verified_sha256 TEXT,
    first_seen_at  TEXT NOT NULL,     -- ISO-8601 UTC
    updated_at     TEXT NOT NULL,     -- ISO-8601 UTC
    PRIMARY KEY (account_name, source_relpath, hash_algo, hash_value)
);
```

**Audit log triggers (append-only enforcement at DB layer):**

```sql
CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(FAIL, 'audit_log is append-only');
END;
```

**Optional/additive tables (created by `_ensure_optional_tables()` on `initialize()`):**

```sql
CREATE TABLE IF NOT EXISTS ingest_terminal_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_run_id TEXT NOT NULL,
    sequence_no  INTEGER NOT NULL,
    account      TEXT NOT NULL,
    onedrive_id  TEXT NOT NULL,
    sha256       TEXT,
    action       TEXT NOT NULL,
    reason       TEXT,
    actor        TEXT NOT NULL,
    ts           TEXT NOT NULL        -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS blocked_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern      TEXT UNIQUE NOT NULL,
    rule_type    TEXT NOT NULL,       -- currently 'filename' or 'regex'
    reason       TEXT,
    enabled      INTEGER DEFAULT 1,   -- 0=disabled, 1=enabled
    created_at   TEXT NOT NULL,       -- ISO-8601 UTC
    updated_at   TEXT NOT NULL        -- ISO-8601 UTC
);

CREATE TABLE IF NOT EXISTS ui_action_idempotency (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key     TEXT UNIQUE NOT NULL,
    action              TEXT NOT NULL,       -- e.g., 'accept', 'reject', 'defer'
    item_id             TEXT NOT NULL,       -- SHA-256 or file identifier
    request_body_json   TEXT,                -- Full request body for audit/replay
    response_status     INTEGER NOT NULL,   -- HTTP status returned
    response_body_json  TEXT,                -- Response body for audit
    created_at          TEXT NOT NULL,      -- ISO-8601 UTC
    expires_at          TEXT NOT NULL       -- ISO-8601 UTC (TTL for garbage collection)
);
```

---

## Properties

- **Idempotent**: `INSERT OR IGNORE` / `ON CONFLICT DO UPDATE` on first insert; status transitions use `UPDATE` + audit append in one `BEGIN IMMEDIATE` transaction.
- **Auditable**: `audit_log` is append-only; enforcement is at the DB layer via SQL triggers (`trg_audit_log_no_update`, `trg_audit_log_no_delete`).
- **Concurrent-safe**: `BEGIN IMMEDIATE` transaction for all write paths; SQLite WAL mode enabled at first open.
- **Resilient to restarts**: staging files named `{onedrive_id}.tmp` during download → renamed on completion; a crashed run leaves `.tmp` files that are cleaned up on next start via `StagingDriftReport`.
- **Move-safe**: `accepted_records` preserves acceptance history even if files are manually moved out of `accepted/`.
- **Pending-first**: `accepted_records` is written only on explicit accept, never on unknown ingest.
- **Provenance-tracked**: `file_origins` records the `(account, onedrive_id)` → `sha256` mapping for every file ever encountered, independent of current status.
- **Advisory hash import**: `external_hash_cache` stores SHA1 hashes imported from `.hashes.sha1` files; `verified_sha256` column is populated after first-download SHA-256 confirmation, converting an advisory hint to a confirmed identity mapping.

### Chunk 1 Optional Tables (Web Control Plane Phase 1)

**blocklist:**
- Stores operator-definable block rules for file filtering.
- Each rule has a pattern, type (`filename` or `regex` in the current implementation), human-readable reason, and enabled flag.
- Allows toggling rules on/off without deletion (audit trail in `updated_at`).
- Queried by read-only `/api/v1/blocklist` endpoint.

**ui_action_idempotency:**
- Tracks write-path action idempotency keys (introduced in Phase 3 triage write path).
- Enables exactly-once semantics for triage operations (accept / reject / defer).
- Stores request body, response status, and response body for replay on duplicate key.
- Rows tagged with `expires_at` for garbage collection (TTL-based cleanup).
- Not queried by any API endpoint in Phase 1 (unused until Phase 3).

**Migration note:** Chunk 1 introduces these tables as additive optional tables under the
existing v2 runtime. Fresh databases receive them on `initialize()`, and existing valid
v2 databases also receive them idempotently on `initialize()`. The current runtime does
not treat these tables as a v2 -> v3 migration.

---

## Properties

| Action | Actor | Trigger |
|---|---|---|
| `pending` | `pipeline` | New file first ingested to pending queue |
| `accepted` | `cli` | Operator explicit accept |
| `rejected` | `cli` or `trash_watch` | Operator explicit reject or trash flow |
| `purged` | `cli` | Operator explicit purge |
| `duplicate_skipped` | `pipeline` | File already `accepted`; discarded from staging |
| `discard_pending` | `pipeline` | File already `pending`; discarded from staging |
| `rejected_duplicate` | `pipeline` | File already `rejected`; discarded from staging |

---

*For the ingest decision engine that writes to this registry, see [ingest.md](ingest.md).*  
*For schema migration details, see [architecture/schema-and-migrations.md](../architecture/schema-and-migrations.md).*
