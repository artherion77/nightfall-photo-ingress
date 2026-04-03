# Accept Flow Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §6.5  
**See also:** [specs/reject.md](reject.md), [specs/purge.md](purge.md), [specs/registry.md](registry.md)

---

## Overview

The accept flow is the explicit operator transition that moves a file from the `pending` queue to the `accepted` queue. There is no automatic transition from `pending` to `accepted`; operator intent is required.

---

## CLI Command

```bash
nightfall-photo-ingress accept <sha256> [--reason "..."] --path /etc/nightfall/photo-ingress.conf
```

---

## Precondition

- Current registry status for the SHA-256 must be `pending`.
- The physical file must be present at the path recorded in `files.current_path` or derivable from the pending queue root.

---

## Execution Steps

1. Look up SHA-256 in `files`; verify `status = 'pending'`.
2. Resolve the physical file path within `pending_path`.
3. Move file from `pending/` to `accepted/` using `accepted_storage_template` (`{yyyy}/{mm}/{original}`).
4. Collision-safe suffixing applied if the target path already exists.
5. Transition `files.status` from `pending` → `accepted` in an `BEGIN IMMEDIATE` transaction.
6. Write a row to `accepted_records` (preserves acceptance history independent of future file moves).
7. Append an `accepted` row to `audit_log` with `actor = 'cli'`.
8. Write status snapshot to `/run/nightfall-status.d/photo-ingress.json`.

---

## Registry Side Effects

| Table | Effect |
|---|---|
| `files` | `status` updated to `accepted`; `current_path` updated to new path; `updated_at` set |
| `accepted_records` | New row inserted recording SHA-256, account, source_path, accepted_at |
| `audit_log` | Row appended: `action = 'accepted'`, `actor = 'cli'` |

---

## Move-Safety

`accepted_records` preserves the acceptance truth independent of the current file location. If the operator manually moves an accepted file to the permanent library:
- The `files.current_path` becomes stale (advisory only).
- The acceptance event remains durable in `accepted_records`.
- Future polls will skip re-downloading this file because `files.status = 'accepted'`.

---

## Post-Accept Operator Step

The accept command does **not** move files to the permanent library. A separate operator step is required:

```bash
# Manual move to permanent library
mv /nightfall/media/photo-ingress/accepted/YYYY/MM/<file> /nightfall/media/pictures/<dest>/
```

Immich will pick up the new file on its next library scan as an external library addition.

---

*For the reject flow, see [reject.md](reject.md).*  
*For the purge flow (removes physically rejected files), see [purge.md](purge.md).*
