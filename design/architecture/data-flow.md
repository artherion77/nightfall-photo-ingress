# Data Flow: High-Level Pipeline Architecture

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §2  
**See also:** [storage-topology.md](storage-topology.md), [lifecycle.md](lifecycle.md), [specs/ingest.md](../specs/ingest.md)

---

## Pipeline Overview

```
iOS Camera Roll
      │
      │  (automatic background upload)
      ▼
  OneDrive (personal Microsoft account)
      │
      │  Microsoft Graph API — delta poll on operational cadence (8-24h in production)
      ▼
┌─────────────────────────────────────────┐
│           nightfall server              │
│                                         │
│  /mnt/ssd/photo-ingress/staging/        │  ← SSD; temp download area
│       │                                 │
│       │  SHA-256 hash                   │
│       │  registry lookup                │
│       ▼                                 │
│  registry.db (SQLite, SSD)              │  ← authoritative content ledger
│       │                                 │
│       ├─ rejected → delete from staging │
│       ├─ pending  → delete from staging │
│       ├─ accepted → delete from staging │
│       ├─ purged   → delete from staging │
│       └─ unknown  → move to pending/    │
│                    + insert registry    │
│                                         │
│  /nightfall/media/photo-ingress/        │  ← HDD pool
│    pending/    ← ingest destination      │
│    accepted/   ← explicit accept target  │
│    rejected/   ← retained rejected files │
│    trash/      ← rejection trigger       │
└─────────────────────────────────────────┘
      │
     │  manual operator move/copy
      ▼
  /nightfall/media/pictures/... (permanent library)
     │
     │  read-only bind-mount
     ▼
  Immich (LXC container) external library
```

---

## Stage Descriptions

| Stage | Component | Description |
|---|---|---|
| **Upload** | iOS → OneDrive | iOS background upload over cellular/WiFi; service has no control or visibility here |
| **Delta Poll** | GraphClient | Enumerates changes since last cursor via Microsoft Graph delta API; metadata pre-filter skips known files |
| **Staging Download** | GraphClient / storage | Streaming download to SSD staging as `{onedrive_id}.tmp`; renamed on completion |
| **Hash + Ingest Decision** | IngestDecisionEngine | SHA-256 computed; registry looked up; decision applied (pending/discard/duplicate) |
| **Queue Boundary** | storage | Unknown files moved to `pending/YYYY/MM/`; known files discarded from staging |
| **Operator Transitions** | CLI / trash path unit | Explicit `accept`, `reject`, `purge`; trash directory used for filesystem-triggered rejection |
| **Permanent Library** | Manual / operator | Accepted files manually moved to `/nightfall/media/pictures/` for Immich indexing |

---

## Key Pipeline Properties

- **Immich-independence**: Immich has no write path to the ingest queue. A fresh Immich DB rescans the permanent library without affecting ingress state.
- **HDD isolation**: Staging, hashing, and registry all operate on SSD. HDD is only written when a new file first moves to `pending/`, or on explicit accept/reject/purge transitions.
- **Delta cursor discipline**: Cursor is advanced only after all page-level side effects are durable. Interrupted runs resume safely from last committed cursor.
- **Registry as system of record**: SHA-256 identity is the authoritative content key. File paths are advisory only (`current_path`).

---

*For physical storage layout, see [storage-topology.md](storage-topology.md).*  
*For step-by-step poll cycle mechanics, see [lifecycle.md](lifecycle.md).*  
*For the ingest decision engine specification, see [specs/ingest.md](../specs/ingest.md).*
