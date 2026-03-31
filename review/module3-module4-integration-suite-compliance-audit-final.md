# Module 3 And Module 4 Integration Suite Compliance Audit Final

Status: Open for follow-up work
Date: 2026-03-31
Scope: Audit of the compliance review itself against the approved integration specification and the implemented integration suite

## Purpose

This document validates whether the existing compliance review is itself accurate, complete, and proportionate. It is a corrective synthesis over three artifacts:

1. The approved specification in [testspecs/module3-module4-integration-test-suite-specification.md]((root)/testspecs/module3-module4-integration-test-suite-specification.md)
2. The implemented suite in [tests/integration/conftest.py]((root)/tests/integration/conftest.py) and [tests/integration]((root)/tests/integration)
3. The first compliance review in [review/module3-module4-integration-suite-spec-compliance-review.md]((root)/review/module3-module4-integration-suite-spec-compliance-review.md)

The goal is not to restate the earlier review, but to correct any overstatement, understatement, duplication, or missed structural issues.

## Final Assessment Of The Existing Compliance Review

The existing compliance review is directionally correct and useful, but not fully accurate or complete.

High-level verdict:

1. It correctly identifies the largest structural risk: the synthetic Module 3 to Module 4 handoff reconstruction in [tests/integration/conftest.py]((root)/tests/integration/conftest.py).
2. It correctly identifies several under-tested cases: 8, 17, 19, 23, and 26.
3. It overstates a few gaps without acknowledging current partial coverage.
4. It misses several fixture-level and determinism risks.
5. It duplicates at least one discrepancy in the severity section.

## 1. Coverage Matrix Validation

### Accurate findings in the existing review

The following mappings and coverage ratings are materially correct:

1. Cases 1, 10, 21, 22, and 24 are the strongest-covered tests.
2. Cases 8, 17, 19, 23, and 26 are materially incomplete relative to the specification.
3. Cases 3 to 7 are only partial because they do not validate operator-facing summaries or rich audit semantics deeply enough.

### Corrections to the existing review

1. Case 2 is understated slightly.
The existing review says it does not directly assert copy-verify-unlink semantics. That is mostly true, but the implemented test does verify destination content and that the staging directory no longer contains the staged file. It should still remain Partial, but the review should acknowledge that source unlink is already indirectly covered.

2. Case 16 is correctly Partial, but the reason should be sharper.
The current test is valid for the OneDrive boundary. The gap is not that it checks the wrong layer, but that it does not additionally assert that registry, accepted, and quarantine remain untouched after the download failure.

3. Case 18 is correctly Partial, but "single-visibility semantics" is not really proven or disproven here.
The stronger wording should be: the test proves rename path use indirectly through absence of temp files, but does not explicitly validate a no-copy path or intermediate visibility constraints.

4. Case 20 is correctly Partial, but the exact gap is not just bounded suffixing.
The larger missing check is deterministic suffix policy across reruns and concurrent-like collision conditions. The current test only proves non-overwrite.

5. Case 25 is slightly stronger than the existing review states.
It does prove the three-cycle behavioral shape new then replay then noop. The missing part is richer audit and operator-summary coherence, not the idempotency shape itself.

### False negative or underreported items not called out strongly enough

1. Case 11 should explicitly mention that acceptance-history policy is not asserted at all, not merely weakly asserted.
2. Case 12 should explicitly mention that "no hash performed" cannot currently be proven with the implemented fixture surface.
3. Case 15 should mention that the test does not assert terminal audit action for size mismatch.

## 2. Fixture Compliance Validation

### Existing review findings that are correct

1. All required fixtures exist.
2. `poll_and_ingest_fixture` is the most significant source of boundary drift.
3. `crash_injection_fixture` is incomplete relative to the spec intent.
4. `audit_reader_fixture` is too narrow for strong operator-facing assertions.

### Additional fixture-level risks missed in the existing review

1. `poll_and_ingest_fixture` zips `reduced_candidates` with `poll_result.downloaded_paths`.
This assumes positional equivalence between test-side candidate reduction and production poll download ordering. That is a stronger and more fragile assumption than the existing review states.
Severity: High

2. `fake_graph_fixture.reduced_candidates()` calls `parse_delta_items()` directly on raw page items and then applies its own last-event-wins reducer. This duplicates production boundary shaping logic inside the harness instead of consuming a single production-emitted boundary object.
Severity: High

3. `fake_graph_fixture` queues pages and downloads deterministically, but it does not model page-to-download mismatches, ghost items, or download URL disappearance with enough fidelity for the full spec intent.
Severity: Medium

4. `app_config_fixture` includes many policy knobs, but the existing review understates that some policy-based tests are impossible to write faithfully with current helper ergonomics because `poll_and_ingest_fixture` only exposes a narrow set of overrides.
Severity: Medium

5. `crash_injection_fixture` only patches two concrete implementation hooks. The deeper problem is that its model is storage/registry-centric, not lifecycle-centric. It cannot currently inject after staging write, after hash complete, during journal append, or during journal replay because the production code does not expose those seams through the harness.
Severity: Medium

## 3. Boundary Fidelity Validation

### Existing review finding

The suite does not fully exercise the Module 3 to Module 4 boundary through a single explicit production handoff artifact.

This is correct.

### Severity validation

The existing review assigns High severity. That is appropriate.

Reason:

1. The test harness reconstructs `StagedCandidate` objects in [tests/integration/conftest.py]((root)/tests/integration/conftest.py) from test-side reduced candidates instead of consuming a production-owned boundary DTO, file, or mapper.
2. This can hide drift in field naming, normalization, or ordering.
3. It can also produce false confidence for crash/replay scenarios that bypass the real handoff.

### Additional overlooked boundary drift risks

1. Several tests invoke the ingest engine directly after using the poll fixture only for staging. Those are still useful, but they should be explicitly categorized as boundary-adjacent recovery tests, not pure end-to-end boundary tests.
2. The harness does not validate that every staged path in `poll_result.downloaded_paths` is matched to the same semantic candidate object that Module 3 intended. It assumes that relationship.

## 4. Invariant Enforcement Validation

### Invariant 1
A file must never be marked accepted in registry without a committed accepted-queue file, unless explicitly pending replay or recovery.

Existing review: Partial.
Assessment: Correct.
Correction: case 2 contributes more strongly than the review credits because it does validate accepted file presence after cross-pool commit.

### Invariant 2
A file must never remain committed in accepted queue without finalized registry state or explicit replay/journal evidence.

Existing review: Partial.
Assessment: Correct, but understated.
The gap is larger because the tests do not systematically assert accepted-root contents together with journal evidence and registry state after interrupted operations.

### Invariant 3
Repeated poll cycles over the same content must be idempotent.

Existing review: Good but partial.
Assessment: Correct.

### Invariant 4
Replayed or duplicate delta events must not produce duplicate accepted files or conflicting registry state.

Existing review: Good.
Assessment: Correct.

### Invariant 5
Rejected content must never be re-ingested.

Existing review: Full.
Assessment: Correct.

### Invariant 6
Audit trail must explain terminal outcomes.

Existing review: Partial.
Assessment: Correct, but the gap is larger than stated.
The current suite barely checks actor, reason, remediation clarity, or cross-surface alignment between audit rows and operator-facing summaries.

## 5. Failure-Mode Coverage Validation

### Correctly identified as missing or incomplete

1. crash during journal replay
2. crash during journal append
3. invalid schema version path
4. zero-byte allow and reject modes
5. delete+create rename pattern
6. stale page or resurrected item simulation
7. explicit ghost-item boundary scenario
8. corrupted body distinct from truncated body

### Items where the existing review slightly overstates the gap

1. crash after hash complete
This is indeed missing, but it belongs more to the failure-injection strategy and fixture seam coverage than to the explicit 1 to 26 case matrix.

2. null field path and extra unknown fields path
These are valid missing scenarios, but they are derived from the test data strategy section, not from named case definitions. They should be classified as secondary compliance gaps, not first-order missing test cases.

### Additional missing failure modes not called out

1. mismatch between `poll_result.candidate_count` and the reconstructed staged candidate count in the harness
2. replay of a delta page containing both deleted tombstones and downloadable files where ordering matters
3. duplicate download URLs across distinct items, which could expose harness assumptions

## 6. Commit-Path Coverage Validation

The existing review is correct that both same-pool and cross-pool paths are represented but incompletely validated.

Corrections:

1. The review is right that case 19 is the biggest purpose drift.
2. It should also explicitly note that case 5 and case 19 together currently conflate crash-during-copy and verification-failure semantics.
3. The same-pool assessment should note that case 18 checks absence of temp residue, which is a meaningful but indirect commit-path signal.

Overlooked edge cases:

1. no test asserts directory creation race resilience
2. no test asserts collision handling under cross-pool commit specifically

## 7. Operator-Facing Semantics Validation

The existing review is correct and the severity should remain High.

Additional missing gaps not explicitly called out:

1. No test asserts that operator-visible summaries distinguish replay recovery from quarantine.
2. No test asserts that the same `batch_run_id` appearing in terminal audit rows also lines up with any operator-visible summary.
3. No test asserts per-run digest coherence for accepted, discarded, quarantined, replayed, and prefilter outcomes together.
4. No test asserts actor values on terminal audit rows even though the production code now emits stable actor labels.

## 8. Determinism And Isolation Validation

The existing review is directionally correct but incomplete.

Correct findings:

1. tmp_path isolation is used well.
2. fake Graph behavior is deterministic.
3. external network is not used.

Additional determinism risks missed:

1. The suite depends on production code that writes timestamps and recovery classifications using current time, but no explicit time control is present.
2. Some tests use directory snapshots and journal side effects without freezing time, which can make stale/orphan classifications harder to reason about if production thresholds change.
3. The fake Graph queue state is mutable and single-use; this is fine per test, but makes accidental multi-use fixture sharing a latent hazard.

Severity: Medium

## 9. Review Drift In The Existing Compliance Analysis

### Overstated items

1. Case 2 gap is slightly overstated because source unlink is indirectly validated.
2. Some failure-mode omissions are presented as if they were part of the 26 named cases, when they are actually data-strategy-level gaps.

### Understated items

1. The positional zip between reduced candidates and downloaded paths is a more severe boundary drift than stated.
2. Operator-facing audit and summary weakness is broader than just case 23.
3. Invariant 2 is less well enforced than the review suggests.

### Misread or duplicated items

1. The severity section duplicates the case 8 schema-version gap in both High and Medium form.
2. The final verdict’s statement that "all 26 test cases are present by name or direct mapping" is broadly true, but it masks that several are only weak semantic approximations of the approved cases.

## Corrected Severity Summary

### High

1. Synthetic boundary reconstruction in [tests/integration/conftest.py]((root)/tests/integration/conftest.py)
2. Positional zip coupling between reduced candidates and downloaded paths
3. Case 19 purpose mismatch
4. Case 23 weak operator-facing summary validation
5. Case 26 weak deterministic recovery assertions
6. Invalid schema version branch from case 8 not covered

### Medium

1. Case 8 still missing explicit `item_id` subcase
2. Case 14 stale-prefilter protection remains weakly asserted
3. Case 17 missing zero-byte allow and reject branches
4. `crash_injection_fixture` missing lifecycle-level interruption points
5. `audit_reader_fixture` too narrow for richer audit/operator assertions
6. No explicit time control for time-sensitive behaviors
7. Several tests validate only one or two of registry, storage, audit, and operator-summary surfaces when the spec expects all four
8. Missing rename as delete+create integration case
9. Missing ghost-item and stale-page integration cases

### Low

1. Some happy-path tests could assert richer operator summaries
2. Same-pool visibility semantics could be asserted more directly
3. Collision determinism is only lightly checked

## Final Verdict

The existing compliance review is useful and mostly correct, but it is not fully accurate or complete.

It should be treated as a strong draft, not the final authoritative assessment.

What must be corrected from the existing review:

1. Clarify that case 2 already covers source removal indirectly.
2. Elevate the positional zip boundary drift in the harness.
3. Remove duplicate severity counting for the case 8 schema-version gap.
4. Distinguish clearly between missing named cases and missing data-strategy-level scenarios.
5. Broaden the operator-facing weakness assessment beyond case 23 alone.
6. Record the additional missing integration scenarios:
   - rename as delete+create
   - ghost-item boundary case
   - stale-page/resurrected item case

## Minimal Corrections Required To The Existing Compliance Review

- [ ] Correct the case 2 wording to acknowledge indirect unlink coverage
- [ ] Add the positional zip drift risk in the harness as High severity
- [ ] Remove duplicated severity treatment of the case 8 schema-version gap
- [ ] Separate named-case gaps from data-strategy-level gaps
- [ ] Expand operator-facing weakness analysis beyond case 23
- [ ] Add missing structural scenarios: rename pair, ghost item, stale page, resurrected item
