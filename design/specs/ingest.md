# Ingest Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §6.1, §6.1.1, §6.3  
**See also:** [specs/registry.md](registry.md), [architecture/lifecycle.md](../architecture/lifecycle.md), [architecture/data-flow.md](../architecture/data-flow.md)

---

## Poll Cycle (8–24h production cadence via systemd timer)

1. Acquire OAuth2 token silently (MSAL refresh token flow).
2. Call Graph API delta endpoint for the configured OneDrive folder.
3. For each changed `file` item:
   a. **Metadata pre-filter**: look up `metadata_index` by `(account_name, onedrive_id, size, modified_time)`. If hit and SHA-256 is in `files`, skip — no download needed.
   b. **Download** file to `/mnt/ssd/photo-ingress/staging/{onedrive_id}.tmp` (streaming, chunked).
   c. Rename `.tmp` → `{onedrive_id}.{ext}` on success.
   c1. Each downloaded file is wrapped in a `DownloadedHandoffCandidate` record (the production-owned M3→M4 boundary contract: `account_name`, `onedrive_id`, `original_filename`, `relative_path`, `modified_time`, `size_bytes`, `staging_path`). The ingest engine processes these immediately within the same poll run.
   d. **Compute SHA-256** (streaming 64 KB chunks; never loads full file into memory). The lifecycle journal (`IngestOperationJournal`) records phase transitions (`download_started`, `hash_computed`, `decision_applied`, `finalized`) for crash-boundary recovery.
   e. **Blocklist enforcement (Chunk 5):**
      - evaluate enabled rules in `blocked_rules` (`filename` glob and `regex` patterns).
      - on match: delete staged file; persist file as `rejected`; append `rejected` audit event with reason `block_rule:<rule_type>:<pattern>`; return ingest outcome `discard_rejected`.
   f. **Registry lookup** (if not blocklist-rejected):
      - `rejected` → delete from staging; append `discard_rejected` to `audit_log`.
      - `pending`  → delete from staging; append `discard_pending` to `audit_log`.
      - `accepted` → delete from staging; append `discard_accepted` to `audit_log`.
      - `purged`   → delete from staging; append `discard_purged` to `audit_log`.
      - `unknown` → move to `pending/YYYY/MM/{filename}`; insert `files` row as `pending`; insert `metadata_index` row; append `pending` to `audit_log`.
4. Persist cursor checkpoints with a commit-gated streaming sequence per page:
   - fetch one page,
   - evaluate prefilter and ingest outcomes for that page,
   - commit registry/storage side effects,
   - then persist `nextLink` cursor for the next page.
5. On chain completion (`deltaLink` reached), persist the `deltaLink` as the committed cursor.

---

## Authoritative Cursor Commit Rule

The streaming page-commit model is authoritative. Cursor advancement is a commit acknowledgement, not a fetch acknowledgement.

- Never advance cursor before page ingest side effects are durable.
- If a poll run is interrupted before cursor advance, replaying the same page must be safe via registry idempotency.
- If interrupted after cursor advance, the next run resumes from the next page without missing committed work.

**Account execution rule:** Enabled accounts are processed serially in declaration order from the configuration file.

---

## Ingest Decision Matrix

| Registry state | Action |
|---|---|
| `blocked_match` | Delete from staging; persist as `rejected`; append `rejected` with block-rule reason |
| `rejected` | Delete from staging; append `discard_rejected` to `audit_log` |
| `pending` | Delete from staging; append `discard_pending` to `audit_log` |
| `accepted` | Delete from staging; append `discard_accepted` to `audit_log` |
| `purged` | Delete from staging; append `discard_purged` to `audit_log` |
| `unknown` | Move to `pending/YYYY/MM/{filename}`; insert `files`; insert `metadata_index`; append `pending` to `audit_log` |

Blocklist-matched outcomes are persisted as rejected records, so replayed ingest of the
same content continues to follow known-hash discard behavior and skips pending.

---

## Live Photo Support

- Pair detection is required in v2.
- Ingest tracks likely Live Photo components (e.g. HEIC/JPEG + MOV) as separate physical files.
- Pairing heuristics are configurable with current runtime defaults:
  - `live_photo_capture_tolerance_seconds = 3`
  - `live_photo_stem_mode = exact_stem`
  - `live_photo_component_order = photo_first`
  - `live_photo_conflict_policy = nearest_capture_time`
- The runtime currently supports only these validated defaults.
- Pair linkage metadata is persisted for audit and future tooling.
- Merge/export workflows are deferred beyond v2.0.

---

## Hash Import (Offline Dedupe Index Seeding — Issue #65)

The `hash-import` CLI command imports SHA-256 hashes from `.hashes.v2` files into the
registry dedupe index. This is an offline operation that does not interact with the
ingest pipeline, audit log, or any UI surfaces.

```bash
nightfall-photo-ingress hash-import /nightfall/media/pictures --stats
```

Key properties:

- Reads `.hashes.v2` files (produced by `nightfall-immich-rmdups.sh`) from the permanent library.
- Enforces v1/v2 cache precedence: valid v2 wins; missing v2 + existing v1 uses
   ephemeral v2-equivalent reconstruction; stale/invalid v2 forces full ephemeral
   recompute; v1 is never written and never consumed directly as canonical SHA-256 input.
- If `.hashes.v2` is missing, invalid, stale, or incomplete, it is recomputed
   before import using ephemeral in-memory hash computation (same format contract
   as `nightfall-immich-rmdups.sh`).
- Uses the exact `nightfall-immich-rmdups.sh` directory-hash algorithm
   (`find ... -printf '%f %s %T@\n' | LC_ALL=C sort | sha1sum | awk '{print $1}'`)
   with cache-file and `thumbs.db` exclusions.
- Imports only the SHA-256 column into the `external_hash_cache` table.
- Does not create `files` rows, audit events, staging items, or lifecycle state.
- Fully idempotent: duplicates and re-imports are silently skipped.
- Does not write to the permanent library; recompute results are transient.
- Imported hashes prevent future re-downloads of known content during ingest.

For the full hash-import specification (CLI options, input format, invariants, registry
semantics, error handling), see [cli-config-specification.md](../cli-config-specification.md) §3.

For the 12 mandatory hash-import invariants, see
[architecture/invariants.md](../architecture/invariants.md) §Hash Import Invariants.

### Deprecated: sync-import (Legacy)

The `sync-import` command is deprecated and replaced by `hash-import`. It imported
advisory SHA-1 hashes from `.hashes.sha1` files. The advisory SHA-1 model required a
first-download SHA-256 verification before imported hashes could gate future skips,
negating most of the download-reduction benefit. The `hash-import` command imports
authoritative SHA-256 hashes directly, eliminating the advisory layer.

See [rationale/deprecated-concepts.md](../rationale/deprecated-concepts.md) for the
full deprecation record.

---

## Throughput Bounds

Two soft bounds prevent unbounded poll run duration:

- `max_downloads_per_poll`: when the per-run download count reaches this limit, the current page is committed and the poll terminates cleanly. Cursor advances to last committed page; next run resumes from there.
- `max_poll_runtime_seconds`: wall-clock timeout. Same clean-commit behaviour applies.

Neither bound raises an exception; both result in an orderly, auditable stop.

---

*For the full registry schema written by the ingest engine, see [registry.md](registry.md).*  
*For crash-recovery journal mechanics, see [architecture/lifecycle.md](../architecture/lifecycle.md).*
