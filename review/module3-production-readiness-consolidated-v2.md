# Module 3 Production-Readiness Consolidated Review (Merged Stages 1-3 + Final)

Date: 2026-03-31
Scope: OneDrive client, auth/cache behavior, delta orchestration, staging download boundary.

## Executive verdict

Module 3 is substantially hardened and test-covered, but it is not yet at full production-grade for a critical foreign-ingress boundary. Remaining high risks are concentrated in crash-boundary durability, integrity when remote metadata is weak, and schema-drift fail-fast policy.

## Merged findings by category

### 1. Observability and logging trace

- **Weakness (medium):** Request/retry/backoff events are partially represented by counters, but event-level trace coverage is not yet guaranteed for every attempt.
  - Why it matters: incident reconstruction is harder without sequence logs.
  - Recommendation: add explicit structured trace events for request start/end, retry decisions, sleep delays, token refresh outcomes, and delta page transitions.

- **Weakness (medium):** Correlation context is not yet enforced as a stable run-wide key in every trace event.
  - Why it matters: log stitching across retries/pages/refresh is brittle.
  - Recommendation: require `poll_run_id`, `account_name`, `operation`, and `client_request_id` in all network trace events.

- **Weakness (medium):** Redaction is strong in exception hints but not centrally enforced at the logger boundary.
  - Why it matters: future ad-hoc logs could leak signed URLs or tokens.
  - Recommendation: central safe logging helper and sanitizer before emission.

### 2. Crash-boundary and staging safety

- **Weakness (high):** Crash after download-before-rename can leave stale temp artifacts without startup sweep/recovery policy.
  - Why it matters: staging drift and ambiguous downstream behavior.
  - Recommendation: startup reconciliation for stale `.tmp` files with age-based quarantine/cleanup.

- **Weakness (high):** Crash after rename-before-hash/registry insertion has no explicit bridging journal in Module 3.
  - Why it matters: re-download ambiguity until Module 4 state catches up.
  - Recommendation: append-only local download lifecycle journal (`started`, `completed`, `ready_for_hash`).

- **Weakness (medium):** Crash during delta pagination can replay safely but may incur excess work if cursor checkpoint timing is unlucky.
  - Why it matters: avoidable bandwidth and staging churn.
  - Recommendation: short-lived replay suppression cache tied to cursor generation.

### 3. Download integrity

- **Weakness (high):** Integrity guarantees degrade when `expected_size` is missing/unreliable.
  - Why it matters: truncated or partial files may survive in edge cases.
  - Recommendation: integrity mode policy:
    - strict: require reliable size or immediate extra verification marker
    - tolerant: quarantine uncertain files for downstream verification

- **Weakness (medium):** Size mismatch is retried/fails, but mismatch rates are not elevated to drift-health decisions.
  - Why it matters: systemic remote inconsistencies can go under-reported.
  - Recommendation: mismatch threshold alerting/fail-fast.

- **Weakness (medium):** No resumable range strategy for large files.
  - Why it matters: expensive restart costs under intermittent failures.
  - Recommendation: optional range-resume for very large files.

### 4. Schema drift resilience

- **Weakness (high):** Parser anomalies are counted but not threshold-enforced to fail fast.
  - Why it matters: severe API drift can silently degrade behavior.
  - Recommendation: per-account anomaly-ratio thresholds with warning/critical states and hard stop in critical.

- **Weakness (medium):** Drift telemetry is not summarized into an explicit drift state.
  - Why it matters: operators cannot quickly distinguish normal noise from contract breakage.
  - Recommendation: emit `drift_state` and reason summary per poll.

- **Weakness (medium):** Backward-incompatible field/type changes can appear as generic invalid payloads.
  - Why it matters: slower root-cause diagnosis.
  - Recommendation: explicit reason buckets for schema-shape incompatibility.

### 5. Delta feed stability

- **Weakness (medium):** In-run reducer handles duplicates/out-of-order events, but missing-item/stale-page reality still needs periodic reconciliation strategy.
  - Why it matters: long-lived feed anomalies can leave blind spots.
  - Recommendation: bounded reconciliation passes on schedule or anomaly-trigger.

- **Weakness (medium):** Ghost and stale-page rates are observed but not circuit-broken.
  - Why it matters: repeated bad pages/items waste runtime budget.
  - Recommendation: account-level anomaly breaker with cooldown and optional resync escalation.

- **Weakness (medium):** nextLink loops are detected, but repeated incidents across runs are not persisted/escalated.
  - Why it matters: recurring loops require deterministic escalation policy.
  - Recommendation: persist loop-incident count and force resync after threshold.

### 6. Token lifecycle

- **Strengths present:** refresh-once for 401/403, cache lock, corruption quarantine, identity sidecar binding.

- **Weakness (medium):** Identity sidecar trust is file-based without integrity attestation.
  - Why it matters: local tamper/accidental edits may misbind identity.
  - Recommendation: signed/hashed sidecar validation plus owner/mode checks.

- **Weakness (medium):** Cross-process refresh contention remains partially addressed.
  - Why it matters: rare parallel invocations can still thrash.
  - Recommendation: process singleton lock per account poll/refresh path.

### 7. Performance and throughput

- **Weakness (medium):** Serial-only execution limits throughput for larger multi-account backlogs.
  - Why it matters: poll windows may not clear queue.
  - Recommendation: optional bounded parallel workers while keeping serial default.

- **Weakness (medium):** Graph query shaping opportunities (`$select`, pagination shaping) not fully exploited.
  - Why it matters: avoidable payload and latency.
  - Recommendation: evaluate safe endpoint shaping compatible with delta semantics.

- **Weakness (medium):** Backpressure controls are mostly retry-based, not queue-aware/adaptive.
  - Why it matters: inefficient behavior under sustained incidents.
  - Recommendation: adaptive per-account cooldown/circuit breaker.

### 8. Integration readiness for Module 4

- **Weakness (medium):** Result contract blends diagnostics and anomalies.
  - Why it matters: consumer complexity and contract drift risk.
  - Recommendation: split into sections: payload, anomalies, diagnostics, lifecycle_state.

- **Weakness (medium):** Timestamp provenance (raw vs normalized) is not explicitly separated end-to-end.
  - Why it matters: dedupe/pairing semantics can blur.
  - Recommendation: carry both raw source timestamp and normalized timestamp with provenance flags.

- **Weakness (medium):** Sanitized item-ID staging names can theoretically collide.
  - Why it matters: low-probability overwrite risk.
  - Recommendation: deterministic short hash suffix from original item ID.

## Consolidated severity-ranked list

### High
1. Startup crash-recovery reconciliation for staging artifacts missing.
2. Download lifecycle journal bridging to Module 4 missing.
3. Integrity policy when expected size is missing/unreliable is incomplete.
4. Schema drift threshold-based fail-fast behavior missing.

### Medium
1. Full per-attempt structured trace logging not guaranteed.
2. Stable run-wide correlation context not enforced on all events.
3. Central guaranteed log sanitization gateway missing.
4. Ghost/stale-page circuit-breaker and escalation policy missing.
5. Periodic reconciliation strategy for delta blind spots missing.
6. Repeated nextLink loop escalation across runs missing.
7. Identity sidecar integrity attestation missing.
8. Cross-process token-refresh contention hardening incomplete.
9. Optional bounded parallelism missing.
10. Graph query shaping not yet leveraged.
11. Adaptive queue-aware backpressure controls missing.
12. Output contract sectioning for Module 4 should be tightened.
13. Raw vs normalized timestamp provenance split incomplete.
14. Sanitized ID collision guard (hash suffix) missing.
15. Explicit remediation-class mapping in errors could be improved.

### Low
1. Additional queue-pressure metrics for Module 4 scheduling can be improved.

## Most critical residual risk summary

The highest residual risk is silent correctness erosion under real-world failure combinations: process crashes around staging boundaries, uncertain file integrity when upstream metadata is weak, and severe schema drift without fail-fast thresholds. These should be resolved before treating Module 3 as fully production-ready for a critical ingress boundary.
