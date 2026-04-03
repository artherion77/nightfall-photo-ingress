# Deprecated Concepts Registry

**Status:** active  
**Sources:** `design/superseeded/v1-lifecycle-baseline-superseded.md`, `design/superseeded/web-control-plane-initial-extension-superseded.md`  
**See also:** [tradeoffs.md](tradeoffs.md), [design/architecture-decision-log.md](../architecture-decision-log.md)

---

## Purpose

This document records design concepts and documents that have been superseded. It provides
a single-entry lookup for why a concept was retired, what replaced it, and where the
authoritative current design lives. It does not restate the full content of superseded
documents — those are retained in `design/superseeded/` for historical reference.

---

## Deprecation Registry

| Concept | Superseded document | Approximate date | Replacement | Reason |
|---|---|---|---|---|
| Accepted-first ingest lifecycle | `design/superseeded/v1-lifecycle-baseline-superseded.md` | 2026-04-02 | V2 pending-first lifecycle — `design/specs/ingest.md`, `design/specs/accept.md` | V1 auto-accepted all unknown files with no operator review step. Replaced by an explicit `pending → accepted` transition to make every acceptance decision intentional and auditable. See DEC-20260402-01. |
| V1 CLI command `photo-ingress` (no namespace prefix) | `design/superseeded/v1-lifecycle-baseline-superseded.md` §2 | 2026-04-03 | `nightfall-photo-ingress` | Renamed to carry the `nightfall-` prefix for consistency with all other nightfall tooling and to prevent namespace collisions in system package managers. See DEC-20260403-01. |
| V1 registry schema version 1 (`files.status` without `pending`) | `design/superseeded/v1-lifecycle-baseline-superseded.md` §5 | 2026-04-02 | Schema version 2 (`design/specs/registry.md`) | V1 schema defined `status CHECK (status IN ('accepted','rejected','purged'))` — no `pending` state existed. Schema version 2 adds `pending` and restructures `accepted_records`. No in-place migration path is supported. |
| Original web control plane scoping sketch | `design/superseeded/web-control-plane-initial-extension-superseded.md` | 2026-04-01 | `design/web/webui-architecture-phase1.md`, `design/web/web-control-plane-architecture-phase2.md` | The original sketch was a high-level intent document. Replaced by the Phase 1 SvelteKit architecture spec and Phase 2 architecture, which provide detailed component, API, and security specifications. |

---

## Deprecated Concept Summaries

### Accepted-first ingest lifecycle (V1)

The V1 design specified that all unknown files encountered during a delta poll were
immediately and automatically transitioned to `accepted` status. Files were placed
directly into the accepted queue (`accepted_path`) without an intermediate review step.
Rejection was operator-initiated via the trash directory or CLI (`photo-ingress reject`),
but the default ingest path produced an already-accepted file.

This was superseded by the V2 pending-first design (DEC-20260402-01). All unknown files
now transition to `pending` status. The `accepted` transition requires explicit operator
action via `nightfall-photo-ingress accept <sha256>`. The change makes every acceptance
decision auditable and intentional, and prevents accidental promotion of unwanted content
into the accepted queue.

The `accepted_records` table was also redesigned: V1 used `sha256 TEXT PRIMARY KEY` (one
record per hash); V2 uses an autoincrement `id` primary key to support multiple
acceptance event records per file.

**Current design:** `design/specs/ingest.md`, `design/specs/accept.md`  
**ADL reference:** DEC-20260402-01 in `design/architecture-decision-log.md`

---

### V1 CLI naming (`photo-ingress`)

The V1 specification named the CLI command `photo-ingress` without a namespace prefix.
This matched the service-level naming convention (`/etc/nightfall/photo-ingress.conf`,
ZFS datasets) but diverged from all other nightfall tooling, which uses `nightfall-`
prefixed binaries (e.g. `nightfall-zfs-snapshot-*`, `nightfall-health-report`).

The CLI was renamed to `nightfall-photo-ingress` (DEC-20260403-01). Service-level names —
config path, ZFS dataset names, and the status file — retained the shorter `photo-ingress`
form for operator ergonomics. The V1 CLI name is no longer valid for any invocation
example in documentation or operator tooling.

**Current naming:** `design/domain/glossary.md` §"Canonical Naming Conventions"  
**ADL reference:** DEC-20260403-01 in `design/architecture-decision-log.md`

---

### V1 registry schema (version 1)

The V1 baseline spec defined a `files` table with `status CHECK (status IN ('accepted',
'rejected', 'purged'))`. There was no `pending` status because V1 used an accepted-first
model — the first destination for an unknown file was the accepted queue directly.

Schema version 2, introduced alongside the pending-first lifecycle, makes three changes
that are incompatible with schema version 1:

1. `pending` is added as a valid `status` value.
2. `accepted_records` gains an autoincrement `id` primary key (V1 used `sha256` as sole
   PK, which only allowed one acceptance record per hash).
3. New tables were added: `file_origins`, `external_hash_cache`, `live_photo_pairs`,
   `ingest_terminal_audit`.

There is no migration path from V1 to V2. Deployments must bootstrap a fresh
`registry.db` using `domain/registry.py`'s `initialize()` at schema version 2.

**Current schema:** `design/specs/registry.md`  
**ADL reference:** DEC-20260402-01 in `design/architecture-decision-log.md`

---

### Original web control plane scoping sketch

The document `design/superseeded/web-control-plane-initial-extension-superseded.md` was
the first scoping sketch for adding an operator-facing web interface. It defined a
FastAPI + Svelte architecture, a set of API routes under `/api/v1`, a basic security
baseline (static token auth, CORS), and a progressive deployment topology. All content
was at intent level — no component or implementation detail was specified.

It was superseded by two replacement documents with greater specificity:

- `design/web/webui-architecture-phase1.md` — Phase 1 SvelteKit architecture, detailed
  component specification, and security baseline.
- `design/web/web-control-plane-architecture-phase2.md` — Phase 2 expansion with
  enhanced triage and thumbnail workflows.

The original sketch's invariants (registry remains the source of truth; mutating actions
are idempotent and audit-first; permanent library is out of bounds for web writes) are
carried forward unchanged in both replacement documents.

**Current design:** `design/web/webui-architecture-phase1.md`, `design/web/web-control-plane-architecture-phase2.md`

---

*For architecture evolution context, see [tradeoffs.md](tradeoffs.md) and [design/architecture-decision-log.md](../architecture-decision-log.md).*  
*For the V2 current design, see [design/domain-architecture-overview.md](../domain-architecture-overview.md) (navigation index).*
