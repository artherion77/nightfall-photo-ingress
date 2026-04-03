# Observability

Status: active
Created: 2026-04-03
Updated: 2026-04-03

---

## 1. Purpose

This document describes the observability model for `nightfall-photo-ingress`: how
structured logs are formatted and routed, how a poll run is identified and correlated
across log lines and audit records, what diagnostic counters are exported, and how the
health status snapshot is written for external consumers.

---

## 2. Logging Modes

The CLI accepts `--log-mode {json|human}` (default: `human`).

| Mode | When to use | Format |
|------|-------------|--------|
| `human` | Interactive terminal, development | Plain-text lines; trace events collapsed to single animated progress line |
| `json` | systemd service, log aggregation | One compact JSON object per line (JSONL) |

The systemd unit should invoke `nightfall-photo-ingress poll --log-mode json` so that
all output is structured and can be forwarded to a log aggregator or queried with
`journalctl -o json`.

---

## 3. JSON Log Format

In JSON mode, each log record is a single-line JSON object written to stderr. Field
order is sorted alphabetically (via `json.dumps(sort_keys=True)`).

### 3.1 Guaranteed Base Fields

| Field | Type | Description |
|-------|------|-------------|
| `ts` | string | UTC ISO-8601 timestamp with microsecond precision |
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | string | Python logger name (e.g. `nightfall_photo_ingress.adapters.onedrive.client`) |
| `message` | string | Formatted log message |

### 3.2 Context Fields (added as extras)

The following fields are attached to records where they are relevant:

| Field | Meaning |
|-------|---------|
| `run_id` | UUID for the current poll run (see §4) |
| `account` | Account name from config |
| `sha256` | SHA-256 hex digest of the file being processed |
| `filename` | Original filename from OneDrive |
| `status` | Registry status (`pending`, `accepted`, etc.) |
| `action` | Ingest action taken (`pending`, `discard_*`, `quarantine_zero_byte`, etc.) |
| `error_code` | Machine-readable error code from an `OneDriveAdapterError` |
| `operation` | Operation that failed |
| `status_code` | HTTP status code if applicable |
| `event` | Trace event name (only on `msg="onedrive_trace"` records) |

Not all records carry all fields; extras are only attached where meaningful.

### 3.3 Trace Records

High-frequency polling events (graph responses, delta progress, download progress,
checkpoints) are emitted with `msg="onedrive_trace"`. In JSON mode these appear as
full records; in human mode they are collapsed into a single animated progress line
on the terminal and suppressed from the log output, keeping operator output readable.

---

## 4. Run-ID

A UUID is generated once per `poll_accounts()` invocation:

```python
poll_run_id = str(uuid4())
```

This ID is:
- Attached to every structured log record emitted during that poll run (as `run_id`).
- Written to `ingest_terminal_audit` rows (`batch_run_id` column) via the ingest engine.
- Included in the status snapshot `details` block on run completion.

This enables cross-surface correlation: a single `run_id` value links all log lines,
audit rows, and the status snapshot produced by one poll cycle.

---

## 5. Diagnostic Counters

The following counters are accumulated across the lifetime of one `poll_account_once()`
call and returned in `AccountPollResult.diagnostics.counters`. Only counters listed in
`_EXPORTED_DIAGNOSTIC_KEYS` (in `adapters/onedrive/client.py`) are included in the
exported result.

| Counter key | Meaning |
|-------------|---------|
| `retry_attempt_total` | Total HTTP retry attempts made during the poll |
| `retry_transport_error_total` | Transport-layer errors (connection refused, timeout) that triggered retries |
| `throttle_response_total` | HTTP 429 or 503 responses received (rate limiting) |
| `resync_required_total` | Delta `410 Gone` events requiring cursor reset |
| `auth_refresh_attempt_total` | MSAL token refresh attempts initiated |
| `auth_refresh_success_total` | Successful token refreshes |
| `auth_refresh_failure_total` | Failed token refreshes |
| `graph_response_request_id_seen_total` | Graph responses carrying `request-id` headers (for Microsoft support correlation) |
| `graph_response_correlation_id_seen_total` | Graph responses carrying `client-request-id` headers |

These counters are included in the status snapshot `details.diagnostics` block and in
the `account_poll_end` trace event.

---

## 6. Safe Logging

### 6.1 sanitize_extra()

`sanitize_extra()` (`adapters/onedrive/safe_logging.py`) must be called on all
`extra=` dicts before they reach the logging system. It:

1. Applies `redact_token()` to string values on token-like keys (keys matching
   `token|secret|authorization|auth|password|sig|tempauth|client_secret`).
2. Applies `redact_url()` to string values that look like URLs (`https?://`).
3. Recursively processes nested dicts, lists, and tuples.
4. Converts `Path` values to `str`.
5. Never raises; on internal error returns a safe fallback dict.

### 6.2 Transport Library Redaction

The `_RedactingFormatter` wraps the standard formatter for `httpx` and `httpcore`
loggers. It applies a regex URL substitution (`_URL_RE`) on the formatted string,
replacing any `https?://...` fragments with their `redact_url()` result. This catches
any URL that leaks through the transport library's own log calls.

---

## 7. Status Snapshot

After each CLI command that modifies state, `write_status_snapshot()` (in `status.py`)
writes a JSON file for consumption by the nightfall health subsystem.

### 7.1 Write Protocol

1. Assemble the payload dict.
2. Ensure the parent directory exists (`mkdir -p`).
3. Write to a `.tmp` sibling: `status_path.with_suffix(".json.tmp")`.
4. Atomically replace: `tmp_path.replace(status_path)`.

The atomic rename ensures readers never see a partially-written file.

### 7.2 File Location

Default: `/run/nightfall-status.d/photo-ingress.json`

This path is under the `tmpfs`-backed `/run/` hierarchy and is re-created on each boot.
The parent directory is created by the service unit's `RuntimeDirectory=` directive.

### 7.3 Schema

```json
{
  "schema_version": 1,
  "service": "photo-ingress",
  "version": "<package version>",
  "host": "<socket.gethostname()>",
  "state": "<state value>",
  "success": true,
  "command": "<cli subcommand>",
  "updated_at": "<UTC ISO-8601>",
  "details": {}
}
```

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | Increment on breaking schema changes |
| `service` | string | Always `"photo-ingress"` |
| `version` | string | `nightfall_photo_ingress.__version__` |
| `host` | string | Hostname at write time |
| `state` | string | See §7.4 |
| `success` | bool | Whether the command completed without error |
| `command` | string | CLI subcommand that wrote this snapshot (`poll`, `accept`, `reject`, etc.) |
| `updated_at` | string | UTC ISO-8601 timestamp |
| `details` | object | Command-specific data: diagnostic counters, account results, error info |

### 7.4 State Values

| State | Operator meaning |
|-------|-----------------|
| `healthy` | Last command completed successfully; no action required |
| `degraded` | Non-fatal error; service will retry on next scheduled run |
| `auth_failed` | Authentication failed; token cache must be refreshed before next poll (`nightfall-photo-ingress auth-setup`) |
| `disk_full` | Staging or pending dataset above free-space threshold; manual intervention required |
| `ingest_error` | Ingest engine failed; check journal and audit log for details |
| `registry_corrupt` | SQLite integrity check failed; manual recovery required before any further writes |

---

## 8. Human-Mode Interactive Output

When `--log-mode human` is used on an interactive terminal (`stderr.isatty()`), the
`_InteractiveTraceHandler` intercepts trace events and renders them as a single
animated progress line using ANSI `\r` overwrites. This collapses per-page and
per-download chatter into one compact status line during polling.

Non-trace log records (INFO and above) are printed as plain text lines after flushing
the progress line.

In non-interactive contexts (e.g. pipes, redirects), human mode falls back to a plain
`StreamHandler` with a `_RedactingFormatter`, and trace records are included in output
rather than being suppressed.

---

## 9. Transport Debug Logging

When `--debug-httpx-transport` is passed, `httpx` and `httpcore` transport-level
logging is enabled and written to a dedicated file (`debug-transport.log` by default,
configurable via `--httpx-transport-log-path`). All URLs in this output are passed
through `_RedactingFormatter` before writing.

This flag is intended only for development and support diagnostics; it must never be
set in production systemd units.
