# Module 3 Hardening Plan V2 (High + Medium Issues)

Date: 2026-03-31
Objective: Resolve all remaining high/medium risks from consolidated production review.
Constraints:
- Commit-sized, self-contained chunks.
- Each chunk includes dedicated tests + regression checks.
- Stop for review after each chunk.

## Chunk V2-1: Full trace logging contract (Point 1)

Commit goal:
- Guarantee structured trace visibility for every network attempt and control-flow decision.

Scope:
- Add explicit structured trace events for:
  - request attempt start/end
  - retry classification and delay decision
  - token refresh attempt/success/failure
  - delta page start/end and transitions
- Enforce stable correlation fields on each trace event:
  - `poll_run_id`, `account_name`, `operation`, `client_request_id` (when applicable)
- Keep sensitive redaction intact.

Deliverables:
- Trace-event helper and call sites in OneDrive client.
- JSON formatter support for extra structured fields.
- Dedicated tests for event coverage and correlation stability.

Tests:
- Unit: trace event payload shape and required keys.
- Integration (mocked): retry/backoff, refresh, and pagination emit expected event sequence.
- Regression: no sensitive URL query/tokens in trace payloads.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-2: Centralized safe log sanitizer

Commit goal:
- Enforce one guaranteed redaction/sanitization path before logging.

Scope:
- Introduce central sanitizer for URL/token-like fields.
- Apply sanitizer to all trace and error log emission points.
- Add defensive redaction for nested dict/list payloads.

Tests:
- Unit: sanitizer redacts secrets across nested payloads.
- Regression: attempted raw signed URL/token logging gets sanitized.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-3: Startup staging crash-recovery sweep

Commit goal:
- Make staging safe and deterministic after abrupt process termination.

Scope:
- Startup reconciliation pass for `.tmp` artifacts by age/size.
- Quarantine or remove stale partial files per policy.
- Emit recovery counters and operator-visible summary.

Tests:
- Integration (mocked filesystem): crash remnants are classified and handled correctly.
- Regression: no valid finalized files are mistakenly removed.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-4: Download lifecycle journal bridge

Commit goal:
- Preserve deterministic state between download completion and Module 4 ingestion.

Scope:
- Append-only local lifecycle journal:
  - `download_started`
  - `download_completed`
  - `ready_for_hash`
- Idempotent replay/recovery semantics.

Tests:
- Unit: journal write/read/append integrity.
- Integration: crash-restart replay consistency.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-5: Integrity policy when expected size is weak

Commit goal:
- Prevent silent truncation acceptance when size metadata is missing/untrusted.

Scope:
- Add integrity mode policy (`strict`/`tolerant`).
- Strict mode enforces stronger acceptance criteria.
- Tolerant mode quarantines uncertain downloads.
- Track uncertainty counters.

Tests:
- Integration: missing size, wrong size, empty 200, early EOF scenarios.
- Regression: uncertain downloads are not silently accepted in strict mode.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-6: Schema drift thresholds and fail-fast

Commit goal:
- Convert anomaly counters into explicit drift-health behavior.

Scope:
- Add per-account threshold configuration.
- Compute drift state: `normal`, `warning`, `critical`.
- Fail-fast on critical threshold breach.

Tests:
- Unit: threshold evaluation matrix.
- Integration: critical drift triggers controlled stop and clear reason.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-7: Delta anomaly breakers and escalation

Commit goal:
- Contain repetitive feed anomalies with deterministic escalation.

Scope:
- Ghost/stale-page circuit breaker with cooldown.
- Persistent repeated-loop incident counters.
- Forced resync escalation after threshold.

Tests:
- Integration: repeated anomalies trigger breaker and escalation paths.
- Regression: normal feeds remain unaffected.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-8: Token lifecycle integrity and contention hardening

Commit goal:
- Harden sidecar trust and concurrent refresh behavior.

Scope:
- Identity sidecar integrity attestation.
- Strict owner/mode validation before use.
- Per-account singleton guard for refresh-sensitive paths.

Tests:
- Unit: tampered sidecar detection.
- Integration: concurrent refresh race simulation.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-9: Throughput + adaptive backpressure

Commit goal:
- Improve scaling while maintaining safety.

Scope:
- Optional bounded parallelism (serial default).
- Adaptive backpressure/cooldown by account health.
- Runtime budget-aware scheduling.

Tests:
- Integration: bounded worker behavior under mixed account health.
- Regression: serial mode remains deterministic default.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk V2-10: Module 4 interface contract stabilization

Commit goal:
- Stabilize output contract for ingestion module consumers.

Scope:
- Split result sections: payload/anomalies/diagnostics/lifecycle_state.
- Explicit raw vs normalized timestamp fields.
- Deterministic sanitized-ID collision suffixing.

Tests:
- Unit: contract schema tests.
- Regression: compatibility with existing module expectations.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Execution order recommendation

1. V2-1
2. V2-2
3. V2-3
4. V2-4
5. V2-5
6. V2-6
7. V2-7
8. V2-8
9. V2-9
10. V2-10

## Tick-off checklist

- [x] V2-1 committed
- [x] V2-2 committed
- [x] V2-3 committed
- [x] V2-4 committed
- [x] V2-5 committed
- [x] V2-6 committed
- [x] V2-7 committed
- [x] V2-8 committed
- [x] V2-9 committed
- [ ] V2-10 committed
