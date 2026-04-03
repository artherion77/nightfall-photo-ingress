# Module 3 + Module 4 Integration Suite Spec Compliance Review

Status: Open for later work
Date: 2026-03-31
Scope: Review of the implemented Module 3 + Module 4 integration test suite against the approved specification

## Purpose

This document records the gap analysis between the approved integration test suite specification and the currently implemented integration suite. It is intended as a follow-up work item reference and should be used to drive a future tightening pass on the test harness and assertions.

## Spec Coverage Matrix

| # | Spec Test Case | Implemented Test | Coverage | Review |
|---|---|---|---|---|
| 1 | test_e2e_single_new_photo_same_pool_accepts_cleanly | tests/integration/test_m3_m4_happy_path.py | Full | Good core coverage: poll, ingest, registry, accepted path, terminal audit. Logs/operator summary only lightly checked. |
| 2 | test_e2e_single_new_photo_cross_pool_accepts_with_copy_verify | tests/integration/test_m3_m4_happy_path.py | Partial | Confirms accepted outcome and destination content, but does not directly assert copy-verify-unlink semantics or audit/log specifics. |
| 3 | test_crash_after_download_before_ingest_leaves_recoverable_staging_state | tests/integration/test_m3_m4_crash_recovery.py | Partial | Validates staged-file recovery, but lacks explicit audit/log summary assertions from the spec. |
| 4 | test_crash_after_storage_commit_before_registry_finalize_replays_or_completes_safely | tests/integration/test_m3_m4_crash_recovery.py | Partial | Exercises the boundary, but recovery semantics are weaker than spec: it mainly asserts quarantine, not deterministic finalize-or-quarantine with detailed operator summary. |
| 5 | test_crash_during_cross_pool_copy_never_leaves_false_accepted_state | tests/integration/test_m3_m4_crash_recovery.py | Partial | Good negative acceptance check, but operator-facing failure semantics and quarantine visibility are under-asserted. |
| 6 | test_replay_of_interrupted_operation_is_monotonic_and_idempotent | tests/integration/test_m3_m4_crash_recovery.py | Partial | Covers replay monotonicity, but not audit-event duplication or operator summary depth. |
| 7 | test_corrupted_journal_entry_isolated_without_blocking_other_replays | tests/integration/test_m3_m4_crash_recovery.py | Partial | Covers corruption isolation, but does not verify audit warning event or explicit unresolved-op summary. |
| 8 | test_missing_required_fields_rejected_at_boundary_before_ingest | tests/integration/test_m3_m4_schema_drift.py | Partial | Only missing downloadUrl path is exercised. Spec also called out missing item_id and invalid schema version; those are not covered here. |
| 9 | test_malformed_size_and_timestamp_produce_drift_classification_not_silent_accept | tests/integration/test_m3_m4_schema_drift.py | Partial | Covers malformed size/timestamp, but does not validate audit/drift-summary visibility deeply. |
| 10 | test_duplicate_delta_items_reduce_to_single_ingest_effect | tests/integration/test_m3_m4_duplicates_and_replay.py | Full | Good duplicate reduction coverage. |
| 11 | test_replayed_delta_page_on_next_poll_does_not_duplicate_accepted_content | tests/integration/test_m3_m4_duplicates_and_replay.py | Partial | Good idempotency check, but does not verify acceptance-history row policy or operator summary text. |
| 12 | test_prefilter_hit_skips_hashing_for_known_metadata_match | tests/integration/test_m3_m4_happy_path.py | Partial | Prefilter hit count and discard outcome are checked, but no-hash-performed is inferred rather than directly proven. |
| 13 | test_prefilter_miss_hashes_and_accepts_when_registry_unknown | tests/integration/test_m3_m4_happy_path.py | Partial | Correct accept behavior is covered, but audit/log specifics are thin. |
| 14 | test_prefilter_false_positive_protection_sampling_or_policy_path | tests/integration/test_m3_m4_schema_drift.py | Partial | Exists, but weak. It only asserts action is not discard_accepted; it does not verify the intended stale-index warning/anomaly path clearly. |
| 15 | test_size_mismatch_between_metadata_and_staged_file_rejected_before_accept | tests/integration/test_m3_m4_storage_commit.py | Partial | Correct boundary target now, but registry and audit assertions are still shallow. |
| 16 | test_truncated_download_detected_end_to_end | tests/integration/test_m3_m4_storage_commit.py | Partial | Correctly checks OneDrive boundary rejection via DownloadError, but does not verify downstream storage/registry remain untouched. |
| 17 | test_zero_byte_policy_is_enforced_consistently | tests/integration/test_m3_m4_storage_commit.py | Partial | Only quarantine policy is covered. Spec explicitly called out allow, quarantine, reject. |
| 18 | test_same_pool_atomic_rename_is_single_commit_visibility | tests/integration/test_m3_m4_storage_commit.py | Partial | Good same-pool path presence check, but not true single-visibility or audit detail validation. |
| 19 | test_cross_pool_copy_verify_unlink_rejects_on_hash_mismatch | tests/integration/test_m3_m4_storage_commit.py | Partial | Largest purpose drift in storage tests. Simulates a crash during copy, not a post-copy hash mismatch. |
| 20 | test_collision_safe_destination_generation_remains_deterministic | tests/integration/test_m3_m4_storage_commit.py | Partial | Only verifies destination paths differ. It does not validate deterministic, bounded suffixing behavior. |
| 21 | test_registry_rejected_hash_is_discarded_without_accept_commit | tests/integration/test_m3_m4_storage_commit.py | Full | Good rejected-path enforcement coverage. |
| 22 | test_registry_purged_hash_is_not_reaccepted | tests/integration/test_m3_m4_storage_commit.py | Full | Good purged-path enforcement coverage. |
| 23 | test_operator_summary_matches_registry_storage_and_audit_counts | tests/integration/test_m3_m4_operator_semantics.py | Partial | Underpowered for the spec. It checks counts loosely and only asserts one trace log record exists. |
| 24 | test_terminal_audit_sequence_is_monotonic_per_batch | tests/integration/test_m3_m4_operator_semantics.py | Full | Good sequence_no and batch_run_id coverage. |
| 25 | test_three_poll_cycles_new_then_replay_then_noop_are_idempotent | tests/integration/test_m3_m4_idempotency.py | Partial | Good storage no-duplication check, but audit/operator summary assertions are missing. |
| 26 | test_recovery_cycle_after_interrupted_commit_then_replay_is_idempotent | tests/integration/test_m3_m4_idempotency.py | Partial | Too weak for the spec. It allows accepted_count in {0, 1}, which makes the intended invariant ambiguous. |

## Fixture Compliance Review

Required fixtures are present:
- app_config_fixture
- registry_fixture
- fake_graph_fixture
- ingest_engine_fixture
- poll_and_ingest_fixture
- crash_injection_fixture
- fs_snapshot_fixture
- audit_reader_fixture

### Assessment

1. app_config_fixture
- Good: deterministic and isolated.
- Risk: only a subset of policy switches are exercised in tests.

2. registry_fixture
- Good: direct SQL helper access is aligned with the spec.

3. fake_graph_fixture
- Good: deterministic and boundary-level.
- Drift risk: reduced_candidates reparses page payloads independently of the poll result payload.

4. ingest_engine_fixture
- Good for direct replay and ingest-state tests.

5. poll_and_ingest_fixture
- High drift risk: reconstructs StagedCandidate objects from reduced candidates instead of consuming a single explicit production boundary artifact from the OneDrive client.

6. crash_injection_fixture
- Partial: supports only a subset of the intended interruption points.
- Missing from spec-level intent:
  - after staging write
  - after hash complete
  - during journal append
  - during journal replay

7. fs_snapshot_fixture
- Good and deterministic.

8. audit_reader_fixture
- Partial: adequate for terminal action checks, but too narrow for richer operator-facing and audit-detail assertions.

## Boundary Fidelity Review

The suite does not fully exercise the Module 3 to Module 4 boundary through a single explicit production handoff artifact.

### Main issue

The integration harness reconstructs ingest candidates in test code rather than consuming a concrete boundary object emitted by Module 3. This means the suite validates real poll logic and real ingest logic, but the handoff between them is partially synthetic.

### Why this matters

1. Module 3 candidate semantic drift may be masked by the harness.
2. Contract failures at the boundary may not be detected if the reconstruction logic preserves old assumptions.

### Tests that bypass the intended boundary more deeply than ideal

- tests/integration/test_m3_m4_crash_recovery.py
- tests/integration/test_m3_m4_storage_commit.py
- tests/integration/test_m3_m4_idempotency.py

These are still useful integration tests, but they are not pure end-to-end boundary validations.

## Invariant Enforcement Review

### Invariant 1
A file must never be marked accepted in registry without a committed accepted-queue file, unless explicitly pending replay or recovery.
- Covered by cases 1, 2, 4, 5, 25, 26.
- Status: Partial.
- Gap: case 26 is too weak and case 4 emphasizes quarantine more than deterministic finalize-or-evidence.

### Invariant 2
A file must never remain committed in accepted queue without finalized registry state or explicit replay/journal evidence.
- Covered by cases 4, 5, 6, 7.
- Status: Partial.
- Gap: not strongly asserted across accepted-root and journal state together.

### Invariant 3
Repeated poll cycles over the same content must be idempotent.
- Covered by cases 11, 25, 26.
- Status: Good but partial.

### Invariant 4
Replayed or duplicate delta events must not produce duplicate accepted files or conflicting registry state.
- Covered by cases 10, 11, 25.
- Status: Good.

### Invariant 5
Rejected content must never be re-ingested.
- Covered by case 21.
- Status: Full.

### Invariant 6
Audit trail must explain terminal outcomes.
- Covered by cases 23 and 24 plus scattered terminal assertions.
- Status: Partial.
- Gap: reason text, actor, and operator-facing summary alignment are weakly asserted.

## Failure-Mode Coverage Review

Covered reasonably:
- crash after download before ingest
- crash after storage commit before registry finalize
- crash during cross-pool copy
- duplicate delta items
- replayed delta page
- size mismatch
- truncated download
- rejected and purged paths

Missing or incomplete:
- crash during journal replay
- crash during journal append
- crash after hash complete
- invalid schema version path
- null field path
- extra unknown fields path
- delete+create rename pattern
- stale page or resurrected item simulation
- explicit ghost-item boundary scenario
- zero-byte allow and reject policies
- corrupted download body distinct from truncated body

## Cross-Pool / Same-Pool Commit Path Review

Both commit paths are represented, but coverage is not fully faithful.

### Same-pool
- Covered by cases 1 and 18.
- Gap: single-visibility semantics are only indirectly checked.

### Cross-pool
- Covered by cases 2, 5, and 19.
- Major gap: case 19 does not truly simulate hash mismatch after copy verification.
- Additional gap: no deep assertion that source remains until verification succeeds and partial destination is cleaned up on verification mismatch.

## Operator-Facing Semantics Review

What is asserted:
- one trace log presence in case 23
- terminal action ordering and batch_run_id in case 24

What is missing:
- explicit operator distinction between accepted, rejected, quarantined, duplicate-skipped, and replay-recovered
- actor correctness assertions
- strong reason-text assertions
- per-run summary coherence across registry, storage, and audit state
- recovery summaries with unresolved operation IDs

This is the most under-tested area relative to the approved specification.

## Determinism And Isolation Review

Strengths:
- tmp_path isolation
- deterministic fake Graph behavior
- no external network
- no obvious shared mutable state across tests

Weaknesses:
- no explicit time freezing or monkeypatched time despite specification intent
- some tests rely indirectly on current-time production behavior
- time-sensitive drift and replay classifications are not tightly controlled in test code

## Discrepancies And Severity

### High severity
- Boundary adapter drift in tests/integration/conftest.py
- Case 19 purpose mismatch
- Case 23 weak operator-summary validation
- Case 26 weak idempotency and recovery assertions
- Invalid schema version branch from case 8 not covered

### Medium severity
- Case 8 missing item_id and schema-version subcases
- Case 14 weak stale-prefilter protection assertions
- Case 17 missing allow and reject policy branches
- crash_injection_fixture missing several interruption points
- audit_reader_fixture too narrow
- no explicit time freezing or monkeypatching for time-sensitive scenarios
- inconsistent validation depth across registry, storage, audit, and operator-summary surfaces

### Low severity
- some happy-path and log assertions are lighter than ideal
- same-pool visibility semantics could be asserted more directly
- collision determinism is not deeply validated

## Final Verdict

The implementation does not fully satisfy the approved specification.

What is solid:
- correct file layout
- all required fixtures exist
- all 26 test cases are present by name or direct mapping
- broad category coverage is in place

What remains to reach full compliance:
1. Replace or harden the boundary handoff in tests/integration/conftest.py so ingest input comes from an explicit production boundary adapter or artifact.
2. Strengthen case 8 to cover:
   - missing item_id
   - missing downloadUrl
   - invalid schema version
3. Strengthen case 17 to cover all zero-byte policies:
   - allow
   - quarantine
   - reject
4. Rewrite case 19 so it actually simulates cross-pool hash mismatch after copy verification.
5. Strengthen case 23 so it asserts:
   - summary counts
   - registry alignment
   - storage alignment
   - terminal event coverage
   - meaningful operator-facing log content
6. Strengthen case 26 so it asserts deterministic final state:
   - one final accepted record
   - one accepted file
   - no duplicate terminal finalization
7. Expand fixture support:
   - more crash injection points
   - richer audit reader access
   - deterministic time control for time-sensitive scenarios

## Follow-Up Checklist

- [ ] Harden boundary adapter fidelity between OneDrive client output and ingest input
- [ ] Expand case 8 to full required coverage
- [ ] Expand case 17 to all zero-byte policy modes
- [ ] Rewrite case 19 to true cross-pool hash mismatch verification
- [ ] Strengthen case 23 operator-summary assertions
- [ ] Strengthen case 26 deterministic recovery assertions
- [ ] Extend crash_injection_fixture with missing interruption points
- [ ] Extend audit_reader_fixture for richer audit and operator validations
- [ ] Add deterministic time control where needed
