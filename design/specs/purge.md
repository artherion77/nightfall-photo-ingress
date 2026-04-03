# Purge Flow Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §6.5  
**See also:** [specs/reject.md](reject.md), [specs/accept.md](accept.md), [specs/registry.md](registry.md)

---

## Overview

The purge flow is a destructive, explicit operator transition that removes the physical file from `rejected/` and transitions the registry record to `purged`. The SHA-256 audit history is retained permanently in `audit_log`.

Purge is the terminal state for an unwanted file: once purged, the file cannot be recovered from the queue. Future poll runs will continue to block re-ingestion of the same SHA-256.

---

## CLI Command

```bash
nightfall-photo-ingress purge <sha256> [--reason "..."] --path /etc/nightfall/photo-ingress.conf
```

---

## Precondition

- Current registry status for the SHA-256 must be `rejected`.
- The purge command will fail closed if the resolved physical path is outside the configured `rejected_path` root (root-containment safety check).

---

## Execution Steps

1. Look up SHA-256 in `files`; verify `status = 'rejected'`.
2. Resolve the physical file path within `rejected_path`.
3. Apply root-containment safety check: reject any path that resolves outside `rejected_path`. Fail closed if the check does not pass.
4. Delete the physical file from `rejected/`.
5. Transition `files.status` from `rejected` → `purged` in a `BEGIN IMMEDIATE` transaction.
6. Append a `purged` row to `audit_log` with `actor = 'cli'`.
7. Write status snapshot to `/run/nightfall-status.d/photo-ingress.json`.

---

## Registry Side Effects

| Table | Effect |
|---|---|
| `files` | `status` updated to `purged`; `current_path` cleared; `updated_at` set |
| `audit_log` | Row appended: `action = 'purged'`, `actor = 'cli'` |

---

## Safety Requirements

- **Root-containment check**: the resolved file path must be a strict descendant of `rejected_path`. Any symlink traversal or path manipulation that would resolve outside this root causes the purge to fail with an error.
- **Requires prior rejection**: purge will not run on files in `pending` or `accepted` state. To remove a pending file, reject it first, then purge.
- **Audit retention**: unlike the physical file, the `audit_log` entry for the rejection and purge events is retained permanently and cannot be deleted (enforced by DB triggers).

---

## Post-Purge State

Once purged:
- The physical file is deleted from `rejected/`.
- The SHA-256 record in `files` shows `status = 'purged'`.
- All prior `audit_log` rows for that file (pending, rejected, purged) remain intact.
- Future polls that encounter the same SHA-256 will classify it as `rejected_duplicate` and skip it, because the registry still has a record for the SHA-256 (status `purged`) and the ingest engine blocks re-ingestion of any known-rejected-or-purged hash.

---

*For the reject flow that must precede purge, see [reject.md](reject.md).*  
*For the accept flow, see [accept.md](accept.md).*
