# design/rationale/ — Design Rationale

This folder contains documents explaining why architectural choices were made and
what was superseded. These complement the ADL (`design/architecture-decision-log.md`)
with synthesised, thematic rationale.

---

## Documents

| File | Status | What it covers |
|---|---|---|
| [tradeoffs.md](tradeoffs.md) | active | Tech stack choices (language, HTTP client, auth library, database, schema types, process model); SQLite vs. network database; WAL mode; stdlib-first; delegated auth; no Immich write path; WAL mode rationale; adapter extensibility pattern; systemd timer vs. daemon architecture |
| [deprecated-concepts.md](deprecated-concepts.md) | active | Deprecation registry (4 entries): accepted-first V1 lifecycle, V1 CLI naming (`photo-ingress`), V1 registry schema (version 1), original web control plane scoping sketch; one-paragraph summary per deprecated concept |

---

## Relationship to Architecture Decision Log

The Architecture Decision Log (`design/architecture-decision-log.md`) records
individual decisions as append-only entries in template format. The documents in
this folder provide synthesised, thematic rationale that is easier to read when you
need to understand *why* a group of choices were made together.

Each tradeoff entry in [tradeoffs.md](tradeoffs.md) references the relevant ADL entry
where one exists.

---

*Parent: [design/README.md](../README.md)*
