# Module 4 Final Cross-Module and State-Machine Review

Date: 2026-03-31
Scope: Ingest decision engine and storage commit workflow

## Review Basis

This assessment was performed against the current implementation and tests in:

- `nightfall_photo_ingress/pipeline/ingest.py`
- `nightfall_photo_ingress/storage.py`
- `nightfall_photo_ingress/registry.py`
- `nightfall_photo_ingress/pipeline/journal.py`
- `tests/test_m4_h1_atomic_finalize.py`
- `tests/test_m4_h2_journal_replay.py`
- `tests/test_m4_h4_contract_validation.py`
- `tests/test_m4_h7_audit_ordering.py`
- `tests/test_m4_h8_performance_scaling.py`
- `tests/test_m4_h9_security_policies.py`

---

## 1. Cross-Module Consistency Review (OneDrive client -> ingest pipeline)

### Findings

1. Missing explicit boundary adapter contract between OneDrive client outputs and ingest candidate objects.
- Why it matters: schema evolution in either module can drift silently.
- Severity: High
- Recommendation: introduce a single boundary mapper with schema version pinning and compatibility tests.

2. Timestamp semantics are not fully preserved across the boundary.
- Why it matters: forensic and pairing behavior can become ambiguous.
- Severity: Medium
- Recommendation: carry both `source_raw_timestamp` and normalized timestamp into ingest and persistence paths.

3. Error propagation semantics are not fully standardized across modules.
- Why it matters: operators may lose root-cause context when failures cross module boundaries.
- Severity: Medium
- Recommendation: enforce a shared error envelope with `account`, `onedrive_id`, `correlation_ids`, `phase`.

4. Candidate essentials are validated at the ingest boundary.
- Why it matters: this is a strength, but still convention-based without a strict adapter layer.
- Severity: Informational

---

## 2. State Machine Review (Ingest lifecycle)

Target lifecycle states:
- `ingest_started`
- `hash_completed`
- `storage_committed`
- `registry_persisted`

### Findings

1. Legal transition graph is not explicitly validated during replay.
- Why it matters: out-of-order or corrupted journal entries can be interpreted incorrectly.
- Severity: High
- Recommendation: add transition validator and quarantine illegal transitions with explicit operator alerts.

2. Journal replay currently uses latest-record logic and broad clearing behavior.
- Why it matters: mixed healthy/corrupt operations can lose useful evidence.
- Severity: High
- Recommendation: replay per operation ID, mark resolved operations, archive unresolved/corrupt entries.

3. Repeated/skipped/reverse transitions are not explicitly classified.
- Why it matters: hidden instability can look like normal replay noise.
- Severity: Medium
- Recommendation: add counters and warnings for duplicate, skipped, and reverse transitions.

4. Terminal audit ordering is deterministic and tested.
- Why it matters: this is a strength for forensic traces.
- Severity: Informational

---

## 3. Operator-Facing Failure Semantics Review

### Findings

1. Remediation guidance is not consistently attached to terminal failure outcomes.
- Why it matters: operator cannot quickly decide whether to retry, quarantine, or investigate.
- Severity: High
- Recommendation: define and attach deterministic remediation hints for each failure category.

2. Crash-recovery completeness is not emitted as a concise operator summary artifact.
- Why it matters: unclear whether recovery is partial or complete.
- Severity: Medium
- Recommendation: emit structured recovery summary with recovered, quarantined, unresolved counts and IDs.

3. Duplicate skipped vs reprocessed visibility exists but not as an explicit run digest.
- Why it matters: triage is slower and drift is harder to detect.
- Severity: Medium
- Recommendation: add per-run summary fields: accepted, known-discarded, prefilter-discarded, replay-recovered, quarantined.

4. Audit actor naming and broad event coverage are generally good.
- Why it matters: this is a strength but should be kept stable.
- Severity: Informational

---

## Additional Production Readiness Findings

### Decision correctness and idempotency

1. Crash between `storage_committed` and `registry_persisted` can lead to quarantine of potentially recoverable files.
- Why it matters: recoverable accepted assets may become operator intervention tasks.
- Severity: High
- Recommendation: replay path should attempt deterministic registry completion when sufficient journal data exists.

2. Metadata prefilter may false-discard if metadata index is stale.
- Why it matters: possible missed ingest of unknown content.
- Severity: Medium
- Recommendation: periodic verification sampling of prefilter hits.

### Storage commit integrity

1. Containment checks are strong but can be hardened for edge filesystems.
- Why it matters: path edge cases under unusual mounts/symlink behavior.
- Severity: Medium
- Recommendation: prefer `Path.relative_to` based containment where possible.

2. Collision race handling under concurrency can still fail commit attempts.
- Why it matters: rare but disruptive under parallel workers.
- Severity: Medium
- Recommendation: on collision race, rerun collision-safe naming once before failing.

### Staging recovery

1. Reconciliation classification relies mainly on age/suffix heuristics.
- Why it matters: can misclassify delayed operations.
- Severity: Medium
- Recommendation: combine journal cross-reference with on-disk heuristics.

2. Partial-hash state is implicit, not explicit.
- Why it matters: forensic replay clarity is reduced.
- Severity: Low
- Recommendation: add explicit `hash_in_progress` journal state.

### Integrity guarantees

1. Missing expected size policy can permit ingestion based on mode selection.
- Why it matters: can increase uncertainty for integrity-sensitive environments.
- Severity: Medium
- Recommendation: make strict integrity policy default in production profiles.

2. Optional post-commit verification on same-pool rename path is not enabled.
- Why it matters: rare filesystem anomalies may pass undetected.
- Severity: Low
- Recommendation: high-assurance mode for post-commit verification.

### Performance and scalability

1. Per-item transactional finalization may bottleneck at scale.
- Why it matters: throughput ceiling under bursts.
- Severity: Medium
- Recommendation: evaluate batched finalize operations or write queue.

2. Collision-heavy directories can degrade naming loops.
- Why it matters: avoidable filesystem lookup overhead.
- Severity: Low
- Recommendation: encourage hash-prefix partitioning in template defaults.

### Security

1. Startup permission self-check is not fully explicit for all output paths.
- Why it matters: deployment misconfiguration may go unnoticed.
- Severity: Medium
- Recommendation: add startup safety check for effective modes and ownership.

2. Filename sanitization may still produce operator-hostile names.
- Why it matters: shell and script friction.
- Severity: Low
- Recommendation: optional strict filename policy mode.

---

## Consolidated Severity-Ranked Remaining Issues

### High

1. No explicit cross-module boundary adapter contract (OneDrive client to ingest candidate mapping).
2. No strict legal-transition validator for ingest lifecycle replay.
3. Journal replay strategy can lose evidence for mixed healthy/corrupt operations.
4. Crash window between `storage_committed` and `registry_persisted` may quarantine recoverable files.
5. Operator remediation hints are inconsistent across terminal failure outcomes.

### Medium

1. Timestamp provenance not fully preserved across module boundary.
2. Error envelopes not standardized end-to-end.
3. Prefilter false-discard risk without verification sampling.
4. Concurrency race handling in collision commit path can be further hardened.
5. Staging reconciliation relies heavily on heuristics without full journal cross-reference.
6. Unknown-size integrity mode can permit ambiguity depending on config.
7. Throughput bottleneck risk from per-item transactional writes at high load.
8. Startup permission checks can be made more explicit.

### Low

1. Add explicit `hash_in_progress` state for forensic clarity.
2. Optional post-rename verification for high-assurance deployments.
3. Optional strict filename policy for operator ergonomics.
4. Improve default layout guidance to reduce collision-domain hotspots.

---

## Critical Risk Summary

The most critical remaining risks are boundary drift and replay correctness:

- Module boundary assumptions are not yet enforced by a strict adapter contract.
- Lifecycle replay does not fully validate legal transitions and can over-clear journal evidence.
- Crash recovery in the `storage_committed -> registry_persisted` window can quarantine files that may be recoverable.

Addressing these first will materially reduce correctness and recoverability risk before proceeding further.
