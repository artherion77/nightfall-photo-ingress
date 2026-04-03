# Ingest Lifecycle and Crash Recovery

Status: active
Created: 2026-04-03
Updated: 2026-04-03

---

## 1. Purpose

This document describes the staged ingest lifecycle for one `DownloadedHandoffCandidate`
and the mechanisms by which crash-interrupted operations are detected and resolved at
next startup.

It covers the `IngestOperationJournal` (JSONL crash-boundary log), the
`StagingDriftReport` reconciliation classification, zero-byte file policy, and the
relationship between the journal and the SQLite `audit_log`.

---

## 2. Lifecycle Overview

Each file that the OneDrive adapter downloads passes through a staged pipeline before
becoming a permanent registry entry:

```
OneDrive Graph API
    │
    ▼
[M3] Download to staging_path (adapter layer)
    │  phase: ingest_started
    │
    ▼
[M4] Size verification (optional)
    │  phase: size_mismatch → quarantine/discard
    │
    ▼
Zero-byte check
    │  policy: allow | quarantine | reject
    │
    ▼
Metadata prefilter (optional)
    │  known onedrive_id+metadata → skip SHA-256 hashing
    │
    ▼
SHA-256 hash computation
    │  phase: hash_completed
    │
    ▼
Registry policy decision
    │  unknown hash  → pending (move to pending_path)
    │  known hash    → discard (unlink staging file)
    │  phase: registry_persisted
    │
    ▼
SQLite commit + audit_log row
    │
    ▼
staging_path removed
```

The `IngestOperationJournal` appends a record at each named phase boundary. If the
process crashes between phases, the journal record at restart identifies where the
operation stopped.

---

## 3. IngestOperationJournal

### 3.1 Role

The journal is a per-run JSONL append-only file that records coarse phase transitions
for each ingest operation. It exists solely as a crash-boundary recovery mechanism.

It is complementary to — but separate from — the SQLite `audit_log`:

| Concern | IngestOperationJournal | audit_log |
|---------|----------------------|-----------|
| Scope | Per-operation phase markers, ephemeral | All state transitions, permanent |
| Format | JSONL on disk | SQLite rows |
| Retention | Cleared after successful replay | Append-only, never deleted |
| Purpose | Crash recovery / replay | Audit visibility |

### 3.2 File Location and Rotation

The journal path is configured via `journal_path` in the `[core]` config section.
If not set, the journal is disabled; crash recovery falls back to manual staging
reconciliation.

Rotation: when the journal file reaches `max_bytes` (default 5 MB), the active
file is renamed to `<path>.1` (overwriting any previous `.1`) and a new file begins.
Only one rotation file is retained.

### 3.3 Write Durability

Each `append()` call:
1. Serialises the payload to a compact JSON line (no whitespace, sorted keys).
2. Writes the line with a trailing `\n`.
3. Calls `handle.flush()` — flushes the Python buffer to the OS.
4. Calls `os.fsync(handle.fileno())` — ensures the write reaches durable storage
   before returning to the caller.

This ensures a crash immediately after `append()` returns still finds the record on
the next read.

### 3.4 Record Format

Each JSONL line is a JSON object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `op_id` | string | `<account>:<onedrive_id>:<12-hex-uuid>` — unique per operation |
| `phase` | string | Phase name (see §4) |
| `ts` | string | UTC ISO-8601 timestamp when the phase was recorded |
| `account` | string | Account name from config |
| `onedrive_id` | string | OneDrive item ID |
| `staging_path` | string | Absolute path of the staging file at time of recording |
| `destination_path` | string or null | Destination path (set from `hash_completed` onward) |
| `sha256` | string or null | SHA-256 hex digest (set from `hash_completed` onward) |

### 3.5 Parse Resilience

`read_all()` silently skips:
- Blank lines
- Lines that are not valid JSON
- Records missing `op_id` or `phase`

This ensures a partially-written final line (from a crash mid-write) does not
prevent reading all prior complete records.

---

## 4. Phase Sequence

The following phases are recorded in order for a successful ingest operation:

| Phase | Recorded when |
|-------|---------------|
| `ingest_started` | `_process_one()` begins; before any file I/O |
| `size_mismatch` | Size check fails; file quarantined or discarded |
| `missing_staged` | `staging_path` does not exist at processing time |
| `hash_completed` | SHA-256 computation finished; `sha256` field is set |
| `registry_persisted` | Registry row committed and staging file removed |

Phases `size_mismatch` and `missing_staged` are terminal (no `registry_persisted`
follows). The absence of `registry_persisted` on a non-discarded operation is the
recovery trigger condition.

Metadata prefilter hits do not produce journal records — they resolve before
`hash_completed` and discard the staging file with an `audit_log` entry only.

---

## 5. Crash Recovery

### 5.1 When Recovery Runs

`IngestDecisionEngine.replay_interrupted_operations()` is called once at startup,
before the first poll, if a journal path is configured.

### 5.2 Detection Logic

All journal records are grouped by `op_id`. For each group:
- If `registry_persisted` is present → operation completed successfully; skip.
- If `registry_persisted` is absent → operation was interrupted; recover.

### 5.3 Recovery Actions

For each interrupted operation (most-recent record used for path resolution):

1. **If `destination_path` exists on disk**: the file was moved out of staging but the
   registry row was not committed. The destination file is renamed to
   `<destination_path>.orphaned` and quarantined to prevent it from being treated as
   a permanent file. The quarantine count is incremented.
2. **If `staging_path` exists on disk**: the staging file is removed (the operation
   will be re-downloaded on the next poll). The removed count is incremented.
3. **If `sha256` is known and a registry row exists** for that hash: an audit event
   `recovery_interrupted_ingest` is appended to `audit_log`.

### 5.4 Journal Cleared After Replay

After processing all operations, `IngestOperationJournal.clear()` is called, which
deletes the active journal file. The next poll starts with a clean journal.

### 5.5 Safety Properties

- All downstream operations (registry upsert, audit append) use `ON CONFLICT DO UPDATE`
  or `INSERT OR IGNORE`, making recovery replay idempotent.
- If the process crashes again during recovery, the journal is not yet cleared, so the
  next startup re-runs recovery on the same records. This is safe.

---

## 6. StagingDriftReport

`reconcile_staging_drift()` scans the staging directory and classifies all files into
categories based on their age and suffix. It runs independently of the journal.

### 6.1 Classification

| Category | Condition | Default TTL |
|----------|-----------|-------------|
| `stale_temp` | `.tmp` suffix; age > `tmp_ttl_minutes` | Configurable |
| `completed_unpersisted` | Non-`.tmp`; age > `failed_ttl_hours` but < `orphan_ttl_days` | Configurable |
| `orphan_unknown` | Non-`.tmp`; age > `orphan_ttl_days` | Configurable |

Files that do not meet any age threshold are left in place.

### 6.2 Quarantine Behaviour

All classified files are moved to `quarantine_dir/<category>/<filename>`. If a file
with the same name already exists in the quarantine directory, an integer timestamp
suffix is appended to the quarantine filename.

### 6.3 StagingDriftReport Fields

| Field | Type | Meaning |
|-------|------|---------|
| `stale_temp_count` | int | Count of expired `.tmp` files moved to quarantine |
| `completed_unpersisted_count` | int | Files older than `failed_ttl_hours` |
| `orphan_unknown_count` | int | Files older than `orphan_ttl_days` |
| `quarantined_count` | int | Total files moved to quarantine this pass |
| `warnings` | tuple[str, ...] | Threshold-exceeded warning strings if counts ≥ `warning_threshold` |

Warning strings are formatted as `<category>_threshold_exceeded:<count>`.

---

## 7. Zero-Byte File Policy

Zero-byte files detected during ingest are handled according to the `zero_byte_policy`
config key (default: `allow`):

| Policy | Behaviour |
|--------|-----------|
| `allow` | File is processed normally; an empty SHA-256 hash is computed and the file is registered as pending. |
| `quarantine` | File is moved to `quarantine_dir/zero_byte/`; an `IngestOutcome` with action `quarantine_zero_byte` is returned; audit event appended. |
| `reject` | File is unlinked; an `IngestOutcome` with action `reject_zero_byte` is returned; no audit event. |

Zero-byte files are never silently discarded.

---

## 8. Relationship to SQLite audit_log

The journal and the `audit_log` table serve different purposes and must not be confused:

| | IngestOperationJournal | audit_log |
|-|----------------------|-----------|
| Written by | `IngestDecisionEngine._process_one()` | `Registry.append_audit_event()` |
| Written when | At each phase boundary during processing | After a successful registry commit |
| Deleted | After successful `replay_interrupted_operations()` | Never |
| Readable by | Recovery logic at next startup | Operator, reporting tools |
| Scope | One operation at a time | Full history of all state changes |

The `audit_log` is the authoritative record of what happened to a file. The journal is
a lightweight safety net that exists only to bridge the gap between a crash and the next
successful startup.
