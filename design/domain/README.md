# design/domain/ — Domain Model and Concepts

This folder contains the domain foundation documents: the entities, terms, constraints,
and structural model that the rest of the architecture implements. These are
source-agnostic — they apply regardless of which provider adapter is active.

---

## Documents

| File | Status | What it covers |
|---|---|---|
| [glossary.md](glossary.md) | active | Alphabetical term definitions (25 terms) with owning module and notes; canonical naming conventions matrix (service, CLI, systemd units, ZFS datasets) |
| [constraints.md](constraints.md) | active | 10 design constraints (fully automated, reject-once-reject-forever, idempotent, auditable…) and 7 derived system invariants with enforcement mechanisms |
| [domain-model.md](domain-model.md) | active | Bounded context statement; 12-entity primary domain entities table; module-layer map diagram; Mermaid ER diagram for all registry tables |

---

## Relationship to Other Documents

- **[domain-model.md](domain-model.md)** supersedes the module architecture sections in
  `ARCHITECTURE.md`.
- **[glossary.md](glossary.md)** extends the naming matrix from `design/domain-architecture-overview.md §1.1`
  with full definitions.
- **[constraints.md](constraints.md)** is the source for the invariant statements catalogued
  in detail in [design/architecture/invariants.md](../architecture/invariants.md).

---

*Parent: [design/README.md](../README.md)*
