# Registry-Aware Ingest Filter Integration Test Suite Specification

## 1. Purpose

This document defines a registry-focused integration test suite for the staging environment using:

1. the installed `nightfall-photo-ingress` staging container,
2. a real authenticated staging token already present in the container, and
3. the live SQLite registry used by the staging deployment.

The suite is intended to answer one operational question:

Is the ingest filter logic meaningfully reducing unnecessary work while preserving correct accept/reject behavior?

This is a specification only. It intentionally does not include test code.

---

## 2. Business Logic Intent From The Design

The accepted design intent is defined primarily in:

1. `design/v1-baseline-spec.md`
2. `design/architecture.md`
3. `design/configspec.md`
4. `design/decisions.md`

The ingest filter exists to enforce the following business rules.

### 2.1 Source of truth and boundary intent

1. OneDrive delta is the source of candidate discovery, not the source of ingest truth.
2. The SQLite registry is the source of truth for whether content is already accepted, rejected, or purged.
3. The accepted queue is only a handoff boundary. Manual operator moves into the permanent library must not cause later re-downloads.

### 2.2 Intended filtering behavior

For each OneDrive delta file candidate, the intended decision flow is:

1. Check the metadata pre-filter using `(account_name, onedrive_id, size_bytes, modified_time)`.
2. If that metadata exactly matches a known registry-backed row, skip unnecessary downstream work.
3. If metadata does not resolve the item safely, continue to download and compute SHA-256.
4. After hashing:
   - known `accepted` hash => discard staged file, persist duplicate/known-hit side effects,
   - known `rejected` hash => discard staged file, persist reject-duplicate side effects,
   - known `purged` hash => discard staged file,
   - unknown hash => accept into the accepted queue and persist canonical registry state.

### 2.3 What “meaningful” means operationally

The filter is meaningful only if it reduces expensive work without introducing false skips.

That means:

1. Exact metadata repeats should avoid redundant download and hash work where design says they should.
2. Changes that invalidate metadata certainty must force re-evaluation.
3. Acceptance history must keep blocking re-downloads even after queue files are manually moved away.
4. Advisory sync-import data must never bypass canonical SHA-256 safety when `verify_sha256_on_first_download=true`.

### 2.4 Known risk to detect

Current implementation seams suggest a possible design drift:

1. The design intent places metadata pre-filtering before download.
2. The current ingest engine also performs a registry metadata prefilter on already-staged files.
3. Therefore, this suite must explicitly distinguish:
   - pre-download filtering effectiveness,
   - post-download discard behavior,
   - overall correctness of registry-driven dedupe.

The suite must not assume those are the same thing.

---

## 3. Test Objectives

The suite must validate these objectives.

1. Exact metadata matches backed by registry truth are skipped safely.
2. Metadata mismatches force re-evaluation instead of producing false skips.
3. Known accepted/rejected/purged states drive the correct terminal outcome.
4. Registry side effects improve future filtering effectiveness.
5. Acceptance history remains effective even when files are no longer physically present in the accepted queue.
6. Sync-import advisory data remains advisory, not canonical.
7. Poll-level counters and ingest-level counters are separated clearly enough to diagnose whether filtering is reducing I/O or only discarding late.

---

## 4. Scope

### In Scope

1. Integration between live poll inputs, staging download boundary, registry lookups, and ingest outcomes.
2. Real registry behavior in the staging container.
3. Real authenticated Graph access using the already-present staging token.
4. Evidence gathered from logs, registry rows, handoff manifests, and filesystem state.

### Out Of Scope

1. P5 snapshot/reset testing.
2. Full crash-recovery and journal-replay coverage.
3. Exhaustive Live Photo pairing coverage except where pairing affects filter meaning.
4. Performance benchmarking beyond coarse effectiveness ratios.

---

## 5. Test Harness Model

The future test suite should use two complementary layers.

### Layer A: Live staging poll plus registry assertions

Use the installed staging container and real authenticated token to:

1. run `poll`,
2. observe poll summaries and detailed trace logs,
3. inspect registry state before and after,
4. inspect staging and accepted filesystem boundaries.

This layer proves real-world behavior.

### Layer B: Registry-seeded ingest boundary scenarios

Seed the registry with known rows and drive the ingest boundary with controlled staged candidates and/or controlled handoff manifests.

This layer proves decision semantics deterministically even when live OneDrive content is hard to control.

Both layers are required. Layer A alone cannot reliably isolate edge cases. Layer B alone cannot prove live poll behavior.

---

## 6. Required Test Data Strategy

The suite should define and maintain a dedicated OneDrive fixture area for the staging account.

Recommended fixture classes:

1. `new_unique_file`
2. `known_accepted_same_metadata`
3. `known_rejected_same_metadata`
4. `known_purged_same_metadata`
5. `same_onedrive_id_changed_size`
6. `same_onedrive_id_changed_modified_time`
7. `renamed_same_onedrive_id_same_size_same_mtime`
8. `manual_move_out_of_queue_but_already_accepted`
9. `sync_import_sha1_match_first_seen`
10. `sync_import_sha1_match_after_verified_sha256`

The suite should also define registry fixture builders for:

1. `files`
2. `accepted_records`
3. `metadata_index`
4. `file_origins`
5. `external_hash_cache`
6. `audit_log`

---

## 7. Observability Requirements

Each test should capture enough evidence to answer these questions:

1. Was the item seen by Graph delta traversal?
2. Was it counted as a poll candidate?
3. Was it actually downloaded?
4. Did it enter the ingest handoff manifest?
5. Was the registry metadata prefilter hit?
6. What terminal ingest action occurred?
7. Which registry tables changed?
8. Which files were created, removed, or left untouched?

Minimum evidence per test:

1. poll log or ingest log,
2. registry diff,
3. handoff manifest rows when present,
4. staging directory listing,
5. accepted queue listing,
6. relevant audit rows.

---

## 8. Acceptance Metrics For The Suite

The suite should classify filter behavior using these metrics.

1. `graph_seen_count`
2. `poll_candidate_count`
3. `downloaded_count`
4. `handoff_candidate_count`
5. `ingest_prefilter_hit_count`
6. `ingest_prefilter_miss_count`
7. `accepted_count`
8. `discard_known_count`

The key interpretation rule is:

1. If `poll_candidate_count` is high but `downloaded_count` is near zero, then filtering may be happening before download.
2. If `downloaded_count` is high but `ingest_prefilter_hit_count` is high, then filtering is happening late and may not be meaningfully reducing I/O.
3. If exact known repeats still download regularly, the design intent is not being met.

---

## 9. Concrete Test Cases

### Case 1: New unique file is accepted and indexed

Purpose:
Prove the baseline unknown path still works.

Preconditions:

1. Registry contains no matching `metadata_index` or `files` row.
2. Fixture file exists in the staging OneDrive fixture area.

Expected outcome:

1. Item appears in Graph traversal.
2. Item becomes a poll candidate.
3. Item is downloaded.
4. Item enters ingest handoff.
5. Terminal action is `accepted`.
6. `files`, `accepted_records`, `metadata_index`, `file_origins`, and `audit_log` are updated.

### Case 2: Exact accepted metadata repeat is filtered without redundant download

Purpose:
Validate the primary business value of the metadata filter.

Preconditions:

1. Registry contains `files.status='accepted'` for the file hash.
2. `metadata_index` contains an exact `(account_name, onedrive_id, size_bytes, modified_time)` match.
3. The file may or may not still exist in the accepted queue.

Expected outcome:

1. Item appears in Graph traversal.
2. Item is not redundantly downloaded.
3. Item does not require a new handoff candidate.
4. Accepted history remains the reason it is skipped.
5. No duplicate accepted file is created.

Failure signal this test is meant to catch:

1. Exact repeats still downloading despite exact metadata match.

### Case 3: Exact rejected metadata repeat is filtered and never re-ingested

Purpose:
Validate reject permanence.

Preconditions:

1. Registry contains `files.status='rejected'`.
2. `metadata_index` exact match exists.

Expected outcome:

1. Item may appear in traversal.
2. Item is skipped or discarded without entering accepted queue.
3. No accepted queue write occurs.
4. Audit evidence reflects duplicate rejected handling.

### Case 4: Exact purged metadata repeat stays discarded

Purpose:
Validate `purged` semantics are handled consistently.

Preconditions:

1. Registry contains `files.status='purged'`.
2. `metadata_index` exact match exists.

Expected outcome:

1. No accepted queue write occurs.
2. No false `accepted` transition occurs.

### Case 5: Size drift on same OneDrive item forces re-evaluation

Purpose:
Ensure metadata filter does not over-trust stale rows.

Preconditions:

1. `metadata_index` exists for the same `(account_name, onedrive_id)`.
2. Live item size differs from the indexed row.

Expected outcome:

1. Item is not skipped on metadata certainty.
2. Download and hash path is re-entered.
3. Registry is updated according to canonical SHA-256 outcome.

### Case 6: Modified time drift on same OneDrive item forces re-evaluation

Purpose:
Ensure mtime is part of the trust boundary.

Preconditions:

1. Same as Case 5, except only `modified_time` differs.

Expected outcome:

1. Metadata filter does not treat the item as exact match.
2. Download/hash path is used.

### Case 7: Rename or move with same OneDrive ID, size, and modified time should remain filtered

Purpose:
Validate path-independent dedupe semantics.

Preconditions:

1. Exact metadata row exists for the same `onedrive_id`, size, and modified time.
2. The visible path/name in OneDrive changed.

Expected outcome:

1. No duplicate accepted file is created.
2. No re-download is required if the design intent is met.

### Case 8: Accepted history survives manual operator move out of queue

Purpose:
Validate the core queue-boundary contract.

Preconditions:

1. File was previously accepted.
2. Operator has manually moved it out of `accepted_path`.
3. Registry still has accepted history.

Expected outcome:

1. Future poll cycles still block re-ingest.
2. Physical absence from `accepted_path` does not cause re-download.

### Case 9: Known accepted hash without metadata index requires one expensive pass, then becomes filterable

Purpose:
Prove the registry side effects improve future filtering.

Preconditions:

1. `files.status='accepted'` exists for the canonical SHA-256.
2. No matching `metadata_index` row exists yet for the OneDrive item.

Expected outcome:

1. First encounter may require download/hash.
2. Terminal action is discard of known accepted content.
3. `metadata_index` is written during finalize-known handling.
4. A second identical encounter becomes filterable earlier.

### Case 10: Sync-import advisory SHA1 match still requires first verification download

Purpose:
Validate `verify_sha256_on_first_download=true`.

Preconditions:

1. `external_hash_cache` contains a matching advisory SHA1.
2. No canonical SHA-256 verification has yet been recorded for this item.

Expected outcome:

1. The item is not permanently trusted on advisory SHA1 alone.
2. One verification download occurs.
3. Canonical registry state is then established.

### Case 11: Verified advisory match becomes safely skippable on subsequent encounter

Purpose:
Validate that the verification flag improves safety first, then efficiency later.

Preconditions:

1. Case 10 has already completed successfully.
2. Canonical SHA-256 is now persisted with matching metadata.

Expected outcome:

1. Subsequent identical encounters are skipped without redundant download.

### Case 12: Poll summary and ingest summary must tell the same operational story

Purpose:
Prevent operator confusion like “many pages traversed but zero candidates/downloads” without explanation.

Preconditions:

1. Any scenario above is executed with trace logging available.

Expected outcome:

1. Poll-side counters and ingest-side counters can be reconciled.
2. Evidence makes it clear whether filtering happened:
   - before download,
   - after download but before accept,
   - after hashing via known-hash discard.

---

## 10. Suggested Execution Order

Implement the suite in this order.

1. Case 1
2. Case 9
3. Case 2
4. Case 3
5. Case 5
6. Case 6
7. Case 8
8. Case 10
9. Case 11
10. Case 12
11. Case 4
12. Case 7

This order establishes the baseline, then proves whether filtering gains effectiveness as registry state accumulates.

---

## 11. Primary Questions The Suite Must Answer

When this suite exists, it must let us answer these questions unambiguously.

1. Are exact repeats being prevented before download, or only discarded later?
2. Is `metadata_index` materially reducing work, or just recording history after the expensive path?
3. Does accepted history remain effective when queue files are gone?
4. Are advisory SHA1 matches safe under the default verification policy?
5. Which counters should operators trust when they see heavy traversal but zero downloads?

If the suite cannot answer those five questions, it is not complete.