# Operational Playbook

**Status:** active  
**Source:** extracted from `docs/operations-runbook.md` §Operator Workflows, §Status File Interpretation  
**See also:** [cli-guide.md](cli-guide.md), [troubleshooting.md](troubleshooting.md), [design/architecture/observability.md](../../design/architecture/observability.md)

---

## Overview

This playbook covers the routine operator commands used to manage the photo-ingress service: config validation, queue transitions (accept, reject, purge, trash), sync import, and status file interpretation.

---

## Config Check

Validates the configuration file format, required keys, account sections, and path accessibility. Run this any time the config is modified.

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

A passing run exits 0 and prints a summary of all validated accounts. A failing run exits non-zero and prints actionable messages identifying which key or section is invalid.

---

## Accepting a File

Accept a file by its SHA-256 hash. This moves it from the pending queue to the accepted queue in the registry and writes an `accepted_records` row.

```bash
nightfall-photo-ingress accept <sha256> --path /etc/nightfall/photo-ingress.conf
```

Use when inspecting the pending queue and explicitly approving an item for permanent library inclusion. Accepted files are not moved to permanent storage by this command — a separate operator step moves the accepted queue to `/nightfall/media/photo-ingress/accepted/`.

---

## Rejecting a File

Reject a file by its SHA-256 hash. This marks the file as rejected in the registry with an audit record. Rejected files are blocked from re-download if OneDrive serves them again.

```bash
nightfall-photo-ingress reject <sha256> --reason "<description>" --path /etc/nightfall/photo-ingress.conf
```

The `--reason` flag is optional but strongly recommended for audit clarity. The actor recorded in the audit row will be `operator-cli`.

---

## Purging a File

Purge a file by its SHA-256 hash. This transitions the registry record to `purged` state and removes the physical staging copy if present.

```bash
nightfall-photo-ingress purge <sha256> --path /etc/nightfall/photo-ingress.conf
```

Purge is intended for records that are confirmed unwanted and should be completely removed from tracking. The audit history is retained.

---

## Processing the Trash Queue

Drain files placed in the trash directory by the operator. This command reads all items in `trash_path`, creates rejected registry records for each, removes the physical files, and emits audit rows.

```bash
nightfall-photo-ingress process-trash --path /etc/nightfall/photo-ingress.conf
```

This command is also triggered automatically by the `nightfall-photo-ingress-trash.path` systemd unit whenever files are dropped into the trash directory.

**Trash workflow:**
1. Operator drops a file into the configured `trash_path` directory.
2. `nightfall-photo-ingress-trash.path` detects the change.
3. `nightfall-photo-ingress-trash.service` runs `process-trash` automatically.
4. Audit log records the rejection with actor `trash-processor`.

To process manually (e.g. when debugging the path unit):
```bash
systemctl start nightfall-photo-ingress-trash.service
```

---

## Sync-Import from Permanent Library

Populate the registry with SHA-1 hashes from existing `.hashes.sha1` files in the permanent library. This prevents re-downloading files that are already in the library.

```bash
nightfall-photo-ingress sync-import --path /etc/nightfall/photo-ingress.conf
```

Run this once after initial deployment against an existing library. Also run it after bulk additions to the permanent library to keep the advisory hash index current. The command is read-only with respect to the library — it never modifies `.hashes.sha1` files.

Use `--dry-run` to preview the import without writing to the registry:

```bash
nightfall-photo-ingress sync-import --dry-run --path /etc/nightfall/photo-ingress.conf
```

---

## Status File Interpretation

The status file at `/run/nightfall-status.d/photo-ingress.json` is written atomically after each command run.

```bash
jq . /run/nightfall-status.d/photo-ingress.json
jq .state /run/nightfall-status.d/photo-ingress.json
jq '{state, updated_at, command}' /run/nightfall-status.d/photo-ingress.json
```

| State | Meaning | Operator action |
|-------|---------|----------------|
| `healthy` | Last command completed successfully with no anomalies | None required |
| `degraded` | Command completed but encountered recoverable issues (e.g. partial poll due to runtime limit) | Check `details` field for specifics; monitor next poll result |
| `auth_failed` | MSAL token refresh failed; account cannot be polled | Run `nightfall-photo-ingress auth-setup --account <name>` to re-authenticate; check token cache permissions |
| `disk_full` | Staging or accepted path is below the configured minimum free space threshold | Free space on the relevant volume; poll will resume automatically |
| `ingest_error` | Ingest decision engine encountered an unexpected error processing one or more candidates | Inspect journald logs for the failed run ID; check staging directory for stale `.tmp` files |
| `registry_corrupt` | Registry integrity check failed (e.g. WAL recovery failure) | Stop the service immediately; run SQLite integrity check (`PRAGMA integrity_check`); restore from last ZFS snapshot |

If the status file is absent after a run, confirm that `/run/nightfall-status.d/` exists and is writable by the service user, then check journald output.

---

*For CLI reference and setup commands, see [cli-guide.md](cli-guide.md).*  
*For failure handling and recovery, see [troubleshooting.md](troubleshooting.md).*  
*For accept/reject/purge specification detail, see the spec docs in [design/specs/](../../design/specs/).*
