# Fresh Registry Bootstrap Open Point

## Problem Statement

When the service starts against an empty registry (e.g. first run after a reinstall,
registry corruption recovery, or a deliberate `registry reset`), it has no knowledge of
files that already exist on disk. This leads to two classes of problem:

1. **Re-ingestion of already-accepted files** — files in `accepted/` and `rejected/`
   that were previously processed are treated as unknown and may be queued again on the
   next poll cycle, polluting the pending queue with duplicates.

2. **Loss of state metadata** — the registry records the authoritative SHA-256, the
   OneDrive item ID, the account association, the ingest timestamp, and the final state
   for every file. A blank registry loses all of this. Without it, deduplication cannot
   work correctly and audit trails are incomplete.

---

## Proposed Design

### Phase 1 — Disk scan at startup with fresh registry

On startup, if the registry is empty (or after an explicit bootstrap command), the
service should scan `media_root` and import all discoverable files into the registry
with their known state inferred from their location:

| Directory | Imported state |
|---|---|
| `accepted/` | `accepted` |
| `rejected/` | `rejected` |
| `trash/` | `trashed` |
| `pending/` | `pending` (re-queued for the accept/reject workflow) |

For each file found:
- Compute SHA-256 from the file on disk.
- Insert a registry row with: file path, SHA-256, inferred state, and a sentinel
  `onedrive_id = null` / `account = null` to mark metadata as pending enrichment.

This scan should be idempotent — running it on a partially-imported registry must not
create duplicates (match on SHA-256 or canonical path).

### Phase 2 — Metadata enrichment without re-download

On the next poll run after a bootstrap scan, when the service walks the OneDrive delta
for an account, it should recognise files already present in the registry by SHA-256
and:
- Backfill `onedrive_id`, `account`, and any missing metadata fields.
- **Not** re-download the file.
- Update the registry row's enrichment status to `complete`.

This requires the poll loop to cross-reference the file hash from the Graph API item
metadata (`file.hashes.sha256Hash`) against the registry before enqueuing a download.
The mechanism is similar to the existing `sync_hash_import` deduplication path and can
likely reuse parts of that logic.

---

## Design Phase Open Question — Advisory Hash Files in `media_root`

Evaluate whether to store SHA-256 sidecar files alongside accepted/rejected media,
analogous to the external library hash import mechanism (`sync_hash_import`).

**Arguments for:**
- Makes the registry fully reconstructable from disk alone, without a Graph API poll.
- Enables offline integrity verification of the media library.
- Consistent with the existing `.hashes.sha1` advisory hash pattern already supported.
- Simplifies the bootstrap scan: read hash sidecars instead of computing SHA-256 on
  every file at startup (potentially expensive for large libraries).

**Arguments against:**
- Adds write overhead on every accepted file (one extra file per media item).
- Increases directory entry count in the media pool.
- Sidecar files must be kept in sync; a partially-written or orphaned sidecar is
  misleading.
- Hash format versioning becomes a maintenance concern.

**Options to evaluate:**
1. Per-file sidecar (e.g. `IMG_1234.jpg.sha256`) written atomically alongside the file.
2. Aggregate hash manifest per directory (e.g. `.hashes.sha256` in each `{yyyy}/{mm}/`
   folder), appended on each new file — matches the existing SHA-1 model exactly.
3. No sidecars; bootstrap scan always recomputes SHA-256 on disk (simpler, slower).

This sub-question should be resolved before the bootstrap scan is designed in detail,
as the chosen approach determines the scan algorithm and the write path for accepted
files.

---

## Impact Assessment

### New capability / command

A `bootstrap-registry` (or `registry scan`) subcommand should be added to the CLI,
callable independently of `poll`. It should:
- Accept `--dry-run` to report what would be imported without writing.
- Emit structured log records and a status snapshot on completion.
- Be safe to run at any time, not only on an empty registry (idempotent).

### config.py / CoreConfig

- No new required config keys anticipated; `media_root` (see config-path-rework open
  point) is the scan root.
- If advisory hash sidecars are adopted, a config key controlling sidecar write
  behaviour will be needed (e.g. `write_sha256_sidecars = true|false`).

### Ingest / poll loop

- Cross-reference on SHA-256 before enqueuing download (already partially present in
  the `sync_hash_import` path — evaluate reuse).
- Backfill logic for rows with null `onedrive_id`.

### Registry schema

- New column(s) to track enrichment status (`metadata_complete: bool`) and bootstrap
  provenance (`bootstrapped_from_disk: bool`) may be needed.
- If schema changes, `config_version` and registry migration handling apply.

### design/cli-config-specification.md / architecture docs

- Document the bootstrap command, its scanning algorithm, and the enrichment lifecycle.

---

## Dependencies

- Config path rework open point (config-path-rework-open-point.md) — `media_root` base
  path is the scan root for this feature. The two open points should be resolved
  together or in sequence (path rework first).

---

## Open Questions

1. **Trigger** — automatic on startup when registry is empty, explicit CLI command, or
   both? Automatic behaviour risks surprises on operator misconfiguration.
2. **Hash sidecar format** — resolve the advisory hash design question before
   implementation (see Design Phase Open Question above).
3. **Large library performance** — for libraries with tens of thousands of files,
   SHA-256 recomputation at bootstrap may be slow. Evaluate whether to make it
   incremental / resumable.
4. **Pending files at bootstrap** — files found in `pending/` predate the registry wipe;
   their original ingest context is lost. Decide whether to re-enqueue them, move to
   `rejected/`, or quarantine for operator review.
5. **Cross-account ambiguity** — a file might match hashes from multiple accounts when
   OneDrive metadata is unavailable. Decide how to handle ambiguous account attribution
   at bootstrap time.

---

## Status

Open — not assigned, not scheduled.

Raised: 2026-04-03
