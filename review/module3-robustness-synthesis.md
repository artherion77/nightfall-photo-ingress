# Module 3 Robustness Review Synthesis (Stage 1 + 2 + 3)

Date: 2026-03-31
Scope: OneDrive adapter only (auth + delta + download)
Code reviewed:
- [nightfall_photo_ingress/onedrive/client.py](nightfall_photo_ingress/onedrive/client.py)
- [nightfall_photo_ingress/onedrive/auth.py](nightfall_photo_ingress/onedrive/auth.py)
- [tests/test_onedrive_delta.py](tests/test_onedrive_delta.py)
- [tests/test_onedrive_auth.py](tests/test_onedrive_auth.py)

## 1. Stage coverage mapping for the newly supplied vectors

Legend:
- Covered S1: identified in first-stage code review
- Covered S2: identified in second-stage cross-validation
- New S3: additional refinement from this stage

| Failure vector | Covered S1 | Covered S2 | New S3 detail | Current Module 3 status |
|---|---|---|---|---|
| Inconsistent delta feeds (duplicates/missing/out-of-order) | Partial | Yes | Clarify merge semantics must be last-write-wins by item ID within poll page sequence | Not handled |
| Missing or incorrect metadata.hashes | Partial | Yes | Explicitly treat hashes as advisory telemetry only, never trust for accept/reject | Partially handled |
| downloadUrl instability/expiry/403 mid-flow | Partial | Yes | Add single re-resolve step via Graph item fetch when URL fails transiently | Not handled |
| 429/503 without Retry-After or malformed Retry-After | Yes | Yes | Add robust parser supporting invalid/missing header fallback + jitter | Not handled |
| Token refresh race/silent refresh account mismatch | Partial | Yes | Bind cache to expected account identity and retry-once for 401/403 | Not handled |
| Rename/move anomalies as delete+create with weak metadata | Partial | Yes | Add same-cycle correlation by item ID and path hints, avoid timestamp reliance | Not handled |
| Delta nextLink loops | Yes | Yes | Add visited-token/cycle guard + max-page ceiling + resync fallback | Not handled |
| Stale pages / resurrected old items | No | Partial | Add monotonic poll guardrails + replay-safe dedupe + anomaly counters | Not handled |
| Ghost items (delta item but no downloadUrl or 404 fetch) | Yes | Partial | Add quarantine reason codes and per-account counters | Partially handled |
| Large-file partial reads / truncation / early EOF | Yes | Yes | Require streaming with byte-count validation against expected size | Not handled |
| 200 OK with empty body | No | Yes | Treat non-zero expected size + empty body as retryable anomaly | Not handled |

## 2. Third-stage net-new findings

These were not explicit in stage 1 and were only partly addressed in stage 2, now made concrete for implementation policy.

1. Stale/resurrected delta pages need explicit anomaly handling
- Why this matters:
  - Replay or stale pages can re-introduce previously deleted items and trigger unnecessary downloads.
- Impact in current code:
  - [nightfall_photo_ingress/onedrive/client.py](nightfall_photo_ingress/onedrive/client.py) accepts all parsed file items and has no replay-window suppression.
- Recommendation:
  - Add per-account in-memory dedupe set for current poll.
  - Add persisted replay markers keyed by item ID + etag/ctime snapshot if available.
  - Emit anomaly counters when a previously deleted item reappears without meaningful metadata change.
- Severity: Medium

2. Retry policy must handle malformed Retry-After robustly
- Why this matters:
  - Real APIs often return missing or malformed Retry-After values under throttling.
- Impact in current code:
  - float(retry_after) can raise ValueError and abort retry path.
- Recommendation:
  - Parse Retry-After defensively.
  - Support both seconds and HTTP-date.
  - Fallback to capped exponential backoff with jitter.
- Severity: High

3. downloadUrl failure path should support one re-resolve before hard fail
- Why this matters:
  - Pre-authenticated URLs can expire quickly; immediate hard failure increases false negatives.
- Impact in current code:
  - Download failure is terminal for that candidate.
- Recommendation:
  - On 401/403/404 during download, request fresh item metadata once and retry download once.
- Severity: High

4. Empty-body success must be integrity-checked
- Why this matters:
  - 200 with empty body has been observed in production-like workloads.
- Impact in current code:
  - Empty content is accepted and written as valid download.
- Recommendation:
  - If expected size > 0 and bytes written == 0, treat as transient anomaly and retry.
- Severity: High

5. Delta inconsistency requires deterministic in-run collapse strategy
- Why this matters:
  - Duplicate or out-of-order events can produce conflicting candidate states in one run.
- Impact in current code:
  - Candidates are appended in raw order without conflict resolution.
- Recommendation:
  - Collapse candidates by item ID in run scope.
  - Keep last state event in observed sequence.
  - Maintain delete precedence where applicable.
- Severity: High

## 3. Consolidated review list across all three stages

### High severity

1. Non-streaming download path risks memory exhaustion and poor large-file reliability.
2. Missing network exception handling for httpx transport failures.
3. Sensitive URL leakage in Graph/download error messages.
4. No 401/403 refresh-and-retry loop for token expiry during poll.
5. Missing 410 delta reset handling with resync path.
6. Weak retry policy (limited statuses, no jitter, fragile Retry-After parsing).
7. No pagination cycle guard for repeated nextLink values.
8. No in-run candidate dedupe/merge strategy for duplicate or out-of-order delta items.
9. No integrity guard for 200 OK empty-body anomalies.
10. No resume/byte-range strategy for large-file partial reads.
11. downloadUrl expiry path lacks one-time re-resolve attempt.

### Medium severity

1. Cursor checkpoint strategy may cause expensive replay after partial failure.
2. Missing strict validation for candidate id/name/size fields.
3. Potential staging filename collisions when item_id is missing/empty.
4. Stale/resurrected delta pages not explicitly detected/flagged.
5. Silent token acquisition chooses first cached identity, not bound account.
6. Token cache deserialize/corruption handling not defensive.
7. Token cache file access has no explicit inter-process lock.
8. Initial delta path composition lacks explicit path-segment encoding.
9. parentReference path assumptions may fail for rename/move events.
10. Missing correlation IDs for Graph request diagnostics.

### Low severity

1. CLI help text still references module-stub behavior in places.
2. Missing operational metrics for anomaly classes (ghost items, stale pages, malformed metadata).

## 4. Test coverage gaps (current tests vs required robustness)

Current tests validate:
- basic delta parsing filters
- simple Retry-After happy-path retry
- account order behavior
- basic auth cache presence checks

Missing critical tests:
- transport exception retries
- malformed/missing Retry-After handling
- 401/403 token-refresh retry path
- 410 delta-reset and resync behavior
- nextLink cycle detection
- duplicate/out-of-order delta merge behavior
- empty-body 200 handling
- large streamed download + partial read recovery
- download URL re-resolve fallback
- token cache corruption and identity mismatch

## 5. Practical assumptions to remove before production

1. Graph payload fields are always complete and well-typed.
2. Retry-After is always valid numeric seconds.
3. nextLink pages are always finite and acyclic.
4. downloadUrl remains valid for entire poll window.
5. 200 response always carries complete file body.
6. One token cache always maps to exactly one account identity.

## 6. Review conclusion

Module 3 is functionally useful for controlled happy paths but not production-robust for real Graph/OneDrive behavior under throttling, delta anomalies, token churn, and large-file transfer instability.

The highest-risk gaps are:
1. Delta state-machine hardening (410, loops, replay anomalies)
2. Download integrity and streaming resilience (partial/empty/truncated responses)
3. Auth and retry safety (token refresh races, malformed retry metadata)
