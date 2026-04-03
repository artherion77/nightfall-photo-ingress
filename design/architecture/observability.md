# Observability Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §16  
**See also:** [architecture/error-model.md](error-model.md), [architecture/lifecycle.md](lifecycle.md)

---

## Structured Logging

Every log record emitted by the service is structured. In JSON mode (`--log-mode json`), each line is a JSON object with at minimum:

```json
{
  "ts": "2026-04-03T12:00:00.000000+00:00",
  "level": "INFO",
  "component": "onedrive.client",
  "msg": "...",
  "run_id": "...",
  "account": "christopher"
}
```

Context fields appended where relevant: `sha256`, `filename`, `status`, `onedrive_id`, `action`, `actor`, `reason`.

In human mode (`--log-mode human`, default for interactive use), records are plain text but carry the same fields. Both modes feed into journald via stdout.

---

## Run-ID

A UUID is generated once per poll invocation and propagated to:
- All log records emitted during that run
- `ingest_terminal_audit` rows (`batch_run_id` column)
- Status snapshot `details`

This enables cross-surface correlation: a single `run_id` links journal log lines, audit rows, and the status snapshot produced by one poll cycle.

---

## Diagnostic Counters

The following counters are accumulated per poll run inside `GraphClient` and emitted via structured logs and the status snapshot `details` block on run completion:

| Counter key | Meaning |
|-------------|---------|
| `retry_attempt_total` | Total retry attempts made |
| `retry_transport_error_total` | Transport-layer errors that triggered retries |
| `throttle_response_total` | HTTP 429 / Retry-After responses received |
| `resync_required_total` | Delta resync (410 Gone) events |
| `auth_refresh_attempt_total` | MSAL silent refresh attempts |
| `auth_refresh_success_total` | Successful token refreshes |
| `auth_refresh_failure_total` | Failed token refreshes |
| `graph_response_request_id_seen_total` | Graph responses carrying `request-id` headers |
| `graph_response_correlation_id_seen_total` | Graph responses carrying `client-request-id` headers |

---

## Safe Logging

`sanitize_extra()` (`adapters/onedrive/safe_logging.py`) is applied to all `extra=` dicts before they reach the logging handler. It strips any key whose name matches known credential patterns (e.g. `token`, `access_token`, `sig`, `tempauth`). The function never raises; on internal error it returns a sanitized sentinel instead.

---

## Status Snapshot

Written atomically to `/run/nightfall-status.d/photo-ingress.json` (tmp file then `os.replace()`) after each CLI command that modifies system state.

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | `1` — increment on breaking changes |
| `service` | string | always `"photo-ingress"` |
| `version` | string | package `__version__` |
| `host` | string | `socket.gethostname()` |
| `state` | string | see state values below |
| `success` | bool | whether the command succeeded |
| `command` | string | CLI subcommand that wrote this snapshot |
| `updated_at` | string | ISO-8601 UTC |
| `details` | object | command-specific data (counters, error info, etc.) |

### State Values

| State | Meaning |
|-------|---------|
| `healthy` | Last command completed successfully |
| `degraded` | Non-fatal error; service continues on next scheduled run |
| `auth_failed` | Authentication failed; token refresh required before next poll |
| `disk_full` | SSD staging dataset above threshold; manual intervention required |
| `ingest_error` | Ingest engine failed; check journal and audit log |
| `registry_corrupt` | SQLite registry integrity check failed; manual recovery required |

---

*For error categories and retry policy, see [error-model.md](error-model.md).*  
*For per-operation journal and crash recovery, see [lifecycle.md](lifecycle.md).*  
*For operator status file interpretation, see [docs/operator/operational-playbook.md](../../docs/operator/operational-playbook.md).*
