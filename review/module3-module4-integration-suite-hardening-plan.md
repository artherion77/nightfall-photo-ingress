# Module 3 And Module 4 Integration Suite Hardening Plan

Status: In progress (Chunk execution started)
Date: 2026-04-01
Scope: Priority-ordered hardening work to bring the implemented Module 3 and Module 4 integration suite into closer compliance with the approved specification

## Alignment check for Step 1 (Boundary Fidelity)

Step 1 from the post-audit plan is already represented in this hardening plan via
P0 and is the top priority.

Coverage mapping:
- Step 1.1 production-owned handoff artifact -> P0 item 1
- Step 1.2 remove positional zip coupling -> P0 item 2
- Step 1.3 ordering mismatch regression test -> P0 item 3

No scope extension was required. Execution format is refined below to enforce
chunk-by-chunk STOP gates.

## Chunk execution and STOP gates

### Chunk 1 (P0): Boundary artifact + positional decoupling + regression

- [x] Replace synthetic boundary reconstruction with production-owned handoff artifact.
- [x] Remove positional zip coupling between reduced candidates and downloaded paths.
- [x] Add regression test for ordering mismatch binding risk.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

### Chunk 2 (P1): Named case gaps

- [ ] Expand case 8 missing `item_id` and invalid schema version.
- [ ] Expand case 17 zero-byte allow/reject.
- [ ] Rewrite case 19 cross-pool verification mismatch scenario.
- [ ] Strengthen case 23 and 26 deterministic finalization assertions.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

### Chunk 3 (P3 + P4): Fixture capabilities + determinism

- [ ] Add crash hooks for after-staging-write, after-hash-complete,
  during-journal-append, during-journal-replay.
- [ ] Extend audit reader helpers.
- [ ] Introduce deterministic time control fixtures.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

### Chunk 4 (P2 + P5): Strategy scenarios + operator semantics

- [ ] Add rename-as-delete-plus-create, ghost-item boundary,
  stale/resurrected-item, corrupted-body scenarios.
- [ ] Tighten operator summary and audit-coherence assertions.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Priority Order

## P0 Critical Boundary Fidelity

- [ ] Replace the synthetic boundary reconstruction in [tests/integration/conftest.py]((root)/tests/integration/conftest.py) with a single explicit production-owned handoff artifact or boundary adapter.
- [ ] Remove the positional zip coupling between reduced candidates and `poll_result.downloaded_paths`.
- [ ] Add a dedicated regression test proving that candidate ordering mismatches cannot silently bind the wrong staged file to the wrong ingest candidate.

## P1 Required Spec Gaps In Named Cases

- [ ] Expand case 8 to cover missing `item_id`.
- [ ] Expand case 8 to cover invalid schema version.
- [ ] Expand case 17 to cover zero-byte `allow`.
- [ ] Expand case 17 to cover zero-byte `reject`.
- [ ] Rewrite case 19 to simulate true cross-pool verification mismatch after copy, not crash during copy.
- [ ] Strengthen case 23 to assert registry state, storage state, audit events, and operator-visible summary content together.
- [ ] Strengthen case 26 so deterministic final state is required: one accepted file, one accepted registry finalization path, and no duplicate terminal finalization.

## P2 Missing Integration Scenarios From Strategy And Category Intent

- [ ] Add rename-as-delete-plus-create integration coverage.
- [ ] Add explicit ghost-item boundary coverage.
- [ ] Add stale-page or resurrected-item integration coverage.
- [ ] Add corrupted-download-body coverage distinct from truncated download coverage.

## P3 Fixture Capability Expansion

- [ ] Extend `crash_injection_fixture` with after-staging-write interruption.
- [ ] Extend `crash_injection_fixture` with after-hash-complete interruption.
- [ ] Extend `crash_injection_fixture` with during-journal-append interruption.
- [ ] Extend `crash_injection_fixture` with during-journal-replay interruption.
- [ ] Extend `audit_reader_fixture` to expose actor, reason, `batch_run_id`, and sequence-oriented helpers.

## P4 Determinism And Time Control

- [ ] Introduce deterministic time control for replay, drift, and stale/orphan classification scenarios.
- [ ] Remove implicit reliance on current-time production behavior in integration assertions.

## P5 Operator-Facing Semantics Tightening

- [ ] Add assertions that operators can distinguish accepted, rejected, quarantined, duplicate-skipped, and replay-recovered outcomes.
- [ ] Add assertions for actor correctness on terminal audit rows.
- [ ] Add assertions for recovery summaries containing unresolved operation identifiers where applicable.
- [ ] Add assertions that per-run summaries reconcile with registry, storage, and audit state.

## Already Completed Baseline Items

- [x] Required integration fixture names exist
- [x] All seven required integration test files exist under [tests/integration]((root)/tests/integration)
- [x] All 26 specification cases are represented by name or direct mapping
- [x] Same-pool and cross-pool paths are both represented
- [x] Reject and purged registry preconditions are covered
- [x] Duplicate and replay categories exist

## Suggested Execution Order

1. P0 first, because all later strengthening depends on trustworthy boundary fidelity.
2. P1 second, because these are the clearest direct spec non-compliances.
3. P3 and P4 third, because fixture power and determinism enable the deeper scenarios.
4. P2 and P5 last, because they depend on stronger fixtures and boundary fidelity.
