# Glossary and Naming Matrix

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §1.1  
**See also:** [domain/constraints.md](constraints.md), [domain-architecture-overview.md](../domain-architecture-overview.md)

---

## Canonical V2 Naming Matrix

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary name in docs, CLI, and operational language |
| Source adapter | `onedrive` | Current adapter; kept explicit in config and module names |
| Python package | `nightfall_photo_ingress` | Keeps namespace alignment with existing nightfall Python projects |
| CLI command | `nightfall-photo-ingress` | Main operational command (binary installed under `/opt/nightfall-photo-ingress/bin/`) |
| Config file | `/etc/nightfall/photo-ingress.conf` | Single versioned INI file |
| systemd units | `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`, `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service` | systemd-managed runtime inside the `photo-ingress` LXC container |
| SSD ZFS dataset (container) | `ssdpool/photo-ingress` | Always-on staging, cursors, token caches, registry |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Working set for low-latency operations |
| HDD ZFS dataset (container) | `nightfall/media/photo-ingress` | Queue/trash boundary on nightfall pool |
| HDD mountpoint | `/nightfall/media/photo-ingress` | `pending/`, `accepted/`, `rejected/`, and `trash/` live here |
| Permanent library root | `/nightfall/media/pictures` | Read-only to ingress, indexed by Immich |
| Health status file | `/run/nightfall-status.d/photo-ingress.json` | Exported each poll cycle |

---

## Domain Term Glossary

Terms are listed alphabetically. The **Owning module** column identifies the primary
source module that defines or owns the concept; `—` means the term is a configuration
or operational concept without a single owning file.

| Term | Definition | Owning module | Notes |
|---|---|---|---|
| **accepted** | Status value for a file that has been explicitly approved by the operator. The file resides in `accepted_path` awaiting manual operator move to the permanent library. | `domain/registry.py` | One of four valid `files.status` values. Written only by explicit CLI `accept` invocation. |
| **accepted_records** | Append-only SQLite table that records each explicit acceptance event. Never deleted. Preserves acceptance history even after the operator moves the file away from `accepted_path`. | `domain/registry.py` | A separate acceptance proof table independent of `files.current_path`. Keyed by `(id, sha256)`. |
| **account** | A named OneDrive account declared in the config file under `[account.<name>]`. Each account has its own token cache and delta cursor. | `config.py` | Accounts are processed serially in config file declaration order. |
| **audit_log** | Append-only SQLite table recording every state transition and pipeline event. Rows are protected against update and delete by DB-layer SQL triggers. | `domain/registry.py` | `actor` is set by runtime paths such as `ingest_pipeline`, `cli`, `trash_watch`, and `api`. |
| **config_version** | Required INI key (`config_version = 2`) in `[core]`. Any value other than `2` causes a startup abort. | `config.py` | The version 2 boundary marks the pending-first design and the clean registry bootstrap. No in-place upgrade from version 1 is supported. |
| **delta cursor** | Per-account checkpoint recording the last committed Graph API `deltaLink` (or `nextLink` within a page traversal). Enables incremental change enumeration from the last completed position. | `adapters/onedrive/client.py` | Stored as a plain-text file at `delta_cursor` path in config. Advanced only after page ingest side effects are durably committed. |
| **DownloadedHandoffCandidate** | Dataclass produced by the OneDrive adapter and passed to `IngestDecisionEngine` as the M3 → M4 boundary contract. Carries: `account_name`, `onedrive_id`, `original_filename`, `relative_path`, `modified_time`, `size_bytes`, `staging_path`. | `adapters/onedrive/client.py` | Ephemeral; not persisted. The domain layer accepts this as opaque input, enabling adapter extensibility. |
| **external_hash_cache** | SQLite table storing hashes imported from the permanent library. The `hash-import` CLI command (Issue #65) imports authoritative SHA-256 hashes from `.hashes.v2` files with `imported = true` and `source = "hash_import"`. For hash-import entries, `source_relpath` is `NULL` by convention and never implies file origin. Legacy `sync-import` imported advisory SHA-1 from `.hashes.sha1` files (deprecated). Used as a dedupe index for pre-download filtering. | `domain/registry.py` | Imported entries do not create `files` rows, audit events, or lifecycle state. See [architecture/invariants.md](../architecture/invariants.md) §Hash Import Invariants. |
| **file_origins** | SQLite table recording the `(account, onedrive_id) → sha256` provenance mapping for every OneDrive item ever encountered. Append-on-encounter; never deleted. | `domain/registry.py` | Tracks provenance independently of current status. Key: `(account, onedrive_id)`. |
| **IngestDecisionEngine** | Domain class that applies the hash-based policy matrix to a `DownloadedHandoffCandidate`. Determines outcomes such as `pending`, `discard_accepted`, `discard_rejected`, and `discard_purged`, and performs registry writes and queue transitions. | `domain/ingest.py` | Source-agnostic; works identically for any adapter. |
| **IngestOperationJournal** | Per-run JSONL append-only file that records coarse phase transitions (`ingest_started`, `hash_completed`, `registry_persisted`) for each ingest operation. Used as a crash-boundary recovery mechanism only. | `domain/journal.py` | Cleared after `replay_interrupted_operations()` completes successfully. Separate from and complementary to `audit_log`. |
| **live_photo_pairs** | SQLite table linking HEIC/JPEG photo component and MOV video component of an Apple Live Photo by shared stem and capture-time heuristic. Status follows the component files. | `domain/registry.py` | Pair detection is best-effort. Unpaired components are still processed independently. |
| **Live Photo** | An Apple Live Photo: a paired still image (HEIC or JPEG) and a short video (MOV) captured together. The two components share a common filename stem. | `domain/ingest.py`, `live_photo.py` | Tracked as two separate `files` entries linked by a `live_photo_pairs` row. |
| **metadata_index** | SQLite table caching OneDrive item metadata `(account_name, onedrive_id, size_bytes, modified_time, sha256)`. Used as a fast pre-filter to skip re-downloading unchanged items. | `domain/registry.py` | Key: `(account_name, onedrive_id)`. Written on first successful download. |
| **pending** | Status value for a file downloaded from OneDrive with an unknown SHA-256 that has been placed in the operator review queue. | `domain/registry.py` | One of four valid `files.status` values. The default outcome for a newly encountered file. |
| **permanent library** | The destination directory (`/nightfall/media/pictures`) where accepted files ultimately reside and are indexed by Immich. Read-only to the ingress service. | — | Files move to the permanent library via a manual operator step outside the ingress process. |
| **poll cycle** | One full execution of the ingest service: acquire token, fetch Graph API delta pages, evaluate and ingest each item, commit cursors, write status snapshot. Triggered by the systemd timer. | `adapters/onedrive/client.py`, `cli.py` | Bounded by `max_downloads_per_poll` and `max_poll_runtime_seconds`. |
| **process lock** | A non-blocking `fcntl` advisory file lock that ensures at most one poll run executes at a time. Acquired before poll start; released on exit. | `runtime/process_lock.py` | Prevents concurrent CLI and timer invocations from racing on the same registry. |
| **purged** | Status value for a previously rejected file whose physical copy has been deleted by an explicit `purge` CLI command. | `domain/registry.py` | One of four valid `files.status` values. Terminal status; no further transitions. |
| **registry** | The SQLite database (`registry.db`) that is the system-of-record for all file SHA-256 identities, status, history, and metadata. | `domain/registry.py` | Stored on SSD (`ssdpool/photo-ingress`). WAL mode. The authoritative truth for all operator and pipeline decisions. |
| **rejected** | Status value for a file explicitly rejected by the operator. The physical file is retained in `rejected_path` until an explicit `purge`. | `domain/registry.py` | One of four valid `files.status` values. Reject-once-reject-forever: a rejected SHA-256 is never re-ingested. |
| **Run-ID** | A UUID generated once per poll invocation and propagated to all log records, `ingest_terminal_audit` rows (`batch_run_id`), and the status snapshot. | `status.py`, `cli.py` | Enables cross-surface correlation: a single `run_id` links all journal lines, audit rows, and the status snapshot from one poll cycle. |
| **staging** | The temporary SSD directory (`/mnt/ssd/photo-ingress/staging/`) where files are downloaded from OneDrive before hashing and registry lookup. | `adapters/onedrive/client.py` | Files are written as `{onedrive_id}.tmp` and renamed on completion. The staging directory never contains permanent data. |
| **StagingDriftReport** | Dataclass returned by `reconcile_staging_drift()` classifying staging directory contents after a crash or interrupted poll: `stale_temp_count`, `completed_unpersisted_count`, `orphan_unknown_count`, `quarantined_count`. | `domain/ingest.py` | Reports warnings when counts exceed configured thresholds. |
| **hash import** | CLI command (`nightfall-photo-ingress hash-import`) that reads `.hashes.v2` files from the permanent library and seeds `external_hash_cache` with authoritative SHA-256 hashes to populate the dedupe index. Does not create staging items, audit events, or lifecycle state. Replaces the deprecated `sync-import` command. | `hash_import.py` | Offline, non-audit, non-UI-visible. Governed by 12 mandatory invariants (INV-HI01–INV-HI12). See [cli-config-specification.md](../cli-config-specification.md) §3. |
| **sync import** | *(deprecated)* CLI subcommand (`nightfall-photo-ingress sync-import`) that read `.hashes.sha1` files from the permanent library and seeded `external_hash_cache` with advisory SHA-1 hashes. Replaced by `hash-import` (Issue #65) which imports authoritative SHA-256 directly. | `sync_import.py` | Deprecated. SHA-1 advisory model required first-download SHA-256 verification, negating most download-reduction benefit. |
| **trash directory** | The filesystem path (`/nightfall/media/photo-ingress/trash/`) watched by the `nightfall-photo-ingress-trash.path` systemd unit. The operator drops files here to trigger the rejection flow. | — | The `.path` unit fires the trash service on new files; the service computes SHA-256 and applies the rejection transition. |

---

## Canonical Naming Conventions

This table shows how the `photo-ingress` service naming varies by context.

| Context | Name | Notes |
|---|---|---|
| Service / project | `photo-ingress` | Used in docs, config path, ZFS datasets, status file |
| CLI binary | `nightfall-photo-ingress` | Installed under `/opt/nightfall-photo-ingress/bin/`; carries `nightfall-` prefix matching all other nightfall tooling |
| systemd units | `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`, `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service` | All units carry the `nightfall-` prefix |
| SSD ZFS dataset | `ssdpool/photo-ingress` | Staging, registry, cursors, token caches |
| HDD ZFS dataset | `nightfall/media/photo-ingress` | Queue roots: `pending/`, `accepted/`, `rejected/`, `trash/` |

For the full canonical naming matrix, see the [Canonical V2 Naming Matrix](#canonical-v2-naming-matrix) above.

---

*For the complete domain constraints and derived invariants, see [constraints.md](constraints.md).*  
*For the system invariants catalogue, see [architecture/invariants.md](../architecture/invariants.md).*  
*For the pipeline architecture, see [architecture/data-flow.md](../architecture/data-flow.md).*
