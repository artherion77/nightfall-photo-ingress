# design/ — Architecture and Design Documentation

This directory is the authoritative home for all architecture, domain model, behavioral
specifications, and design rationale for `nightfall-photo-ingress`.

---

## Folder Map

| Folder | Contents |
|---|---|
| [architecture/](architecture/) | System-level architecture: data flow, state machines, lifecycle, observability, error model, storage topology, schema |
| [domain/](domain/) | Domain model, glossary, and constraints: the business concepts that the architecture implements |
| [specs/](specs/) | Behavioral specifications for each operator-visible operation: ingest, accept, reject, purge, registry schema |
| [rationale/](rationale/) | Design decisions, tradeoffs, and deprecated concepts |
| [web/](web/) | Web control plane and SvelteKit UI design: API surface, component architecture, design tokens |
| [superseeded/](superseeded/) | Superseded documents retained for historical reference |
| [logos/](logos/) | Project logo assets |
| [ui-mocks/](ui-mocks/) | UI mockup images (web control plane design reference) |

---

## Root-Level Documents

These files sit directly in `design/` and are full specifications that span or predate
the subfolder organisation. They are the authoritative detailed sources; the corresponding
`architecture/` overviews are extractions only.

| File | Category | Relationship to subfolders |
|---|---|---|
| [domain-architecture-overview.md](domain-architecture-overview.md) | Navigation index | Top-level index to all subfolder documents; retained as a reading guide |
| [architecture-decision-log.md](architecture-decision-log.md) | Decision record | Standalone ADL; cross-referenced by all topic documents |
| [auth-design.md](auth-design.md) | Full spec | Auth account model, MSAL integration, token cache security; no subfolder overview |
| [cli-config-specification.md](cli-config-specification.md) | Full spec | Complete INI config schema, required keys, defaults, and validation rules; no subfolder overview |
| [error-taxonomy-and-resilience.md](error-taxonomy-and-resilience.md) | Full spec | Complete exception hierarchy, `as_log_dict()` contract, GhostItemError; overview at [architecture/error-model.md](architecture/error-model.md) |
| [ingest-lifecycle-and-crash-recovery.md](ingest-lifecycle-and-crash-recovery.md) | Full spec | Complete IngestOperationJournal JSONL format, phase sequence, recovery actions, StagingDriftReport, zero-byte policy; overview at [architecture/lifecycle.md](architecture/lifecycle.md) |
| [observability.md](observability.md) | Full spec | Complete JSON log field schema, human vs. JSON mode, safe_logging design, status snapshot writer; overview at [architecture/observability.md](architecture/observability.md) |

---

## Document Status

| Status | Meaning |
|---|---|
| `active` | Authoritative; reflects current implementation |
| `active — overview` | Authoritative for the overview; a companion full-spec document exists |
| `navigation index` | Converted to index after content was extracted to topic documents |
| `stub` | Placeholder pending authoring |
| `superseded` | Replaced by a newer document; retained in `superseeded/` for history |

---

## Entry Points by Reader Role

**Developer onboarding (start here):**
1. [domain-architecture-overview.md](domain-architecture-overview.md) — system overview and document map
2. [domain/domain-model.md](domain/domain-model.md) — entities, module boundaries, ER diagram
3. [architecture/data-flow.md](architecture/data-flow.md) — pipeline overview
4. [architecture/state-machine.md](architecture/state-machine.md) — file lifecycle state machine

**Operator / support:**
1. [specs/ingest.md](specs/ingest.md) — poll cycle and cursor semantics
2. [specs/accept.md](specs/accept.md), [specs/reject.md](specs/reject.md), [specs/purge.md](specs/purge.md) — operator transitions
3. [architecture/invariants.md](architecture/invariants.md) — what the system guarantees

**Implementation / code review:**
1. [architecture/lifecycle.md](architecture/lifecycle.md) + [ingest-lifecycle-and-crash-recovery.md](ingest-lifecycle-and-crash-recovery.md) — crash recovery detail
2. [specs/registry.md](specs/registry.md) — full SQLite schema
3. [architecture/error-model.md](architecture/error-model.md) + [error-taxonomy-and-resilience.md](error-taxonomy-and-resilience.md) — error handling
4. [architecture-decision-log.md](architecture-decision-log.md) — why decisions were made

**Web control plane:**
1. [web/](web/) — Phase 1–3 architecture and component specs
