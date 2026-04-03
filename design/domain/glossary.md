# Glossary and Naming Matrix

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §1.1  
**See also:** [domain/constraints.md](constraints.md), [domain-architecture-overview.md](../domain-architecture-overview.md)

---

## Canonical V2 Naming Matrix

| Scope | Canonical Name | Notes |
|---|---|---|
| Project and service | `photo-ingress` | Primary name in docs, CLI, and operational language |
| Source adapter | `onedrive` | Current adapter; kept explicit in config and module names |
| Python package | `nightfall_photo_ingress` | Keeps namespace alignment with existing nightfall Python projects |
| CLI command | `nightfall-photo-ingress` | Main operational command (binary installed under `/opt/nightfall-photo-ingress/bin/`) |
| Config file | `/etc/nightfall/photo-ingress.conf` | Single versioned INI file |
| systemd units | `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`, `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service` | systemd-managed runtime inside the `photo-ingress` LXC container |
| SSD ZFS dataset (container) | `ssdpool/photo-ingress` | Always-on staging, cursors, token caches, registry |
| SSD mountpoint | `/mnt/ssd/photo-ingress` | Working set for low-latency operations |
| HDD ZFS dataset (container) | `nightfall/media/photo-ingress` | Queue/trash boundary on nightfall pool |
| HDD mountpoint | `/nightfall/media/photo-ingress` | `pending/`, `accepted/`, `rejected/`, and `trash/` live here |
| Permanent library root | `/nightfall/media/pictures` | Read-only to ingress, indexed by Immich |
| Health status file | `/run/nightfall-status.d/photo-ingress.json` | Exported each poll cycle |

---

## Key Domain Terms

| Term | Meaning |
|---|---|
| **pending** | File downloaded from OneDrive with unknown SHA-256; placed in operator review queue |
| **accepted** | File explicitly approved by operator; awaiting move to permanent library |
| **rejected** | File explicitly rejected by operator; retained on disk until purge |
| **purged** | Previously rejected file whose physical copy has been deleted |
| **delta cursor** | Graph API delta link checkpoint; enables incremental change enumeration |
| **registry** | SQLite system-of-record tracking all file SHA-256 identities and state transitions |
| **audit_log** | Append-only SQLite table recording every state transition |
| **staging** | Temporary SSD directory where files are downloaded before hash and registry lookup |
| **trash directory** | Filesystem path watched by the path unit; operator drops files here to trigger rejection |
| **Live Photo** | Apple Live Photo: paired HEIC/JPEG + MOV components tracked together in the registry |
| **sync import** | CLI mode that imports advisory SHA1 hashes from the permanent library |
| **Run-ID** | UUID generated per poll invocation; propagated through logs and audit rows for correlation |
| **StagingDriftReport** | Dataclass classifying staging directory contents after a crash or interrupted poll |

---

*For the complete domain constraints, see [constraints.md](constraints.md).*  
*For the pipeline architecture, see [data-flow.md](../architecture/data-flow.md).*
