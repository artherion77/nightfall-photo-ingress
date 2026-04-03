# design/rationale/ — Design Rationale

This folder contains the Architecture Decision Log and documents explaining why
architectural choices were made and what was superseded.

---

## Documents

| File | Status | What it covers |
|---|---|---|
| [architecture-decision-log.md](architecture-decision-log.md) | active | Append-only decision records (DEC-YYYYMMDD-XX format); each entry records decision, rationale, alternatives, consequences, and implementation notes |
| [tradeoffs.md](tradeoffs.md) | active | Tech stack choices (language, HTTP client, auth library, database, schema types, process model); SQLite vs. network database; WAL mode; stdlib-first; delegated auth; no Immich write path; WAL mode rationale; adapter extensibility pattern; systemd timer vs. daemon architecture |
| [deprecated-concepts.md](deprecated-concepts.md) | active | Deprecation registry (4 entries): accepted-first V1 lifecycle, V1 CLI naming (`photo-ingress`), V1 registry schema (version 1), original web control plane scoping sketch; one-paragraph summary per deprecated concept |

---

## Relationship Between These Documents

`architecture-decision-log.md` records individual decisions as append-only entries in
a structured template format. `tradeoffs.md` and `deprecated-concepts.md` provide
synthesised, thematic rationale derived from those decisions — easier to read when you
need to understand *why* a group of choices were made together.

Each entry in `tradeoffs.md` references the relevant ADL decision record where one exists.
Each entry in `deprecated-concepts.md` includes an **ADL reference** pointing to the
decision that superseded the concept.

---

*Parent: [design/README.md](../README.md)*
