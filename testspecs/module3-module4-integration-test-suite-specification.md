# Module 3 and Module 4 Integration Test Suite Specification

## Phase 1 Specification

This document defines the production-grade integration test suite specification for the combined OneDrive client and ingest pipeline boundary. It is intentionally implementation-ready, but contains no test code.

## 1. Test Scope And Objectives

The integration suite must validate the end-to-end handoff from the OneDrive client to the ingest pipeline under realistic, failure-prone conditions. The focus is not isolated unit behavior, but boundary correctness and state consistency across:

1. OneDrive delta polling and candidate normalization.
2. Download-to-staging behavior.
3. Ingest decisioning and SHA-256 authority.
4. Storage commit workflow.
5. Registry persistence and audit trail updates.
6. Recovery from crashes, replays, duplicates, and malformed upstream data.

Primary objectives:

1. Validate that OneDrive client outputs are accepted by the ingest pipeline without semantic drift.
2. Validate correctness of accept, discard, reject, quarantine, and replay decisions.
3. Validate crash safety across all handoff boundaries:
   - after download
   - after storage commit
   - before registry finalize
   - during journal replay
4. Validate idempotency across repeated poll cycles and replayed delta pages.
5. Validate that operator-visible outcomes are consistent with registry, storage, and audit state.
6. Validate that no invariant is violated under malformed metadata, duplicate items, partial downloads, or stale cursor/page conditions.

Cross-module invariants that must always hold:

1. A file must never be marked accepted in registry without a committed accepted-queue file, unless it is explicitly represented as an interrupted operation pending replay/recovery.
2. A file must never remain committed in accepted queue without either:
   - finalized registry state, or
   - explicit replay/journal evidence explaining why finalization is pending.
3. Repeated poll cycles over the same content must be idempotent.
4. Replayed or duplicate delta events must not produce duplicate accepted files or conflicting registry state.
5. Rejected content must never be re-ingested.
6. Audit trail must explain terminal outcomes.

## 2. Test Categories

The integration suite will be organized into the following categories.

1. Happy-path ingest
Purpose:
Validate the clean path from OneDrive delta response through download, staging, hashing, storage commit, registry finalize, and audit emission.

2. Crash-boundary scenarios
Purpose:
Validate correctness when controlled failures occur at each critical boundary:
- after download
- after storage commit
- before registry finalize
- during journal replay

3. Replay and journal recovery scenarios
Purpose:
Validate that interrupted ingest operations are replayed deterministically and safely.

4. Schema drift and malformed metadata
Purpose:
Validate resilience when upstream OneDrive metadata is missing, malformed, stale, duplicated, or version-incompatible.

5. Duplicate and replayed delta items
Purpose:
Validate reduction, replay safety, and idempotent handling across duplicate and repeated delta feeds.

6. Prefilter hit/miss correctness
Purpose:
Validate metadata_index usage and ensure prefilter decisions match registry truth.

7. Integrity guarantees
Purpose:
Validate size checks, hashing correctness, truncated downloads, early EOF, empty-body anomalies, and uncertain-size policy behavior.

8. Storage commit correctness
Purpose:
Validate same-pool rename and cross-pool copy-verify-unlink behavior, including collisions and durability expectations.

9. Reject-path preconditions
Purpose:
Validate that pre-known rejected content is discarded correctly and never promoted to accepted queue.

10. Operator-facing summaries and audit correctness
Purpose:
Validate that observable outcomes, audit events, drift warnings, journal replay summaries, and per-run result summaries are coherent and actionable.

11. End-to-end idempotency across multiple poll cycles
Purpose:
Validate stable behavior across repeated polls with unchanged, replayed, partially recovered, and already-accepted inputs.

## 3. Test Case Definitions

Below, each category includes concrete test cases with expected outcomes.

### Category A: Happy-Path Ingest

1. Test name: `test_e2e_single_new_photo_same_pool_accepts_cleanly`
Purpose:
Validate the normal new-file path using same-pool commit.
Preconditions:
- Empty registry.
- Valid account config.
- Same-pool commit mode enabled.
Input data:
- One delta item with valid `item_id`, `name`, `relative_path`, `size_bytes`, `normalized_modified_time`, `download_url`.
- Download stream emits full valid bytes.
Expected behavior:
- OneDrive client downloads file to staging.
- Ingest pipeline hashes file.
- Unknown hash becomes accepted.
Expected registry state:
- `files`: one row with `accepted`.
- `metadata_index`: one row for the OneDrive item.
- `accepted_records`: one accepted record.
- `file_origins`: one origin mapping.
Expected storage state:
- File exists in accepted queue path.
- No leftover temp file.
Expected audit events:
- ingest_started
- hash_completed
- storage_committed
- registry_persisted
- terminal accepted event
Expected logs/operator summaries:
- Poll summary shows one candidate, one download.
- Ingest summary shows `accepted_count = 1`.

2. Test name: `test_e2e_single_new_photo_cross_pool_accepts_with_copy_verify`
Purpose:
Validate normal new-file path using cross-pool copy+verify.
Preconditions:
- Empty registry.
- Cross-pool mode enabled.
Input data:
- Same as above, but accepted_root is on different filesystem simulation.
Expected behavior:
- File copied to destination.
- Size and SHA-256 verified.
- Source unlinked.
Expected registry state:
- Same as above.
Expected storage state:
- Accepted file exists only in destination.
- Staging source removed.
Expected audit events:
- Same as above.
Expected logs/operator summaries:
- Storage commit summary indicates cross-pool commit path.

### Category B: Crash-Boundary Scenarios

3. Test name: `test_crash_after_download_before_ingest_leaves_recoverable_staging_state`
Purpose:
Validate crash immediately after OneDrive client download completion.
Preconditions:
- Empty registry.
- Valid downloaded file staged.
Input data:
- One valid delta item.
- Controlled interruption after staging write completes, before ingest starts.
Expected behavior:
- No registry changes.
- File remains in staging.
- Next ingest run processes the staged file successfully.
Expected registry state:
- After crash: unchanged.
- After replayed run: accepted finalized.
Expected storage state:
- After crash: staged file present.
- After replay: accepted file present, staging cleared.
Expected audit events:
- After crash: no ingest terminal event.
- After replay: normal ingest lifecycle.
Expected logs/operator summaries:
- Recovery summary should indicate recovered staged file on next run.

4. Test name: `test_crash_after_storage_commit_before_registry_finalize_replays_or_completes_safely`
Purpose:
Validate the most critical commit boundary.
Preconditions:
- Journal enabled.
- Storage commit succeeds.
Input data:
- Valid candidate.
- Failure injection after storage commit and before registry finalize.
Expected behavior:
- Journal contains enough evidence to replay.
- Recovery either completes registry finalize deterministically or quarantines with explicit reason if recovery cannot prove safety.
Expected registry state:
- No partial inconsistent rows after crash.
- After replay: either accepted finalized or explicit quarantine outcome, never silent orphan.
Expected storage state:
- Committed file either finalized as accepted or moved to quarantine/recovery location.
Expected audit events:
- Interrupted lifecycle visible.
- Recovery terminal event emitted.
Expected logs/operator summaries:
- Recovery summary explicitly states recovered vs quarantined.

5. Test name: `test_crash_during_cross_pool_copy_never_leaves_false_accepted_state`
Purpose:
Validate crash during copy before verify/unlink.
Preconditions:
- Cross-pool mode.
Input data:
- Controlled interruption mid-copy.
Expected behavior:
- No accepted registry state.
- Partial destination file does not survive as a valid accepted file.
Expected registry state:
- No accepted finalization.
Expected storage state:
- Partial destination removed or quarantined, not treated as committed.
Expected audit events:
- Failure/recovery/quarantine visibility.
Expected logs/operator summaries:
- Clear operator signal that commit did not finalize.

### Category C: Replay And Journal Recovery

6. Test name: `test_replay_of_interrupted_operation_is_monotonic_and_idempotent`
Purpose:
Validate replay safety with repeated recovery calls.
Preconditions:
- Journal has interrupted operation entries.
Input data:
- Synthetic journal records covering `ingest_started`, `hash_completed`, `storage_committed`.
Expected behavior:
- First replay resolves the operation.
- Second replay is a no-op.
Expected registry state:
- Stable after first replay.
- Unchanged after second replay.
Expected storage state:
- Stable after first replay.
Expected audit events:
- No duplicate terminal outcomes.
Expected logs/operator summaries:
- Replay summary counts only one resolved operation.

7. Test name: `test_corrupted_journal_entry_isolated_without_blocking_other_replays`
Purpose:
Validate robustness against journal corruption.
Preconditions:
- Journal contains one valid op and one malformed op.
Input data:
- Mixed valid and corrupted journal records.
Expected behavior:
- Valid operation replays.
- Corrupted one is quarantined/flagged.
Expected registry state:
- Valid op finalized.
- Corrupt op does not poison unrelated state.
Expected storage state:
- Valid op committed normally.
Expected audit events:
- Corruption warning event.
Expected logs/operator summaries:
- Recovery summary lists unresolved/corrupt operation IDs.

### Category D: Schema Drift And Malformed Metadata

8. Test name: `test_missing_required_fields_rejected_at_boundary_before_ingest`
Purpose:
Validate strict cross-module contract.
Preconditions:
- OneDrive candidate payload missing required field.
Input data:
- Missing `item_id`, or missing `download_url`, or invalid schema version.
Expected behavior:
- Boundary validation rejects candidate.
- No staging commit attempt.
Expected registry state:
- No changes.
Expected storage state:
- No accepted file.
Expected audit events:
- Validation failure terminal event if the boundary emits one, otherwise error summary only.
Expected logs/operator summaries:
- Actionable validation error naming the missing field.

9. Test name: `test_malformed_size_and_timestamp_produce_drift_classification_not_silent_accept`
Purpose:
Validate malformed metadata handling.
Preconditions:
- Delta item with wrong types.
Input data:
- `size_bytes = "abc"` or malformed timestamp.
Expected behavior:
- Candidate rejected before ingest or classified as drift/anomaly.
Expected registry state:
- No acceptance.
Expected storage state:
- No accepted file.
Expected audit events:
- Anomaly/drift event.
Expected logs/operator summaries:
- Drift ratio or malformed payload summary incremented.

### Category E: Duplicate And Replayed Delta Items

10. Test name: `test_duplicate_delta_items_reduce_to_single_ingest_effect`
Purpose:
Validate in-run reducer consistency across OneDrive client and ingest pipeline.
Preconditions:
- Delta feed returns repeated same item.
Input data:
- Same item twice in same delta sequence.
Expected behavior:
- Only one staged file and one ingest outcome.
Expected registry state:
- Single accepted row.
Expected storage state:
- One accepted file.
Expected audit events:
- No duplicate terminal accepted.
Expected logs/operator summaries:
- Duplicate/reducer anomaly counters visible.

11. Test name: `test_replayed_delta_page_on_next_poll_does_not_duplicate_accepted_content`
Purpose:
Validate cross-poll idempotency.
Preconditions:
- First poll already accepted content.
Input data:
- Same delta page replayed on second poll.
Expected behavior:
- Second run hits metadata prefilter or accepted hash discard path.
Expected registry state:
- No duplicate acceptance history rows beyond intended append policy.
Expected storage state:
- No new accepted file copy.
Expected audit events:
- Duplicate discard or prefilter discard event.
Expected logs/operator summaries:
- Operator can see duplicate skipped, not reprocessed.

### Category F: Prefilter Hit/Miss Correctness

12. Test name: `test_prefilter_hit_skips_hashing_for_known_metadata_match`
Purpose:
Validate fast-path correctness.
Preconditions:
- `metadata_index` contains exact match.
Input data:
- Candidate with matching `onedrive_id`, `size`, `modified_time`.
Expected behavior:
- No hash performed.
- File discarded or skipped appropriately.
Expected registry state:
- Unchanged accepted/rejected state.
Expected storage state:
- No accepted copy added.
Expected audit events:
- Prefilter discard event.
Expected logs/operator summaries:
- Prefilter hit count incremented.

13. Test name: `test_prefilter_miss_hashes_and_accepts_when_registry_unknown`
Purpose:
Validate slow-path correctness.
Preconditions:
- No metadata index match.
Input data:
- Unknown file.
Expected behavior:
- Full hash and accept.
Expected registry state:
- Accepted rows created.
Expected storage state:
- Accepted file present.
Expected audit events:
- Full lifecycle plus accepted terminal event.

14. Test name: `test_prefilter_false_positive_protection_sampling_or_policy_path`
Purpose:
Validate safeguards against stale metadata index.
Preconditions:
- Inject stale `metadata_index` row that points to wrong content.
Input data:
- Candidate metadata matches but content bytes differ.
Expected behavior:
- Depends on configured policy:
  - if verification sampling enabled, stale prefilter is detected
  - otherwise test documents current limitation explicitly
Expected registry state:
- Should not silently corrupt accepted truth.
Expected storage state:
- No wrong-file acceptance.
Expected audit events:
- Verification mismatch or anomaly event.
Expected logs/operator summaries:
- Clear warning that metadata index was stale.

### Category G: Integrity Guarantees

15. Test name: `test_size_mismatch_between_metadata_and_staged_file_rejected_before_accept`
Purpose:
Validate ingest-side size integrity.
Preconditions:
- Downloaded file size does not match candidate metadata.
Input data:
- Candidate claims 100 bytes; staged file is 80 bytes.
Expected behavior:
- Reject or quarantine based on policy, never accept.
Expected registry state:
- No accepted row.
Expected storage state:
- File quarantined or discarded.
Expected audit events:
- `size_mismatch` terminal event.
Expected logs/operator summaries:
- Explicit mismatch reason.

16. Test name: `test_truncated_download_detected_end_to_end`
Purpose:
Validate OneDrive client plus ingest pipeline truncated-file protection.
Preconditions:
- Download stream ends early.
Input data:
- Expected size known; actual body shorter.
Expected behavior:
- OneDrive client rejects or retries; ingest should not see a valid candidate unless explicitly staged by failure injection.
Expected registry state:
- No accepted row.
Expected storage state:
- No accepted file.
Expected audit events:
- Download anomaly only, or ingest size mismatch if forced staged input.
Expected logs/operator summaries:
- Truncated/partial-read explanation.

17. Test name: `test_zero_byte_policy_is_enforced_consistently`
Purpose:
Validate zero-byte handling.
Preconditions:
- Zero-byte staged file.
Input data:
- Candidate with size 0.
Expected behavior:
- Respect zero-byte policy:
  - allow
  - quarantine
  - reject
Expected registry state:
- Policy-dependent, but deterministic.
Expected storage state:
- Policy-dependent.
Expected audit events:
- Matching policy event.
Expected logs/operator summaries:
- Explicit zero-byte classification.

### Category H: Storage Commit Correctness

18. Test name: `test_same_pool_atomic_rename_is_single_commit_visibility`
Purpose:
Validate same-pool commit semantics.
Preconditions:
- `staging_on_same_pool` true.
Input data:
- Valid staged file.
Expected behavior:
- Rename only, no copy fallback.
Expected registry state:
- Accepted finalized.
Expected storage state:
- File visible only at final location after commit.
Expected audit events:
- `storage_committed` event.
Expected logs/operator summaries:
- Same-pool storage path noted if traced.

19. Test name: `test_cross_pool_copy_verify_unlink_rejects_on_hash_mismatch`
Purpose:
Validate safety of cross-pool path.
Preconditions:
- Cross-pool mode.
Input data:
- Inject hash mismatch after copy.
Expected behavior:
- Destination not treated as committed.
- Source retained or quarantined according to recovery design.
Expected registry state:
- No accepted finalization.
Expected storage state:
- No false accepted file.
Expected audit events:
- Storage verification failure.
Expected logs/operator summaries:
- Explicit copy verification failure.

20. Test name: `test_collision_safe_destination_generation_remains_deterministic`
Purpose:
Validate naming correctness under collisions.
Preconditions:
- Existing destination file names collide.
Input data:
- Multiple same-name inputs with different hashes.
Expected behavior:
- Collision-safe suffixing deterministic and bounded.
Expected registry state:
- Distinct accepted records.
Expected storage state:
- Distinct files, no overwrite.
Expected audit events:
- Accepted events per file.
Expected logs/operator summaries:
- Collision count or rename suffix usage visible if exposed.

### Category I: Reject-Path Preconditions

21. Test name: `test_registry_rejected_hash_is_discarded_without_accept_commit`
Purpose:
Validate reject enforcement.
Preconditions:
- Registry contains rejected hash.
Input data:
- Candidate content hashes to known rejected SHA-256.
Expected behavior:
- File discarded, not accepted.
Expected registry state:
- Rejected remains rejected.
Expected storage state:
- No accepted file.
Expected audit events:
- `discard_rejected` terminal event.
Expected logs/operator summaries:
- Clear rejected skip outcome.

22. Test name: `test_registry_purged_hash_is_not_reaccepted`
Purpose:
Validate purged handling semantics.
Preconditions:
- Registry contains purged hash.
Input data:
- Matching content.
Expected behavior:
- Discard according to current policy.
Expected registry state:
- Purged remains purged.
Expected storage state:
- No accepted file.
Expected audit events:
- `discard_purged`.
Expected logs/operator summaries:
- Purged outcome visible.

### Category J: Operator-Facing Summaries And Audit Correctness

23. Test name: `test_operator_summary_matches_registry_storage_and_audit_counts`
Purpose:
Validate that what operators see matches actual state.
Preconditions:
- Mixed batch: accepted, duplicate discard, rejected discard, quarantine.
Input data:
- Mixed candidate set.
Expected behavior:
- Summary counts exactly match outcomes.
Expected registry state:
- Matches accepted and known statuses.
Expected storage state:
- Accepted and quarantine paths align with summary.
Expected audit events:
- One terminal event per candidate outcome.
Expected logs/operator summaries:
- `accepted_count`, `discarded_count`, `prefilter_hits`, `quarantines`, `replay_recovery` all coherent.

24. Test name: `test_terminal_audit_sequence_is_monotonic_per_batch`
Purpose:
Validate audit ordering and batch run grouping.
Preconditions:
- Batch with multiple candidates.
Input data:
- Mixed processing outcomes.
Expected behavior:
- `sequence_no` strictly increasing in terminal audit rows.
Expected registry state:
- Consistent with emitted order.
Expected storage state:
- Not central here.
Expected audit events:
- Monotonic ordering with single `batch_run_id`.
Expected logs/operator summaries:
- Batch summary references same run identity if available.

### Category K: End-To-End Idempotency Across Multiple Poll Cycles

25. Test name: `test_three_poll_cycles_new_then_replay_then_noop_are_idempotent`
Purpose:
Validate full-cycle idempotency.
Preconditions:
- Empty system initially.
Input data:
- Poll 1: new file.
- Poll 2: same delta replay.
- Poll 3: no changes.
Expected behavior:
- Poll 1 accepts.
- Poll 2 discards/skips as duplicate.
- Poll 3 no-op.
Expected registry state:
- Stable accepted state.
Expected storage state:
- Single accepted file.
Expected audit events:
- One accepted terminal event, later duplicate/prefilter/no-op indicators only.
Expected logs/operator summaries:
- Cycle summaries distinguish new, replay, no-op.

26. Test name: `test_recovery_cycle_after_interrupted_commit_then_replay_is_idempotent`
Purpose:
Validate interrupted run followed by normal rerun.
Preconditions:
- Crash injected after storage commit.
Input data:
- First run interrupted.
- Second run replay/recovery.
- Third run same delta replay.
Expected behavior:
- Recovery finalizes once.
- Third run is duplicate/no-op.
Expected registry state:
- Stable single accepted record.
Expected storage state:
- Single accepted file.
Expected audit events:
- Recovery event once, no duplicate finalization.
Expected logs/operator summaries:
- Recovery summary followed by stable no-op/duplicate summary.

## 4. Test Data Strategy

1. Simulating OneDrive delta feeds
- Use deterministic fixture objects representing normalized delta pages.
- Provide factories for:
  - created file item
  - deleted tombstone
  - delete+create rename pattern
  - duplicate same-page item
  - stale/replayed page
- Use page sequences, not only flat item lists, so nextLink replay/cycle behavior can be modeled.

2. Simulating download streams
- Use mocked HTTP/download layer or direct injection into the OneDrive client downloader.
- Stream modes:
  - normal full body
  - truncated body
  - empty 200 body
  - corrupted content body
  - delayed/partial chunk emission
- Provide deterministic byte fixtures for small image-like and video-like payloads.

3. Simulating crashes
- Use controlled interruption points via monkeypatch/failure-injection hooks at:
  - after staging write
  - after hash complete
  - after storage commit
  - before registry finalize
  - during journal append/replay
- Fail with explicit synthetic exceptions, not random failures.

4. Simulating schema drift
- Build malformed candidate factories:
  - missing field
  - wrong type
  - null field
  - extra unknown fields
  - schema version mismatch
- Validate fail-fast and drift summary behavior.

5. Simulating duplicate delta pages
- Feed same page twice.
- Feed same item across multiple pages.
- Feed out-of-order delete/create pairs.

6. Simulating cross-pool vs same-pool storage
- Do not rely on actual separate filesystems.
- Mock storage commit mode or storage helper behavior so one suite explicitly exercises:
  - rename path
  - copy+verify+unlink path
- For cross-pool path, assert source remains until verify succeeds.

## 5. Execution Strategy

1. Test organization
Create a dedicated integration suite under:
- `tests/integration/`

Suggested files:
- `tests/integration/test_m3_m4_happy_path.py`
- `tests/integration/test_m3_m4_crash_recovery.py`
- `tests/integration/test_m3_m4_schema_drift.py`
- `tests/integration/test_m3_m4_duplicates_and_replay.py`
- `tests/integration/test_m3_m4_storage_commit.py`
- `tests/integration/test_m3_m4_operator_semantics.py`
- `tests/integration/test_m3_m4_idempotency.py`

2. Filesystem isolation
- Use `tmp_path`-backed isolated directories for:
  - staging
  - accepted
  - quarantine
  - journal
  - registry db
  - token cache and cursor
- No shared mutable fixtures across tests.

3. Network and Graph mocking
- Mock Graph and download operations at the OneDrive client boundary.
- Prefer deterministic fake client objects over deep patching of internals where possible.
- Preserve actual candidate normalization and poll logic.

4. Time and timestamps
- Freeze or monkeypatch time for:
  - drift/stale-file classification
  - audit ordering assertions
  - journal replay/recovery summaries
- Ensure tests are independent of wall-clock timing.

5. Registry and audit validation
- Query registry directly after each integration run.
- Validate:
  - `files`
  - `metadata_index`
  - `accepted_records`
  - `file_origins`
  - `audit_log`
  - ingest terminal audit tables/events if separate
- Assert both row content and counts.

6. Staging and accepted validation
- Assert exact filesystem contents after each test.
- Validate absence of:
  - orphan temp files
  - duplicate accepted copies
  - silent partial destination files
- Validate quarantine paths where expected.

7. Logging and operator-summary validation
- Capture structured logs with `caplog`.
- Assert presence of:
  - account name
  - item_id or onedrive_id where appropriate
  - outcome reason
  - recovery/quarantine signals
- Validate batch summaries returned by integration entrypoints.

8. Execution model
- Integration tests should run serially by default.
- Explicit worker-count tests may exist, but integration baseline remains deterministic.

## 6. Success Criteria

The integration suite passes only if all of the following hold:

1. No test produces:
   - accepted storage without matching registry finalization or replay evidence
   - duplicate accepted commits for the same content
   - rejected content being accepted
   - silent truncated or partial file acceptance
   - unexplained quarantine or orphan states
2. All crash-recovery tests demonstrate deterministic and explainable outcomes.
3. All operator-facing summaries are consistent with registry and storage state.
4. Replay and duplicate delta tests are idempotent.
5. Schema drift tests fail safely and explicitly.
6. Same-pool and cross-pool commit paths both pass.
7. Journal replay never creates duplicate terminal audit rows.
8. Cross-module handoff from OneDrive client to ingest pipeline is validated through actual normalized candidate objects or an explicit boundary adapter fixture.
9. Full integration suite is deterministic across repeated runs.
10. No integration test relies on external network, real OneDrive, or wall-clock timing.

## Recommended Fixture Set

For Phase 2 implementation, these fixtures should exist:

1. `app_config_fixture`
Creates deterministic config with staging, accepted, quarantine, journal, registry, and OneDrive account settings.

2. `registry_fixture`
Creates initialized SQLite registry and helper query methods.

3. `fake_graph_fixture`
Provides page sequences and download streams.

4. `ingest_engine_fixture`
Constructs ingest engine with journal enabled.

5. `poll_and_ingest_fixture`
Runs a complete OneDrive-client-to-ingest cycle.

6. `crash_injection_fixture`
Enables named interruption points.

7. `fs_snapshot_fixture`
Captures directory trees for concise assertions.

8. `audit_reader_fixture`
Provides typed access to audit and terminal event rows.

## Recommended Minimum Initial Suite Size

A production-grade first implementation should include at least:

1. 6 happy-path and storage correctness tests
2. 6 crash/replay tests
3. 4 schema drift tests
4. 4 duplicate/idempotency tests
5. 4 operator/audit summary tests

Recommended minimum total: 24 integration tests.

## Non-Goals For This Suite

To keep the suite focused and maintainable, Phase 2 should not include:

1. Live Microsoft Graph or OneDrive calls
2. Performance benchmarking
3. Fuzz testing of arbitrary malformed JSON beyond deterministic contract cases
4. Module 5 behavior or trash/reject CLI workflows outside the current Module 3 and Module 4 boundary