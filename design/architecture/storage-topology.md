# Storage Topology

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §4  
**See also:** [data-flow.md](data-flow.md), [specs/registry.md](../specs/registry.md)

---

## ZFS Dataset and Mount Layout

```
ssdpool/photo-ingress  →  /mnt/ssd/photo-ingress/
  staging/               — files downloaded from OneDrive, pending hash + decision
  registry.db            — SQLite hash registry (the system of record)
  token_cache.json       — MSAL OAuth2 token cache (chmod 600)
   delta_cursor           — per-account delta traversal checkpoint (plain text)

nightfall/media/photo-ingress  →  /nightfall/media/photo-ingress/
   pending/               — unknown-hash ingest destination (operator review queue)
   accepted/              — explicit accept destination
   rejected/              — retained rejected artifacts (until purge)
   trash/                 — operator drops files here to trigger rejection flow

nightfall/media/pictures  →  /nightfall/media/pictures/
   ...                    — permanent library, read-only to ingress (used by Immich and sync-import)
```

---

## Dataset Creation (Manual Prerequisite)

```bash
zfs create -o mountpoint=/mnt/ssd/photo-ingress ssdpool/photo-ingress
zfs create -o mountpoint=/nightfall/media/photo-ingress nightfall/media/photo-ingress
```

---

## Pool Assignment Rationale

| Location | Pool | Reason |
|---|---|---|
| `staging/` | SSD (`ssdpool`) | Low-latency I/O during downloads and hashing; avoids spinning up HDD for short-lived temp files |
| `registry.db` | SSD (`ssdpool`) | All registry reads/writes during poll are latency-sensitive; concurrent writes use WAL mode |
| `token_cache.json` | SSD (`ssdpool`) | Auth token must be read on every poll run; must persist across reboots |
| `delta_cursor` | SSD (`ssdpool`) | Cursor checkpoint is read/written every poll page; must be fast and durable |
| `pending/`, `accepted/`, `rejected/`, `trash/` | HDD (`nightfall`) | Queue content is bulk media; written only on ingest decisions and explicit operator transitions |
| `pictures/` (permanent library) | HDD (`nightfall`) | Long-term archival; read-only to ingress |

---

## Queue Directory Semantics

| Directory | Managed by | Operator access |
|---|---|---|
| `staging/` | Pipeline (write), pipeline (cleanup) | Read-only inspection only |
| `pending/` | Pipeline (write on ingest), CLI `accept`/`reject` (consume) | Read and enumerate for review |
| `accepted/` | CLI `accept` (write), operator (move to permanent library) | Move files to permanent library |
| `rejected/` | Trash unit / CLI `reject` (write), CLI `purge` (delete) | Inspect, then purge when confirmed unwanted |
| `trash/` | Operator (write), trash path unit (consume) | Drop files here to trigger rejection |

---

## Path Template

Files entering the queue follow a configurable storage template. The default:

```
storage_template = {yyyy}/{mm}/{original}
accepted_storage_template = {yyyy}/{mm}/{original}
```

Collision-safe suffixing (`_1`, `_2`, …) is applied if a target path already exists.

---

*For the data pipeline context of these directories, see [data-flow.md](data-flow.md).*  
*For the registry schema that tracks files across these directories, see [specs/registry.md](../specs/registry.md).*
