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
    action       TEXT NOT NULL,       -- e.g. 'pending', 'accepted', 'rejected', 'purged', 'discard_accepted'
    reason       TEXT,
    details_json TEXT,
    actor        TEXT NOT NULL,       -- runtime actor label, e.g. 'ingest_pipeline', 'cli', 'trash_watch', 'api'
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
    source_relpath TEXT,
    hash_algo      TEXT NOT NULL,
    hash_value     TEXT NOT NULL,
    verified_sha256 TEXT,
    first_seen_at  TEXT NOT NULL,     -- ISO-8601 UTC
    updated_at     TEXT NOT NULL,     -- ISO-8601 UTC
    PRIMARY KEY (account_name, hash_algo, hash_value)
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
    action              TEXT NOT NULL,       -- e.g., 'triage_accept', 'blocklist_create', 'blocklist_update'
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
- **Advisory hash import / Hash import**: `external_hash_cache` stores hashes imported from the permanent library. The `hash-import` CLI command (Issue #65) imports authoritative SHA-256 hashes from `.hashes.v2` files directly into this table with `account_name='__hash_import__'`, `hash_algo='sha256'`, `hash_value=<sha256>`, `verified_sha256=<sha256>`, and `source_relpath=NULL`. The legacy `sync-import` command imported advisory SHA-1 hashes from `.hashes.sha1` files; the `verified_sha256` column was populated after first-download SHA-256 confirmation. The `hash-import` model eliminates the advisory layer by importing SHA-256 directly as canonical identity. Imported hashes do not create `files` rows, audit events, or lifecycle state. See [architecture/invariants.md](../architecture/invariants.md) §Hash Import Invariants (INV-HI01–INV-HI12).
- **`source_relpath` convention (hash-import)**: `source_relpath` MUST be `NULL` for hash-import entries. It MUST NOT contain file paths, directory paths, synthetic paths, or account-derived paths, because hash-import is hash-index seeding and must not imply file origin.

### Chunk 1/4/5 Optional Tables (Web Control Plane Phase 1)

**blocklist:**
- Stores operator-definable block rules for file filtering.
- Each rule has a pattern, type (`filename` or `regex` in the current implementation), human-readable reason, and enabled flag.
- Allows toggling rules on/off without deletion (audit trail in `updated_at`).
- Queried and mutated by `/api/v1/blocklist` GET/POST/PATCH/DELETE endpoints.
- Enforced by ingest in `domain/ingest.py` before unknown-file pending persistence.

**ui_action_idempotency:**
- Tracks write-path action idempotency keys (introduced in Chunk 4 triage and extended in Chunk 5 blocklist writes).
- Enables replay-safe semantics for triage operations and blocklist CRUD operations.
- Stores request body, response status, and response body for replay on duplicate key.
- Rows tagged with `expires_at` for garbage collection (TTL-based cleanup).
- Accessed by write services for replay/conflict checks; not exposed as a public API endpoint.

**Migration note:** Chunk 1 introduces these tables as additive optional tables under the
existing v2 runtime. Fresh databases receive them on `initialize()`, and existing valid
v2 databases also receive them idempotently on `initialize()`. The current runtime does
not treat these tables as a v2 -> v3 migration.

---

## Properties

| Action | Actor | Trigger |
|---|---|---|
| `pending` | `ingest_pipeline` | New file first ingested to pending queue |
| `accepted` | `cli` | Operator explicit accept |
| `rejected` | `cli` or `trash_watch` or `ingest_pipeline` | Operator explicit reject, trash flow, or blocklist ingest match |
| `purged` | `cli` | Operator explicit purge |
| `discard_accepted` | `ingest_pipeline` | File already `accepted`; discarded from staging |
| `discard_pending` | `ingest_pipeline` | File already `pending`; discarded from staging |
| `discard_rejected` | `ingest_pipeline` | File already `rejected` or blocklist-matched ingest; discarded from staging |
| `discard_purged` | `ingest_pipeline` | File already `purged`; discarded from staging |

---

*For the ingest decision engine that writes to this registry, see [ingest.md](ingest.md).*  
*For schema migration details, see [architecture/schema-and-migrations.md](../architecture/schema-and-migrations.md).*
