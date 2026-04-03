# Module 4 Final Cross-Module, State-Machine, and Operator-Facing Review

Date: 2026-03-31
Scope: Module 4 ingest decision engine and storage commit workflow, with emphasis on the Module 3 to Module 4 boundary.
Status: Review only. No implementation changes in this document.

## Review Basis

This assessment is based on the current implementation and test suite in:

- `nightfall_photo_ingress/onedrive/client.py`
- `nightfall_photo_ingress/pipeline/ingest.py`
- `nightfall_photo_ingress/pipeline/journal.py`
- `nightfall_photo_ingress/storage.py`
- `nightfall_photo_ingress/registry.py`
- `tests/test_m4_h1_atomic_finalize.py`
- `tests/test_m4_h2_journal_replay.py`
- `tests/test_m4_h4_contract_validation.py`
- `tests/test_m4_h7_audit_ordering.py`
- `tests/test_m4_h8_performance_scaling.py`
- `tests/test_m4_h9_security_policies.py`

---

## 1. Cross-Module Consistency Review (Module 3 -> Module 4)

### Finding 1.1: Boundary contract is validated, but not enforced through a dedicated adapter
Severity: High

Module 4 validates incoming staged candidates, which is good, but the Module 3 to Module 4 handoff is still mostly convention-based. There is no single explicit adapter or boundary mapper that converts OneDrive client output objects into ingest-side candidates under one pinned schema contract.

Why it matters:
- Drift between modules can be introduced without a single choke point.
- A future change in Module 3 field naming or normalization could silently break Module 4 assumptions.
- Cross-module integration tests will catch some drift, but the architecture should make drift harder to introduce in the first place.

Recommendation:
- Introduce a dedicated boundary adapter with an explicit schema version and compatibility checks.
- Keep the adapter as the only legal construction path for ingest-side candidates derived from Module 3 output.

### Finding 1.2: Timestamp semantics are not fully aligned across the boundary
Severity: Medium

Module 3 now distinguishes raw and normalized timestamps, but Module 4 primarily works from the normalized view.

Why it matters:
- Forensics and future pairing logic may need the original timestamp string from OneDrive.
- If normalization rules evolve, downstream behavior may shift while losing provenance.

Recommendation:
- Carry both raw source timestamp and normalized timestamp across the boundary.
- Persist both where useful for audit and future ingest decisions.

### Finding 1.3: Cross-module error envelope is not standardized
Severity: Medium

Module 3 and Module 4 both expose structured errors and diagnostics, but there is no unified cross-module error envelope.

Why it matters:
- Operators may see a failure in Module 4 without enough upstream context.
- Correlating OneDrive item failures across both modules remains more manual than necessary.

Recommendation:
- Standardize shared fields such as account, OneDrive ID, correlation IDs, phase, and remediation class.

### Finding 1.4: Candidate semantics are mostly aligned, but still rely on shared assumptions
Severity: Medium

Fields such as size, path, ID, and modified time are broadly aligned, but that alignment is not yet centrally documented in code.

Why it matters:
- Alignment is currently maintained by parallel code evolution and tests, rather than a hard interface boundary.

Recommendation:
- Add a single source-of-truth typed adapter or schema module for the Module 3 -> Module 4 boundary.

---

## 2. State Machine Review (Ingest Lifecycle)

Expected lifecycle states:
- `ingest_started`
- `hash_completed`
- `storage_committed`
- `registry_persisted`

### Finding 2.1: Legal transitions are not explicitly validated as a graph
Severity: High

The lifecycle journal captures useful steps, but replay logic does not yet validate transitions against a formally defined legal state graph.

Why it matters:
- Corrupted or out-of-order journal entries may be treated as latest truth.
- Illegal transition sequences are not clearly isolated from normal recovery.

Recommendation:
- Define a transition graph and validate journal sequences against it.
- Quarantine invalid sequences and emit an explicit operator-facing warning.

### Finding 2.2: Journal replay is operation-aware, but evidence handling can still be improved
Severity: High

Replay logic groups by operation, but the recovery model should preserve unresolved or corrupted sequences more explicitly rather than treating cleanup as a mostly operational concern.

Why it matters:
- Operators need reliable forensic evidence for interrupted ingests.
- A partial or corrupt journal should remain inspectable after replay.

Recommendation:
- Archive corrupt or unresolved operation records separately.
- Emit a replay summary with counts of recovered, quarantined, unresolved, and invalid transitions.

### Finding 2.3: Repeated or skipped transitions are tolerated more than classified
Severity: Medium

The system is replay-tolerant, but it does not strongly classify duplicate-phase, skipped-phase, or reverse-phase events as explicit lifecycle anomalies.

Why it matters:
- Replay-safe behavior can mask subtle corruption.
- Operators cannot easily distinguish expected recovery noise from true state-machine damage.

Recommendation:
- Add lifecycle anomaly counters and include them in operator-facing summaries.

### Finding 2.4: Terminal audit ordering is deterministic
Severity: Low

This is a strong point. Terminal audit sequences are deterministic and tested.

Recommendation:
- Keep this behavior unchanged.

---

## 3. Operator-Facing Failure Semantics Review

### Finding 3.1: Remediation guidance is not consistently attached to all failure outcomes
Severity: High

Module 4 emits useful actions and audit entries, but not all failure outcomes include clear next-step guidance.

Why it matters:
- Operators may not know whether a file was accepted, quarantined, discarded, or left in an ambiguous recovered state.
- Recovery flows are harder to use under incident pressure.

Recommendation:
- Attach a remediation class or operator action hint to all terminal ingest outcomes.
- Keep the guidance concise and stable.

### Finding 3.2: Crash recovery completeness is not surfaced as a concise operator summary
Severity: Medium

Recovery and replay do useful work, but the operator does not yet get a compact summary such as:
- recovered successfully
- quarantined due to ambiguity
- unresolved due to invalid lifecycle

Why it matters:
- Operators need to know whether crash recovery fully completed or partially degraded.

Recommendation:
- Emit a structured replay/recovery summary artifact after each recovery pass.

### Finding 3.3: Duplicate-skip versus replay-recovery visibility can be clearer
Severity: Medium

The system has the raw information to distinguish duplicate skip, prefilter discard, and replay recovery, but there is not yet a concise operator digest.

Why it matters:
- Deduplication and recovery behavior can look similar from the outside.

Recommendation:
- Add per-run operator summary counts for:
  - accepted
  - known-discarded
  - prefilter-discarded
  - replay-recovered
  - quarantined
  - invalid-lifecycle

### Finding 3.4: Audit actor naming is consistent
Severity: Low

The audit actor naming is coherent and already improved.

Recommendation:
- Keep the actor taxonomy stable.

---

## Consolidated Severity-Ranked Remaining Issues

### High

1. No dedicated, enforced boundary adapter between Module 3 output and Module 4 ingest input.
2. Lifecycle journal does not yet validate transitions against a formal legal state graph.
3. Replay and recovery semantics need stronger preservation and operator reporting for corrupt or unresolved operations.
4. Failure outcomes do not consistently include operator remediation guidance.

### Medium

1. Raw versus normalized timestamp semantics are not fully preserved across the boundary.
2. Cross-module error envelope is not standardized.
3. Candidate field alignment still depends on shared assumptions rather than a single hard interface.
4. Duplicate, skipped, and reverse lifecycle transitions are not surfaced as explicit anomalies.
5. Crash recovery results are not summarized in a compact operator-facing report.
6. Duplicate skip versus replay recovery is not summarized clearly enough for operators.

### Low

1. Terminal audit ordering is strong but should remain continuously tested.
2. Actor naming is stable and should remain unchanged.

---

## Most Critical Risks

The most important remaining risk is correctness drift at the boundary between the OneDrive client and the ingest pipeline, combined with incomplete formalization of the ingest state machine. Module 4 is much stronger internally after hardening, but before Module 5 it would benefit from:

1. A single enforced adapter contract between Module 3 and Module 4.
2. A formally validated ingest transition graph.
3. Stronger operator-facing recovery summaries and remediation guidance.

These changes would reduce the chance of silent cross-module drift and make interrupted ingest operations more understandable and safer to operate in production.

---

## Recommended Follow-Up Work

1. Add a Module 3 -> Module 4 boundary adapter with explicit schema versioning and compatibility tests.
2. Define and validate the ingest lifecycle state graph in journal replay.
3. Add structured recovery summaries and remediation hints to terminal outcomes.
4. Preserve raw timestamp provenance in ingest records and audit paths.
5. Standardize cross-module error envelopes and operator correlation identifiers.
