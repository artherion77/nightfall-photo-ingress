# Error Taxonomy and Resilience — Overview

**Status:** active — overview  
**Source:** extracted from `design/domain-architecture-overview.md` §15  
**Full specification:** [design/error-taxonomy-and-resilience.md](../error-taxonomy-and-resilience.md) — complete exception hierarchy, GhostItemError, `as_log_dict()` contract, and implementation detail  
**See also:** [architecture/observability.md](observability.md), [architecture/lifecycle.md](lifecycle.md)

---

## Exception Types

The adapter layer defines a structured hierarchy of exceptions, all carrying loggable fields without exposing sensitive material.

| Exception | Module | Meaning |
|-----------|--------|---------|
| `AuthError` | `adapters/onedrive/auth.py` | MSAL authentication failure (device-code flow, silent refresh) |
| `GraphError` | `adapters/onedrive/errors.py` | Microsoft Graph API request failure |
| `DownloadError` | `adapters/onedrive/errors.py` | File download failure (transport or HTTP error) |
| `GraphResyncRequired` | `adapters/onedrive/errors.py` | Graph delta returned `410 Gone`; cursor must be reset |

---

## URL and Token Redaction

All raise sites in the adapter call `redact_url()` before attaching a URL to an exception or log record.

Rules applied by `redact_url()`:

1. If the URL contains a query string, strip it entirely (pre-authenticated OneDrive download URLs embed bearer material as query parameters).
2. Truncate netloc+path to 80 characters for readability.
3. Never raise — if URL parsing fails, return a fixed sentinel `<unparseable-url>`.

Safe parameters (no query string) are logged at full length up to 120 characters.

---

## Retry Policy

`RetryPolicy` (`adapters/onedrive/retry.py`) governs backoff for transient failures:

- Retryable status codes: 429, 500, 502, 503, 504 and any `Retry-After` response.
- `Retry-After` header is parsed and honoured (seconds or HTTP-date format).
- Exponential backoff with jitter; configurable max attempts and base delay.
- Non-retryable errors (4xx except 429, auth errors, resync) propagate immediately.

---

## Delta Resync

On `GraphResyncRequired` (HTTP 410 from the Graph delta endpoint):

1. The current cursor is cleared.
2. The delta traversal restarts from `?token=latest`.
3. `resync_required_total` diagnostic counter is incremented.
4. Registry idempotency ensures no already-ingested files are re-processed.

---

## Auth Resilience Threshold

Consecutive authentication failures are counted per poll run. After ≥3 consecutive failures (`auth_failure_threshold` in config), the runtime:

1. Writes a status snapshot with `state = "auth_failed"`.
2. Emits a structured log at ERROR level with `component = "auth"`.
3. Stops the current poll run (does not retry further).

Diagnostic counters tracked per run:

| Counter | Meaning |
|---|---|
| `auth_refresh_attempt_total` | MSAL silent refresh attempts |
| `auth_refresh_success_total` | Successful token refreshes |
| `auth_refresh_failure_total` | Failed token refreshes |

---

## Throughput Bounds

Two soft bounds prevent poll runs from consuming unbounded time or I/O:

- `max_downloads_per_poll`: when the per-run download count reaches this limit, the current page is committed and the poll terminates cleanly. The cursor is advanced to the last committed page; the next scheduled run resumes from there.
- `max_poll_runtime_seconds`: wall-clock timeout. Same clean-commit behaviour applies.

Neither bound raises an exception; both result in an orderly, auditable stop.

---

## Edge Cases and Mitigations

| Edge case | Mitigation |
|---|---|
| OneDrive rename / move | Graph delta reports `deleted` + new `created`; metadata_index hit on `onedrive_id` prevents re-download after rename if size+mtime match |
| Partial / in-progress upload | Delta API only returns complete items; items without `file.hashes` or missing `@microsoft.graph.downloadUrl` are skipped |
| Name collision in pending/accepted/rejected | Template rendering + collision-safe suffixing preserves uniqueness |
| Delta cursor loss | Fall back to `?token=latest` (last 30 days) or full folder scan; registry idempotency prevents re-ingesting known files |
| Cross-pool atomic move | Ingest and accept transitions choose rename vs copy-verify-unlink based on filesystem topology |
| Concurrent poll runs | Explicit global process lock serializes full poll runs across CLI and timer paths; `Type=oneshot` is a secondary defense |
| Auth token expiry | MSAL handles refresh transparently; alert email after ≥3 consecutive auth failures |
| Operator manually moves accepted files away | `accepted_records` table preserves acceptance truth independent of current file location |
| Rejected retention and purge safety | Rejected artifacts remain in `rejected/` until explicit purge; purge rejects out-of-root paths |
| Immich DB purge or upgrade | Pipeline is Immich-independent; permanent library remains the viewer source of truth |
| HDD spin-up discipline | Staging, hashing, and registry all on SSD; HDD writes occur on pending/accept/reject transitions only |

---

*For observability and diagnostic counters, see [observability.md](observability.md).*  
*For crash recovery and lifecycle journal, see [lifecycle.md](lifecycle.md).*
