# System Invariants Catalogue

**Status:** active  
**Sources:** `design/domain/constraints.md`, `design/domain-architecture-overview.md` §3 and §5, `design/architecture/ingest-lifecycle-and-crash-recovery.md`, `design/specs/registry.md`, `design/architecture/lifecycle.md`  
**See also:** [domain/constraints.md](../domain/constraints.md), [specs/registry.md](../specs/registry.md)

---

## Purpose

This document is the single authoritative catalogue of system invariants for
photo-ingress. An *invariant* is a property that the implementation must maintain at
all times, across all code paths, including crash recovery and operator-CLI paths.

Invariants are grouped by subsystem. Each entry carries an ID, a statement, the
enforcement mechanism, and a traceable source citation.

---

## Invariant Categories

- [Registry Invariants](#registry-invariants)
- [Storage Invariants](#storage-invariants)
- [Staging Invariants](#staging-invariants)
- [Audit Log Invariants](#audit-log-invariants)
- [Configuration Invariants](#configuration-invariants)
- [Process Model Invariants](#process-model-invariants)
- [Hash Import Invariants](#hash-import-invariants)

---

## Registry Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-R01 | SHA-256 is the canonical content identity — never a filename, path, or SHA-1 | `files` table | `sha256 TEXT PRIMARY KEY`; imported hashes from `hash-import` use SHA-256 directly as canonical identity; legacy advisory SHA-1 entries from `external_hash_cache` are never promoted to canonical status without a verified server-side SHA-256 | `design/domain-architecture-overview.md` §5; `design/architecture/ingest-lifecycle-and-crash-recovery.md` §10.3; `design/cli-config-specification.md` §3 |
| INV-R02 | `files.status` is constrained to `('pending', 'accepted', 'rejected', 'purged')` | `files` table | `CHECK (status IN ('pending', 'accepted', 'rejected', 'purged'))` SQLite constraint | `design/domain-architecture-overview.md` §5 |
| INV-R03 | A file in `rejected` status cannot be re-accepted — there is no `rejected → accepted` transition | `files.status` | `accept` CLI requires current status `pending`; `rejected` files are never re-entered into the pending queue | `design/domain-architecture-overview.md` §3 ("Reject-once, reject-forever") |
| INV-R04 | A rejected SHA-256 encountered again on any future poll is silently discarded with `discard_rejected` semantics — never re-entered into `pending` | `domain/ingest.py` | Registry lookup before persistence; rejected hit deletes staged file and appends discard audit record | `design/specs/ingest.md`; `design/architecture/state-machine.md` |
| INV-R05 | `accepted_records` preserves acceptance history independent of current file location | `accepted_records` table | Separate table written once on `accept`; never modified by file moves; populated even after operator relocates file | `design/domain-architecture-overview.md` §3 ("Accepted-history persistence"); §7 |
| INV-R06 | All registry write paths execute under a `BEGIN IMMEDIATE` transaction — no partial writes | all write paths in `domain/registry.py` | Every mutating method opens `BEGIN IMMEDIATE`; WAL mode enabled at first `initialize()` call | `design/domain-architecture-overview.md` §5 ("Concurrent-safe") |
| INV-R07 | All registry writes use `INSERT OR IGNORE` / `ON CONFLICT DO UPDATE` guards — idempotent under repeated execution and crash replay | all write paths | Explicit upsert guards on every `INSERT` site; crash recovery replay is safe by construction | `design/domain-architecture-overview.md` §3 ("Idempotent") |
| INV-R08 | `pending` → `accepted` requires explicit operator invocation — there is no automatic unknown-to-accepted transition | `domain/ingest.py` | `IngestDecisionEngine` emits `pending` for unknown hashes; explicit transitions are via CLI/API write paths | `design/domain-architecture-overview.md` §3 ("Explicit acceptance"); DEC-20260402-01 |
| INV-R09 | Enabled blocklist matches are persisted as `rejected` during ingest and returned as `discard_rejected` outcomes | `domain/ingest.py` | `_match_block_rule()` check runs before unknown-file persistence; matching files are marked rejected with block-rule reason | `design/specs/blocklist.md`; `design/specs/ingest.md` |

---

## Storage Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-S01 | `pending_path`, `accepted_path`, `rejected_path`, and `trash_path` must be four distinct filesystem paths | `config.py` | Startup validation aborts with a clear error if any two paths are equal or one is a prefix of another | `design/domain-architecture-overview.md` §6.6 |
| INV-S02 | Any `files.current_path` that lies outside the managed queue roots is treated as an operator error | `domain/storage.py` | Accept/reject flows fail closed on out-of-root `current_path` values; no silent move | `design/domain-architecture-overview.md` §6.6 |
| INV-S03 | `purge` requires the target file to be in `rejected` status — no other status allows purge | `reject.py` | Status check precedes any filesystem operation; purge fails closed on non-`rejected` files | `design/domain-architecture-overview.md` §6.5 |
| INV-S04 | `purge` refuses to delete files whose path lies outside the `rejected_path` root | `reject.py` | Root-containment safety check is performed before `unlink`; path-traversal-safe | `design/domain-architecture-overview.md` §6.5 |
| INV-S05 | The permanent library (`/nightfall/media/pictures`) is read-only to the ingress service — no write path crosses this boundary | all modules | No write call site targets the permanent library path; `hash-import` reads `.hashes.v2` files but never writes to the permanent library | `design/domain-architecture-overview.md` §1, §3 |
| INV-S06 | HDD writes occur only on queue transitions (`pending/`, `accepted/`, `rejected/`) — all pre-transition work (staging, hashing, registry) uses SSD | `domain/storage.py`, `domain/registry.py` | Staging directory is on `ssdpool/photo-ingress`; HDD is accessed only for final queue moves | `design/domain-architecture-overview.md` §3 ("Minimize unnecessary I/O") |
| INV-S07 | Cross-pool moves (SSD staging → HDD queue) use copy-verify-unlink when `staging_on_same_pool = false` — rename is used only when both ends are on the same pool | `domain/storage.py` | `staging_on_same_pool` config flag gates the move strategy; cross-pool copies are verified by content hash before unlink | `design/domain-architecture-overview.md` §7 ("Cross-pool atomic move") |

---

## Staging Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-ST01 | Downloaded files are named `{onedrive_id}.tmp` during transfer and renamed to `{onedrive_id}.{ext}` on completion — a final filename is never assigned until the download is complete | `adapters/onedrive/client.py` | `.tmp`-suffix convention; rename called only after successful response consumption | `design/domain-architecture-overview.md` §5 ("Resilient to restarts") |
| INV-ST02 | Zero-byte files are never silently discarded — they are processed, quarantined, or explicitly rejected per `zero_byte_policy` with an audit record in every case | `domain/ingest.py` | `zero_byte_policy` branch always produces a classified `IngestOutcome`; quarantine and reject paths both write audit records | `design/architecture/ingest-lifecycle-and-crash-recovery.md` §7 |
| INV-ST03 | Cursor is advanced only after all ingest side effects for the current page are durably committed to the registry — never before | `adapters/onedrive/client.py` | Page-commit sequence: fetch one page → evaluate → commit registry/storage → advance `nextLink` cursor | `design/domain-architecture-overview.md` §6.1, §6.1.1 |
| INV-ST04 | Metadata pre-filter hits (known `(account_name, onedrive_id, size, modified_time)`) never trigger a download — they produce a `discard` outcome with an audit record | `domain/ingest.py` | Pre-filter path returns before any staging write; audit entry records the skip | `design/domain-architecture-overview.md` §6.1 step 3a |

---

## Audit Log Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-A01 | Every state transition for a file produces an `audit_log` row within the same `BEGIN IMMEDIATE` transaction as the status change | `domain/registry.py` | Audit append and status update share a transaction; no state change is committed without an audit row | `design/domain-architecture-overview.md` §3 ("Auditable") |
| INV-A02 | `audit_log` rows are never updated | `audit_log` table | SQL trigger `trg_audit_log_no_update` raises `FAIL` on any `UPDATE` attempt at the DB layer | `design/domain-architecture-overview.md` §5 |
| INV-A03 | `audit_log` rows are never deleted | `audit_log` table | SQL trigger `trg_audit_log_no_delete` raises `FAIL` on any `DELETE` attempt at the DB layer | `design/domain-architecture-overview.md` §5 |
| INV-A04 | `actor` values in `audit_log` are controlled by runtime write paths (`ingest_pipeline`, `cli`, `trash_watch`, `api`) and are never client-provided free text | `audit_log.actor` | Actor values are set by server-side call sites only; API payloads do not set actor | `design/specs/triage.md`; `design/specs/blocklist.md` |

---

## Configuration Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-C01 | `config_version = 2` is mandatory — the runtime aborts at startup if any other value is present | `config.py` | Explicit `config_version` validation in startup; error message directs operator to bootstrap a fresh config | `design/domain-architecture-overview.md` §3 ("Legacy-free v2 boundary"), §6.6 |
| INV-C02 | Pre-v2 registries are never upgraded in place — a fresh `registry.db` at schema version 2 must be bootstrapped for new deployments | `domain/registry.py` | `initialize()` creates schema v2 tables only; no migration code for v1 → v2 exists | `design/domain-architecture-overview.md` §6.6 |
| INV-C03 | Enabled accounts are processed in config file declaration order — the runtime does not sort or reorder them | `cli.py` / poll orchestration | Config parser preserves insertion order; poll loop iterates in that order | `design/domain-architecture-overview.md` §6.1.1; DEC-20260331-04 |
| INV-C04 | Token cache and delta cursor file paths must be unique per account | `config.py` | Startup validation checks for per-account uniqueness; shared paths abort startup | `design/domain-architecture-overview.md` §11 |
| INV-C05 | UI mutation retries are replay-safe across triage and blocklist write paths via `ui_action_idempotency` | API write services | Mutations require `X-Idempotency-Key`; duplicate matching keys replay response; conflicting reuse is rejected with `409` | `design/specs/triage.md`; `design/specs/blocklist.md` |

---

## Process Model Invariants

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-P01 | At most one poll run executes concurrently across CLI and timer paths | `runtime/process_lock.py` | `fcntl` non-blocking advisory file lock acquired before poll start; a locked state causes an immediate logged abort | `design/domain-architecture-overview.md` §7 ("Concurrent poll runs") |
| INV-P02 | The lifecycle journal is cleared only after `replay_interrupted_operations()` completes successfully — if a crash occurs during replay, the journal is not cleared and replay repeats on next startup | `domain/journal.py` | `clear()` (`os.unlink`) is called at the end of the replay method, after all recovery actions | `design/architecture/ingest-lifecycle-and-crash-recovery.md` §5.4 |
| INV-P03 | The domain layer never imports from `adapters/` — dependency direction is one-way: adapters depend on domain, not vice versa | all modules | Import discipline; CI runs domain unit tests in an environment that has no MSAL or httpx installed | `ARCHITECTURE.md`; DEC-20260403-02 |
| INV-P04 | Auth failures are counted per poll run; after ≥3 consecutive failures the run is stopped and a status snapshot with `state = "auth_failed"` is written | `adapters/onedrive/auth.py`, `status.py` | `auth_failure_threshold` config key governs the limit; counter is not persisted across runs | `design/domain-architecture-overview.md` §15 ("Auth resilience threshold") |

---

---

## Hash Import Invariants

These invariants govern the `hash-import` command (Issue #65). They define strict
boundary separation between offline hash import and all ingest/audit/lifecycle
subsystems. In case of conflict with other design statements, these invariants
take precedence.

| ID | Invariant | Scope | Enforcement | Source |
|---|---|---|---|---|
| INV-HI01 | Imported hashes MUST NOT create staging items | `hash_import` module | No staging write path exists in hash-import code; only `external_hash_cache` INSERT | Issue #65 invariant 1 |
| INV-HI02 | Imported hashes MUST NOT create audit events of any kind | `hash_import` module | No `audit_log` write call in the hash-import code path | Issue #65 invariant 2 |
| INV-HI03 | Imported hashes MUST NOT enter or modify the ingest lifecycle (pending/accepted/rejected) | `hash_import` module | No `files` table write in hash-import; imported entries have no `files.status` | Issue #65 invariant 3 |
| INV-HI04 | Imported hashes MUST NOT participate in live-photo-pair detection | `hash_import` module | Hash-import does not invoke pairing logic; no EXIF or stem analysis | Issue #65 invariant 4 |
| INV-HI05 | Imported hashes MUST NOT trigger thumbnail generation or any media pipeline | `hash_import` module | No thumbnail or media processing calls in hash-import | Issue #65 invariant 5 |
| INV-HI06 | Imported hashes MUST be fully idempotent — duplicates, overlaps, and re-imports produce no errors or state changes | `hash_import` module | `INSERT OR IGNORE` semantics; duplicate hashes silently skipped | Issue #65 invariant 6 |
| INV-HI07 | Imported hashes MUST NOT overwrite or mutate existing registry entries | `hash_import` module | `INSERT OR IGNORE` with no `ON CONFLICT DO UPDATE` for existing entries | Issue #65 invariant 7 |
| INV-HI08 | Imported hashes MUST NOT modify or influence the OneDrive delta token or ingest cursor | `hash_import` module | No cursor or delta-token read/write in hash-import; operates on `external_hash_cache` only | Issue #65 invariant 8 |
| INV-HI09 | Imported hashes MUST NOT appear in any UI surfaces that represent ingest state (Dashboard, Staging, Audit Preview) | `hash_import` module, API layer | API queries filter on `files` table or `audit_log`; imported entries live in `external_hash_cache` which is not surfaced in UI | Issue #65 invariant 9 |
| INV-HI10 | Imported hashes MUST NOT infer or assign account ownership — account MUST remain null | `hash_import` module | No `account_name` field set; `external_hash_cache` entries have no account association | Issue #65 invariant 10 |
| INV-HI11 | Imported hashes MUST NOT participate in EXIF-based heuristics (timestamps, orientation, pairing, clustering) | `hash_import` module | No EXIF processing in hash-import; SHA-256 is the only data extracted from `.hashes.v2` | Issue #65 invariant 11 |
| INV-HI12 | Imported hashes MUST NOT be eligible for reject/purge operations or any file-based lifecycle actions | `hash_import` module | reject/purge CLI commands operate on `files.status`; imported entries have no `files` row | Issue #65 invariant 12 |

---

*For the design constraints that these invariants are derived from, see [domain/constraints.md](../domain/constraints.md).*  
*For the full registry schema that enforces structural invariants, see [specs/registry.md](../specs/registry.md).*  
*For the lifecycle journal behaviour, see [architecture/lifecycle.md](lifecycle.md).*  
*For the hash-import CLI specification, see [cli-config-specification.md](../cli-config-specification.md) §3.*
