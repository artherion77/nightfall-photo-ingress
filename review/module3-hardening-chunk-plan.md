# Module 3 Hardening Plan in Commit-Sized Chunks

Date: 2026-03-31
Goal: Implement robustness fixes in small, reviewable, self-contained commits.
Rule: No chunk should mix unrelated concerns.

## Chunk 1: Error taxonomy and safe logging envelope

Commit goal:
- Introduce explicit error classes and message policy without changing transport behavior yet.

Scope:
- Define adapter-level exception hierarchy.
- Add redaction helpers for URLs/tokens.
- Ensure logs and raised messages never expose pre-authenticated download URLs.

Deliverables:
- [x] Error classes added and used by auth/client boundaries.
- [x] URL redaction utility with tests.
- [x] Structured error payload fields (code, account, operation, status).

Tests:
- [x] Unit: redaction strips query secrets and opaque tokens.
- [x] Unit: error rendering avoids sensitive URL disclosure.

Result: 27 new tests + 60 total passing. Committed.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 2: Retry/backoff core with robust Retry-After parsing

Commit goal:
- Centralize retry decisions and delay computation.

Scope:
- Implement retry policy for 429/500/502/503/504 and transport exceptions.
- Parse Retry-After seconds and HTTP-date safely.
- Add capped exponential backoff with jitter fallback.

Deliverables:
	- [x] Retry policy module.
	- [x] Deterministic test hooks for jitter/sleeper.

Tests:
	- [x] Unit: malformed/missing Retry-After fallback.
	- [x] Unit: status classification matrix.
	- [x] Unit: retry cap behavior.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 3: Streaming downloader with integrity guards

Commit goal:
- Replace memory-buffer download with streamed writes and integrity checks.

Scope:
- Stream response body in chunks to .tmp.
- Validate bytes written against expected non-zero size where available.
- Ensure cleanup on failure and atomic finalize on success.

Deliverables:
- [ ] Streaming download path implemented.
- [ ] Empty-body 200 anomaly handling.
- [ ] Temp file cleanup guarantees documented.

Tests:
- [ ] Integration (mocked): large content streamed without memory buffering.
- [ ] Unit: expected-size mismatch triggers retry/fail.
- [ ] Unit: 200 + empty body with expected size > 0 is treated as anomaly.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 4: Download URL re-resolve and ghost-item handling

Commit goal:
- Make stale/expired downloadUrl recoverable once, then quarantine cleanly.

Scope:
- On 401/403/404 for downloadUrl, fetch fresh item metadata once and retry.
- If still unavailable (missing downloadUrl, repeated 404), classify as ghost item.
- Emit actionable counters/reason codes.

Deliverables:
- [ ] Re-resolve flow added.
- [ ] Ghost-item reason codes.

Tests:
- [ ] Integration (mocked): first URL fails, refresh succeeds.
- [ ] Integration (mocked): refresh fails -> ghost item classification.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 5: Delta pagination hardening (loops, 410 reset, stale pages)

Commit goal:
- Harden delta state machine against known Graph quirks.

Scope:
- Add nextLink cycle detection and max-page/max-runtime guards.
- Implement 410 reset handling with controlled resync path.
- Add stale/replay anomaly counters.

Deliverables:
- [ ] Pagination guardrails.
- [ ] 410 handling path.
- [ ] Resync marker persistence.

Tests:
- [ ] Unit: repeated nextLink terminates with explicit error.
- [ ] Integration (mocked): 410 response triggers resync flow.
- [ ] Unit: page ceiling enforcement.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 6: Delta event normalization and in-run dedupe/merge

Commit goal:
- Make candidate list deterministic despite duplicate/out-of-order events.

Scope:
- Build in-run reducer keyed by item ID.
- Last-observed event wins for file entries; deletion precedence rules applied.
- Preserve audit traces for dropped duplicates.

Deliverables:
- [ ] Candidate reducer component.
- [ ] Reducer stats in logs.

Tests:
- [ ] Unit: duplicate file events collapse deterministically.
- [ ] Unit: delete+create rename pattern normalization.
- [ ] Unit: out-of-order events produce stable final state.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 7: Auth cache resilience and account identity binding

Commit goal:
- Remove cache race/corruption/identity ambiguity.

Scope:
- Add file-locking around token cache read/write.
- Handle cache deserialize corruption with quarantine + actionable error.
- Bind silent token retrieval to expected account identity metadata.
- Add one retry path for 401/403 Graph requests with forced token refresh.

Deliverables:
- [ ] Cache lock abstraction.
- [ ] Identity binding fields persisted and validated.
- [ ] Refresh-once request wrapper.

Tests:
- [ ] Unit: corrupted cache handling path.
- [ ] Unit: wrong-account cache does not silently proceed.
- [ ] Integration (mocked): 401 then refreshed token succeeds.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 8: Path safety and metadata validation tightening

Commit goal:
- Eliminate malformed candidate edge cases and path encoding faults.

Scope:
- Require non-empty item ID and name for candidate acceptance.
- Enforce safe filename normalization for staging names.
- Explicitly encode initial delta path segments.
- Keep parent path metadata best-effort only.

Deliverables:
- [ ] Candidate validator.
- [ ] Safe staging naming helper.
- [ ] Encoded root delta URL builder.

Tests:
- [ ] Unit: malformed payload values rejected with reason codes.
- [ ] Unit: path encoding behavior for spaces/special chars.
- [ ] Unit: missing parentReference handled safely.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 9: Observability and support diagnostics

Commit goal:
- Make failures diagnosable in production without sensitive leakage.

Scope:
- Add client-request-id per Graph request.
- Capture and log response request-id/correlation fields.
- Add counters for throttling, ghost items, stale pages, retries, and resyncs.

Deliverables:
- [ ] Correlation ID plumbing.
- [ ] Metrics/counter emission points.
- [ ] Updated operator troubleshooting notes.

Tests:
- [ ] Unit: correlation IDs present in outbound headers.
- [ ] Integration (mocked): counters increment per anomaly class.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

## Chunk 10: Robustness regression suite and acceptance gate

Commit goal:
- Lock reliability behavior with a dedicated regression suite.

Scope:
- Add end-to-end mocked scenarios combining throttling, loops, token refresh, large downloads, and ghost items.
- Add CI target for robustness suite.

Deliverables:
- [ ] tests/test_onedrive_robustness_regression.py
- [ ] CI command and docs update.

Tests:
- [ ] Full regression suite green.
- [ ] No sensitive URLs in logs/asserted outputs.

Review gate:
=== STOP: Awaiting user feedback before proceeding ===

---

## Tick-off checklist (execution order)

- [ ] Chunk 1 committed
- [ ] Chunk 2 committed
- [ ] Chunk 3 committed
- [ ] Chunk 4 committed
- [ ] Chunk 5 committed
- [ ] Chunk 6 committed
- [ ] Chunk 7 committed
- [ ] Chunk 8 committed
- [ ] Chunk 9 committed
- [ ] Chunk 10 committed

## Suggested commit message template per chunk

Use:
- feat(module3): <short capability>
Or:
- harden(module3): <short robustness change>
Or:
- test(module3): <coverage focus>

Example:
- harden(module3): add retry policy with malformed Retry-After handling
