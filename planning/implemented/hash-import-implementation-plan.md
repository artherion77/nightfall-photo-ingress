# Hash Import (Issue #65) — Implementation Plan

Status: Implemented
Date: 2026-04-12
Completed: 2026-04-12
Owner: Systems Engineering
Issue: #65

---

## Overview

This plan implements the `hash-import` CLI command for nightfall-photo-ingress.
The command imports authoritative SHA-256 hashes from `.hashes.v2` files in the
permanent library into the `external_hash_cache` table to populate the dedupe
index. This prevents re-downloads during ingest without creating staging items,
audit events, lifecycle state, or UI-visible entries.

The work is divided into 9 sequential chunks (H1–H9). Each chunk has explicit
scope, acceptance criteria, STOP gates, and validation steps. Chunks are ordered
by dependency: schema first, then parser, then insert logic, then integration
with CLI and config, then tests, then doc sync.

Authoritative sources:
- `design/cli-config-specification.md` §3 (CLI specification)
- `design/architecture/invariants.md` INV-HI01–INV-HI12 (12 invariants)
- GitHub Issue #65 (requirements and invariant block)

---

## H1 — Schema

Scope:
- Add a new migration to extend `external_hash_cache` with support for
  `source = "hash_import"` entries that use SHA-256 as canonical identity.
- The hash-import path stores entries with `hash_algo = "sha256"`,
  `hash_value = <64-char-hex>`, `account_name = "__hash_import__"` (sentinel
  value; account MUST remain unassigned per INV-HI10).
- Hash-import entries MUST persist `source_relpath = NULL`.
- `source_relpath` MUST NOT store file paths, directory paths, synthetic
  identifiers, or account-derived paths.
- Evaluate whether the existing `external_hash_cache` schema is sufficient
  or whether a dedicated table or column additions are needed. The existing
  schema has columns: `account_name`, `source_relpath`, `hash_algo`,
  `hash_value`, `verified_sha256`, `first_seen_at`, `updated_at`.
- Decision: if the existing schema can hold `hash_import` entries via the
  `hash_algo = "sha256"` + sentinel account_name convention, no migration is
  needed. Document the decision either way.

Acceptance criteria:
1. Hash-import entries can be inserted into `external_hash_cache` without
   schema errors.
2. Hash-import entries are distinguishable from legacy sync-import entries
   by `hash_algo` and/or `account_name` value.
3. Existing sync-import entries are not affected.
4. `INSERT OR IGNORE` semantics work correctly for duplicate SHA-256 values.
5. `source_relpath` is always `NULL` for hash-import entries.

STOP gates:
1. Do not proceed if the schema change breaks any existing migration sequence.
2. Do not proceed if hash-import entries are stored in the `files` table
   (violates INV-HI03).
3. Do not proceed if `account_name` is set to a real account value
   (violates INV-HI10).
4. Do not proceed if any hash-import row stores a non-NULL `source_relpath`.

Validation:
- Unit test: insert hash-import entry, verify round-trip read.
- Unit test: insert duplicate, verify no error and no state change (INV-HI06).
- Unit test: insert hash-import entry, verify existing sync-import entry is
  not modified (INV-HI07).
- Unit test: verify `source_relpath IS NULL` for all hash-import inserted rows.

Cross-references:
- `design/architecture/schema-and-migrations.md`
- `design/architecture/invariants.md` INV-HI06, INV-HI07, INV-HI10
- `design/cli-config-specification.md` §3.10 (`source_relpath` convention)
- `src/nightfall_photo_ingress/domain/registry.py` (schema DDL, upsert method)

Status: Implemented

---

## H2 — Parser

Scope:
- Implement `.hashes.v2` file parser in a new module
  `src/nightfall_photo_ingress/hash_import.py`.
- The parser reads a `.hashes.v2` file and yields validated SHA-256 hashes.
- Validation rules (from CLI spec §3.4):
  1. Line 1 MUST be exactly `CACHE_SCHEMA v2`.
  2. Line 2 MUST match `DIRECTORY_HASH <40-hex>`.
  3. Each subsequent line: 3 tab-separated fields, valid 40-char hex SHA-1 in
     column 1, valid 64-char hex SHA-256 in column 2, non-empty path in column 3.
- Only the SHA-256 column is extracted for import. Path and SHA-1 are validated
  but not stored.
- Invalid files are rejected entirely — no partial consumption (CLI spec §3.4).
- The parser does NOT perform directory-hash freshness checks (that is a
  separate concern for H4).

Acceptance criteria:
1. Valid `.hashes.v2` file yields correct SHA-256 list.
2. Missing `CACHE_SCHEMA v2` header raises parse error.
3. Invalid `DIRECTORY_HASH` line raises parse error.
4. Malformed data rows (wrong field count, invalid hex, empty path) raise
   parse error with line number.
5. Empty file (header only, no data rows) returns empty list without error.

STOP gates:
1. Do not proceed if the parser writes to any file or database.
2. Do not proceed if the parser extracts or stores the path column.
3. Do not proceed if the parser uses SHA-1 as a canonical identity.

Validation:
- Unit test: parse valid `.hashes.v2` file fixture.
- Unit test: parse file with missing header → error.
- Unit test: parse file with invalid SHA-256 hex → error with line number.
- Unit test: parse file with fewer than 3 fields → error.
- Unit test: parse empty data section → empty result.

Cross-references:
- `design/cli-config-specification.md` §3.4 (format spec)
- Issue #65 comment: §6 Hash Import Input Format

Status: Implemented

---

## H3 — Idempotent Insert

Scope:
- Add a `bulk_insert_hash_import` method to `Registry` that accepts a list of
  SHA-256 hashes and inserts them into `external_hash_cache` with `INSERT OR
  IGNORE` semantics.
- Batch size controlled by `chunk_size` parameter.
- Each batch is a single transaction.
- Returns per-chunk statistics: `imported`, `skipped_existing`.
- No writes to `files`, `audit_log`, `staging`, or any other table
  (INV-HI01, INV-HI02, INV-HI03).
- No call to pairing logic, thumbnail pipeline, EXIF processing, or delta
  token (INV-HI04, INV-HI05, INV-HI08, INV-HI11).
- Existing entries MUST NOT be overwritten or mutated (INV-HI07):
  `INSERT OR IGNORE` without `ON CONFLICT DO UPDATE`.

Acceptance criteria:
1. Bulk insert of N hashes creates N rows in `external_hash_cache`.
2. Re-insert of same hashes creates 0 new rows, 0 errors (INV-HI06).
3. Overlapping import (partial new, partial existing) inserts only new rows.
4. No rows appear in `files`, `audit_log`, or `staging` tables.
5. Per-chunk statistics are accurate.
6. Transaction isolation: failed chunk does not corrupt previous chunks.

STOP gates:
1. Do not proceed if any write targets a table other than `external_hash_cache`.
2. Do not proceed if `ON CONFLICT DO UPDATE` is used for hash-import entries.
3. Do not proceed if batch operations modify the delta token or ingest cursor.

Validation:
- Unit test: bulk insert 10 hashes → 10 imported, 0 skipped.
- Unit test: bulk insert 10 hashes twice → second call: 0 imported, 10 skipped.
- Unit test: bulk insert with chunk_size=3 → correct chunk boundaries.
- Unit test: verify `files` table row count unchanged after import.
- Unit test: verify `audit_log` row count unchanged after import.

Cross-references:
- `design/cli-config-specification.md` §3.7 (idempotency)
- `design/architecture/invariants.md` INV-HI01–INV-HI12
- `src/nightfall_photo_ingress/domain/registry.py`

Status: Implemented

---

## H4 — Dedupe Index and Directory Walking

Scope:
- Implement directory tree walker in `hash_import.py` that finds all
  `.hashes.v2` files under the given `<path-to-root>`.
- For each `.hashes.v2` file: parse (H2), then bulk-insert (H3).
- Directory hash freshness: if `DIRECTORY_HASH` does not match the current
  directory listing hash, the file is stale and MUST be recomputed before use
  (per CLI spec §3.4).
- v1/v2 precedence MUST be enforced:
  1. valid `.hashes.v2` -> use v2
  2. `.hashes.v2` exists and v1 missing -> do not create v1
  3. v2 missing and v1 exists -> reconstruct v2-equivalent rows ephemerally
  4. both missing -> full recompute
  5. v2 stale/invalid -> full recompute
  6. v1 never consumed directly as canonical SHA-256 import input
  7. v1 never written by photo-ingress
- Recompute requirement is mandatory for all invalid cache states. If a
  `.hashes.v2` file is missing, invalid, stale, partially corrupted, or missing
  required rows, hash-import MUST recompute the cache before using it.
- Recompute must follow the `nightfall-immich-rmdups.sh` cache format contract:
  enumerate files and compute SHA-1 + SHA-256 using the same directory-hash
  algorithm semantics, but keep recompute ephemeral in memory.
- Directory hash MUST match the exact script algorithm
  (`find ... -printf '%f %s %T@\n' | LC_ALL=C sort | sha1sum | awk '{print $1}'`)
  with cache-file and `thumbs.db` exclusions.
- Aggregate statistics across all directories.
- The walker MUST NOT write to the permanent library. Recompute is ephemeral only.

Acceptance criteria:
1. Walker discovers all `.hashes.v2` files in a directory tree.
2. Valid cache files are parsed and imported.
3. Stale cache files (mismatched directory hash) are recomputed and then imported.
4. Invalid cache files are recomputed and then imported.
5. Aggregate statistics sum correctly across directories.
6. No files are written to the library tree; recomputed rows are transient and
  used for the current import only.
7. v1 backfill semantics are enforced exactly (no v1 writes, no direct v1
  canonical SHA-256 import usage).

STOP gates:
1. Do not proceed if stale or invalid files are consumed without recompute.
2. Do not proceed if recompute writes any file to the permanent library.
3. Do not proceed if directory hash computation uses a different algorithm
   than `nightfall-immich-rmdups.sh`.
4. Do not proceed if v1 cache is written or consumed directly as canonical
  SHA-256 import input.

Validation:
- Unit test: walker on fixture tree with 3 directories, 2 valid + 1 stale;
  stale directory cache is recomputed then imported.
- Unit test: walker on empty directory → no errors, zero stats.
- Unit test: walker on directory with no `.hashes.v2` → ephemeral recompute is
  performed, then imported, with no filesystem writes.
- Unit test: v2 missing + v1 present -> v2-equivalent rows reconstructed
  ephemerally and imported.
- Unit test: v2 present + v1 missing -> import uses v2 and does not create v1.
- Integration test: walker on temp tree with known content → correct stats.

Cross-references:
- `design/cli-config-specification.md` §3.4.3 (directory hash semantics)
- `design/cli-config-specification.md` §3.4.4 (v1/v2 precedence)
- `design/cli-config-specification.md` §3.4.5 (exact directory hash algorithm)
- `design/cli-config-specification.md` §3.4.6 (ephemeral recompute)
- `design/architecture/storage-topology.md` (permanent library read-only boundary)
- `design/architecture/invariants.md` INV-S05

Status: Implemented

---

## H5 — Logging and Output

Scope:
- Implement structured JSON logging for hash-import operations using the
  existing `logging_bootstrap` infrastructure.
- Standard mode output per CLI spec §3.5:
  ```
  [chunk 1] imported=998 skipped_existing=2 duration=0.12s
  [chunk 2] imported=1000 skipped_existing=0 duration=0.11s
  DONE: total_imported=1998 total_skipped=2
  ```
- Dry-run output: `DRY RUN: total=2000 new=1998 existing=2`
- Quiet mode: only errors printed.
- Stats mode: per-chunk statistics.
- Error output per CLI spec §3.6: line-level errors with file context.
- All log records include fields: `command="hash-import"`, `chunk_index`,
  `imported`, `skipped_existing`, `duration`.
- `--stats` semantics MUST reflect recompute-aware counters from in-memory
  processing, not cache-file presence.

Acceptance criteria:
1. Standard mode prints per-chunk and summary lines.
2. Dry-run mode prints summary without database writes.
3. Quiet mode suppresses non-error output.
4. Stats mode prints per-chunk details.
5. Error messages include file path and line number.
6. JSON log records have the documented field set.
7. Stats include: directories processed, recomputes performed, valid caches
  consumed, stale/invalid caches replaced in-memory.

STOP gates:
1. Do not proceed if logging writes to any file in the permanent library.
2. Do not proceed if dry-run mode writes to the database.

Validation:
- Unit test: capture standard mode output, verify format.
- Unit test: capture dry-run output, verify no DB writes.
- Unit test: capture quiet mode output, verify only errors.
- Unit test: stats with missing/stale/invalid caches match recompute-aware
  counters from in-memory processing.

Cross-references:
- `design/cli-config-specification.md` §3.5 (stats semantics), §3.6 (output format), §3.7 (error handling)
- `src/nightfall_photo_ingress/logging_bootstrap.py`

Status: Implemented

---

## H6 — CLI Integration

Scope:
- Add `hash-import` subcommand to `src/nightfall_photo_ingress/cli.py`.
- Syntax: `nightfall-photo-ingress hash-import <path-to-root> [OPTIONS]`
- Options: `--chunk-size <N>`, `--dry-run`, `--quiet`, `--stats`,
  `--stop-on-error`.
- The command loads config (for `registry_path` and `[import] chunk_size`),
  instantiates the walker (H4), and runs the import.
- CLI `--chunk-size` overrides config `[import] chunk_size` overrides
  default 1000.
- Exit codes: 0 = success, 1 = partial errors, 2 = fatal error.
- Status snapshot emission via `_emit_status_snapshot` (consistent with other
  commands).

Acceptance criteria:
1. `nightfall-photo-ingress hash-import /path --dry-run` runs without error.
2. `--chunk-size 500` overrides config value.
3. `--stop-on-error` aborts on first invalid file.
4. `--quiet` suppresses non-error output.
5. `--stats` prints per-chunk details.
6. Exit code reflects success/failure.
7. Status snapshot is written on completion.

STOP gates:
1. Do not proceed if the command is registered under a name other than
   `hash-import`.
2. Do not proceed if the command accepts a `--path` config argument as
   positional (it should be the `<path-to-root>` argument).
3. Do not proceed if `sync-import` is removed from the CLI in this chunk
   (removal is a separate deprecation task).

Validation:
- Unit test: argparse registration, verify help text.
- Unit test: option precedence (CLI > config > default).
- Integration test: end-to-end dry-run on fixture tree.
- Integration test: end-to-end import on temp registry.

Cross-references:
- `design/cli-config-specification.md` §3.1–§3.3 (syntax and options)
- `src/nightfall_photo_ingress/cli.py`

Status: Implemented

---

## H7 — Config Integration

Scope:
- Add `[import]` section parsing to `src/nightfall_photo_ingress/config.py`.
- New config key: `chunk_size` (int, default 1000, must be > 0).
- The `[import]` section is optional. If absent, defaults apply.
- Existing `sync_hash_import_*` keys in `[core]` remain functional for
  backward compatibility with `sync-import` but are NOT read by `hash-import`.
- Add config validation: `chunk_size` must be a positive integer.
- Update `AppConfig` dataclass with an optional `import_chunk_size` field.

Acceptance criteria:
1. Config file with `[import] chunk_size = 500` is parsed correctly.
2. Config file without `[import]` section uses default 1000.
3. `chunk_size = 0` raises validation error.
4. `chunk_size = -1` raises validation error.
5. `sync_hash_import_*` keys are still parsed for `sync-import` compatibility.
6. `hash-import` command reads `import_chunk_size` from config.

STOP gates:
1. Do not proceed if `sync_hash_import_*` keys are removed from config parsing
   (backward compatibility required).
2. Do not proceed if `[import]` section keys conflict with existing section names.

Validation:
- Unit test: parse config with `[import]` section.
- Unit test: parse config without `[import]` section → default.
- Unit test: invalid `chunk_size` values → validation error.
- Unit test: config with both `[import]` and `sync_hash_import_*` → both parsed.

Cross-references:
- `design/cli-config-specification.md` §8 (import config), §11 (deprecated keys)
- `src/nightfall_photo_ingress/config.py`

Status: Implemented

---

## H8 — Tests

Scope:
- New unit test file: `tests/unit/test_hash_import.py`
  - Parser tests (H2 acceptance criteria).
  - Bulk insert tests (H3 acceptance criteria).
  - Idempotency tests (INV-HI06, INV-HI07).
  - Invariant enforcement tests (INV-HI01–INV-HI12): verify no writes to
    `files`, `audit_log`, `staging`, no pairing, no thumbnails, no delta token,
    no UI visibility, no account assignment, no EXIF, no reject/purge eligibility.
  - CLI argparse tests (H6 acceptance criteria).
  - Config parsing tests (H7 acceptance criteria).
- New integration test file: `tests/integration/test_hash_import_integration.py`
  - End-to-end import on temp directory tree with known `.hashes.v2` files.
  - Verify registry state after import.
  - Verify idempotency on second import.
  - Verify no side effects on other tables.
  - Verify stats output.
- Update existing test: `tests/unit/test_sync_import.py` — add deprecation
  comment header noting sync-import is legacy (no functional changes).

Acceptance criteria:
1. All 12 INV-HI invariants have at least one dedicated test.
2. Parser edge cases covered: empty file, malformed header, invalid hex,
   missing fields, valid file.
3. Bulk insert edge cases: empty list, single hash, large batch, duplicates,
   overlapping imports.
4. CLI test: argparse, option precedence, dry-run, quiet, stats, stop-on-error.
5. Config test: present section, absent section, invalid values.
6. Integration test: end-to-end flow on temp fixtures.
7. All tests pass in `govctl run backend.test.unit --json`.

STOP gates:
1. Do not proceed if any invariant (INV-HI01–INV-HI12) lacks a test.
2. Do not proceed if tests import from or depend on `sync_import.py` for
   hash-import functionality.

Validation:
- Run `govctl run backend.test.unit --json` — all tests pass.
- Review test coverage report for `hash_import.py`.

Cross-references:
- `design/architecture/invariants.md` INV-HI01–INV-HI12
- `tests/unit/test_sync_import.py` (existing, for comparison)
- `tests/integration/test_sync_import_integration.py` (existing)

Status: Implemented

---

## H9 — Doc Sync

Scope:
- Final design document review pass after implementation.
- Verify all design documents are consistent with the implemented behavior.
- Update any design statements that diverged during implementation.
- Verify `design/cli-config-specification.md` matches the actual CLI --help
  output.
- Verify `design/architecture/invariants.md` INV-HI01–INV-HI12 enforcement
  column references match actual code locations.
- Verify `design/rationale/architecture-decision-log.md` DEC-20260412-01
  implementation notes match actual implementation.
- Update `design/domain/domain-model.md` module map if module paths changed.
- Verify deprecated-concepts.md is accurate.

Acceptance criteria:
1. `nightfall-photo-ingress hash-import --help` output matches CLI spec §3.
2. All INV-HI enforcement references point to real code locations.
3. No stale sync-import references outside deprecated context.
4. ADL DEC-20260412-01 implementation notes are accurate.

STOP gates:
1. Do not proceed if any invariant enforcement reference is incorrect.
2. Do not proceed if CLI --help diverges from the specification.

Validation:
- Manual review of --help vs spec.
- Grep scan for stale references (same scan as consistency task).
- Review DEC-20260412-01 against implementation.

Cross-references:
- All files updated in the design pass (14 files listed in session)
- `design/cli-config-specification.md`
- `design/architecture/invariants.md`

Status: Implemented

---

## Dependencies

```
H1 (Schema) ─────► H3 (Insert) ─────► H4 (Walker) ─────► H6 (CLI)
                        ▲                                      ▲
H2 (Parser) ────────────┘                                      │
                                        H7 (Config) ───────────┘
                                                               │
H5 (Logging) ──────────────────────────────────────────────────┘
                                                               │
                                        H8 (Tests) ◄──────────┘
                                                               │
                                        H9 (Doc Sync) ◄───────┘
```

Execution order: H1 and H2 can proceed in parallel. H3 depends on H1 and H2.
H4 depends on H3. H5 and H7 can proceed after H2. H6 depends on H4, H5, and
H7. H8 depends on H6. H9 depends on H8.

---

## Completion Summary for Issue #65

When all chunks H1–H9 are complete:
- The `hash-import` CLI command is functional and tested.
- The 12 invariants (INV-HI01–INV-HI12) are enforced and tested.
- The `[import]` config section is parsed and validated.
- Design documents are synchronized with the implementation.
- Legacy `sync-import` remains available but is not modified.
- Issue #65 can be closed.
