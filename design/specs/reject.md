# Reject Flow Specification

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §6.4  
**See also:** [specs/accept.md](accept.md), [specs/purge.md](purge.md), [specs/registry.md](registry.md)

---

## Overview

The reject flow marks a file's SHA-256 identity as `rejected` in the registry. Rejected files are retained on disk in `rejected/` until an explicit `purge` command. Once rejected, the SHA-256 is permanently blocked from future ingest — re-uploading to OneDrive will not re-ingest the file.

---

## Trigger 1: Trash Directory (Filesystem-Triggered)

1. Operator places (or moves) a file into `/nightfall/media/photo-ingress/trash/`.
2. systemd `.path` unit fires `nightfall-photo-ingress-trash.service`.
3. Service computes SHA-256 of each file in `trash/`.
4. If a known queue artifact exists, it is moved to `rejected/`.
5. If unknown, the trash artifact itself is moved to `rejected/` and registered as `rejected`.
6. Registry `status = 'rejected'`; appends `audit_log` row with `actor = 'trash_watch'`.

---

## Trigger 2: CLI Reject

```bash
nightfall-photo-ingress reject <sha256> [--reason "..."] --path /etc/nightfall/photo-ingress.conf
```

- Idempotent: if already `rejected`, logs and exits cleanly.
- Moves current queue file to `rejected/` if present.
- Updates registry and appends audit log.
- `actor = 'cli'` in the audit row; `--reason` text recorded if provided.

---

## Registry Side Effects

| Table | Effect |
|---|---|
| `files` | `status` updated to `rejected`; `current_path` updated to `rejected/` path; `updated_at` set |
| `audit_log` | Row appended: `action = 'rejected'`, `actor = 'cli'` or `'trash_watch'` |

---

## Idempotency

`reject` on an already-rejected SHA-256 is safe: the command logs the outcome and exits cleanly without error. The `audit_log` records only the first rejection event; subsequent idempotent calls do not append additional rows.

---

## Reject-Once, Reject-Forever

The reject state is permanent and cross-account:
- A future poll that encounters the same SHA-256 from OneDrive will classify it as `rejected_duplicate` and discard it from staging without writing to the queue.
- This applies regardless of which OneDrive account re-uploads the file.

---

*To remove a physically rejected file from disk, see [purge.md](purge.md).*  
*For the accept flow, see [accept.md](accept.md).*
