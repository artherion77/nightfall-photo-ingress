# Error Taxonomy and Resilience

Status: active
Created: 2026-04-03
Updated: 2026-04-03

---

## 1. Purpose

This document describes the structured error hierarchy for the OneDrive adapter,
the URL and token redaction policy enforced at all raise sites, the retry backoff
mechanism, the delta resync circuit-breaker, and the throughput bounds that control
poll run duration and download volume.

---

## 2. Exception Hierarchy

All adapter exceptions derive from `OneDriveAdapterError`, which extends `RuntimeError`.
Every exception type carries structured, loggable fields via `as_log_dict()` and never
exposes sensitive material (tokens, pre-authenticated URLs) in its `str()` representation.

```
OneDriveAdapterError
├── AuthError
├── GraphError
│   ├── GraphResyncRequired
│   └── DownloadError
│       └── GhostItemError
```

### 2.1 OneDriveAdapterError (base)

All adapter errors carry:

| Attribute | Type | Meaning |
|-----------|------|---------|
| `code` | str | Machine-readable error code (e.g. `auth_error`, `graph_error`) |
| `account` | str or None | Account name from config (if known at raise site) |
| `operation` | str or None | Short description of the failing operation |
| `status_code` | int or None | HTTP status code, if applicable |
| `safe_hint` | str | Log-safe non-sensitive hint for the operator |

`as_log_dict()` returns these fields as a dict suitable for structured log `extra=`.

### 2.2 AuthError

Raised when authentication cannot produce a usable access token. Examples: no cached
account found, device-code flow failure, corrupted/unreadable MSAL token cache.

- Default `code`: `auth_error`
- Default `operation`: `auth`

### 2.3 GraphError

Raised for non-recoverable or unclassified Microsoft Graph API failures. The `url`
parameter at every raise site is always passed through `redact_url()` before storage;
the raw URL never appears in `str(exc)`, `safe_hint`, or tracebacks.

- Default `code`: `graph_error`

### 2.4 GraphResyncRequired

Raised when the Graph delta endpoint returns HTTP `410 Gone`, signalling that the
stored delta cursor is no longer valid and a full delta re-crawl is required.

- `code`: `graph_resync_required`
- Additional attribute: `resync_url` — the `Location` header from the `410` response,
  if provided (not pre-authenticated; stored as-is).
- On receipt, the current delta cursor is discarded and delta traversal restarts from
  `?token=latest`. The `resync_required_total` diagnostic counter is incremented.
- The resync is transparent to the ingest layer: the registry's `ON CONFLICT DO UPDATE`
  guards prevent any already-ingested file from being re-processed.

### 2.5 DownloadError

Raised for failures specific to file content download, as distinct from metadata or
API failures. Carries an optional `item_id` attribute (OneDrive item ID).

- Default `code`: `download_error`

### 2.6 GhostItemError

Subclass of `DownloadError`. Raised when a delta feed yields an item that cannot be
downloaded — most commonly because the item's pre-authenticated download URL has expired
or the item was deleted after the delta page was fetched.

- `code`: `ghost_item`
- Handled by the ghost-item circuit-breaker: each ghost is recorded in
  `delta_anomaly_counts`; if the count per page exceeds `delta_breaker_ghost_threshold`,
  the page is abandoned and the cursor is not advanced.

---

## 3. URL and Token Redaction Policy

Pre-authenticated OneDrive and SharePoint download URLs embed bearer tokens as query
parameters (`tempauth`, `sig`, `sp`, `sv`, etc.). Any unredacted URL in a log line,
exception message, or stack trace constitutes a credential leak.

### 3.1 redact_url()

Defined in `adapters/onedrive/errors.py`. Applied at every raise site before a URL
is stored in an exception attribute or passed to a log call.

Rules applied in order:

1. **Empty string** → return sentinel `<empty-url>`
2. **URL parse failure** → return sentinel `<unparseable-url>`
3. **Query string present** → strip the entire query string; append ` [query redacted]`
   to the base URL (scheme + netloc + path).  Truncate base to 80 chars if longer.
4. **No query string** → pass through up to 120 chars; truncate with `…` if longer.

This approach (strip entire query string rather than redacting named parameters) is
belt-and-suspenders: it does not depend on `_SECRET_PARAMS` pattern enumeration being
complete.

### 3.2 redact_token()

Also defined in `errors.py`. Applied to access tokens before they appear in log extras.
Shows only the first 6 characters and total length:
`eyJ0eX…[1432 chars]`

### 3.3 sanitize_extra()

Defined in `adapters/onedrive/safe_logging.py`. Applied to all `extra=` dicts before
they reach the logging handler.

- Recursively traverses dicts, lists, and tuples.
- String values on token-like keys (matching `_TOKEN_KEY_RE`: `token`, `secret`,
  `authorization`, `auth`, `password`, `sig`, `tempauth`, `client_secret`) are
  replaced with `redact_token()`.
- URL-looking string values (matching `https?://`) are replaced with `redact_url()`.
- `Path` values are converted to `str`.
- Never raises; on internal error returns a safe fallback.

The `_RedactingFormatter` in `logging_bootstrap.py` applies an additional URL-redaction
pass to formatted log lines emitted by transport libraries (`httpx`, `httpcore`) that
do not use structured logging.

---

## 4. Retry Policy

`RetryPolicy` (`adapters/onedrive/retry.py`) is an immutable `dataclass` governing
backoff for transient HTTP failures.

### 4.1 Retryable Status Codes

```python
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
```

- `429` — Too Many Requests (rate limiting); `Retry-After` header is honoured.
- `500/502/503/504` — transient infrastructure errors.
- All other 4xx codes (including `401`, `403`) are not retried; they propagate
  immediately or trigger a single token-refresh attempt (see §5.1).

### 4.2 RetryPolicy Fields

| Field | Default | Description |
|-------|---------|-------------|
| `max_attempts` | `4` | Total attempts including first; `1` = no retries |
| `base_delay` | `1.0` | Base backoff interval in seconds |
| `max_delay` | `60.0` | Upper cap on any computed sleep duration |

### 4.3 Retry-After Handling

`parse_retry_after()` accepts:
- **Numeric string** (e.g. `"60"`, `"1.5"`) → parsed as seconds, clamped to ≥ 0.
- **HTTP-date string** (RFC 7231) → converted to seconds from now, clamped to ≥ 0.
- **Null or empty** / **unrecognised format** → `None` (caller falls back to
  exponential backoff).

Never raises.

### 4.4 Delay Computation

```
if retry_after is not None:
    delay = min(retry_after, policy.max_delay)
else:
    backoff = policy.base_delay * 2^(attempt-1)
    delay = min(backoff + jitter, policy.max_delay)
```

`jitter` defaults to `random.uniform(0.0, 1.0)`. Tests pass `lambda: 0.0` for
deterministic results.

---

## 5. Auth Resilience

### 5.1 Single-Attempt Token Refresh

When the Graph API returns `401` or `403`, the adapter makes a single silent MSAL
token refresh attempt and retries the request once. This covers the common case of
a cached token that has expired since the poll started.

Outcomes:
- **Refresh succeeds** → `auth_refresh_success_total` incremented; request retried.
- **Refresh fails** (`AuthError` raised by MSAL) → `auth_refresh_failure_total`
  incremented; a `GraphError` with `code="graph_auth_refresh_failed"` is raised.

Only one refresh is attempted per request; if a second `401`/`403` follows the
refreshed request, the error is raised immediately.

### 5.2 Auth Failure Counters

Per poll run, the following diagnostic counters track authentication health:

| Counter | Meaning |
|---------|---------|
| `auth_refresh_attempt_total` | Number of token refresh attempts initiated |
| `auth_refresh_success_total` | Successful refreshes |
| `auth_refresh_failure_total` | Failed refreshes (MSAL could not produce a token) |

These are accumulated per account per poll run and emitted in the status snapshot
`details` block on run completion.

### 5.3 Auth Failure Alert Threshold

> **Planning item** — not yet implemented as of 2026-04-03.
>
> A consecutive-failure threshold (planned: ≥3 auth failures per account per run
> → status `state = "auth_failed"` + structured ERROR log) is tracked in
> `planning/planned/cli-domain-post-audit-next-steps.md` (Module 6 observability work).
>
> Current behaviour: any auth failure on an account raises an exception that causes
> the account's poll to abort and is reported in the status snapshot as a failure.

---

## 6. Delta Resync and Circuit-Breakers

### 6.1 Delta Resync (410 Gone)

When `GraphResyncRequired` is raised:
1. The current per-account delta cursor is cleared from the registry.
2. Delta traversal for that account restarts from `?token=latest`.
3. `resync_required_total` diagnostic counter is incremented.
4. Ingest idempotency (registry `ON CONFLICT DO UPDATE`) prevents already-ingested
   files from being duplicated.

The resync is bounded: `delta_loop_resync_threshold` in config sets the maximum number
of resyncs per poll run for one account before the account is considered unhealthy and
the run aborts.

### 6.2 Ghost Item Circuit-Breaker

If a delta page contains more ghost items (items that exist in the feed but cannot be
downloaded) than `delta_breaker_ghost_threshold`, the page is abandoned. The cursor is
not advanced past that page.

### 6.3 Stale Page Circuit-Breaker

If a delta page is estimated to be stale (based on timestamp drift between page items
and current wall clock), and the count of stale pages in a run exceeds
`delta_breaker_stale_page_threshold`, the traversal stops and logs a diagnostic event.
A cooldown period (`delta_breaker_cooldown_seconds`) must elapse before another resync
is attempted.

---

## 7. Throughput Bounds

Two soft limits prevent poll runs from consuming unbounded time or I/O. Both result in
an orderly stop, not an abort — the current delta page side-effects are committed before
stopping, and the cursor is advanced to the last committed page.

### 7.1 max_downloads_per_poll

Default: `200`. When the per-account download count reaches this limit:
1. Processing of the current page completes.
2. The cursor is advanced to the checkpoint after the last completed page.
3. The poll run returns with a `downloads_budget_exhausted` anomaly count.
4. The next scheduled timer invocation resumes from the saved cursor.

### 7.2 max_poll_runtime_seconds

Default: `300` (5 minutes). A wall-clock deadline is set at the start of `poll_accounts`:

```python
deadline = monotonic() + app_config.core.max_poll_runtime_seconds
```

Before each new account is polled, the remaining budget is checked. If the budget is
exhausted, `_runtime_budget_exhausted_result()` is returned for that account without
starting a poll — the account is not partially polled. The status snapshot reflects
`scheduler_runtime_budget_exhausted` in the anomaly counts.

---

## 8. Edge Cases and Mitigations

| Edge case | Mitigation |
|---|---|
| OneDrive rename / move | Graph delta reports `deleted` + new `created`; metadata_index hit on `onedrive_id` prevents re-download after rename if size+mtime match |
| Partial / in-progress upload | Delta API only returns complete items; items without `file.hashes` or missing `@microsoft.graph.downloadUrl` are skipped |
| Name collision in pending/accepted/rejected | Template rendering + collision-safe suffixing preserves uniqueness |
| Delta cursor loss | Fall back to `?token=latest` (last 30 days) or full folder scan; registry idempotency prevents re-ingesting known files |
| Cross-pool atomic move | Ingest and accept transitions choose rename vs copy-verify-unlink based on filesystem topology |
| Concurrent poll runs | Explicit global process lock serializes full poll runs across CLI and timer paths; `Type=oneshot` is a secondary defense |
| Auth token expiry | MSAL handles refresh transparently; auth failure threshold triggers status snapshot `auth_failed` after repeated failures |
| Operator manually moves accepted files away | `accepted_records` table preserves acceptance truth independent of current file location |
| Rejected retention and purge safety | Rejected artifacts remain in `rejected/` until explicit purge; purge rejects out-of-root paths |
| Immich DB purge or upgrade | Pipeline is Immich-independent; permanent library remains the viewer source of truth |
| HDD spin-up discipline | Staging, hashing, and registry all on SSD; HDD writes occur on pending/accept/reject transitions only |

---

*For observability and diagnostic counters, see [observability.md](observability.md).*  
*For crash recovery and lifecycle journal, see [lifecycle.md](lifecycle.md).*
