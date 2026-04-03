# design/superseeded/ — Superseded Documents

This folder retains design documents that have been superseded by newer designs.
They are kept for historical reference only and must not be treated as authoritative
for the current system.

---

## Documents

| File | Superseded by | Reason |
|---|---|---|
| [v1-lifecycle-baseline-superseded.md](v1-lifecycle-baseline-superseded.md) | `design/specs/ingest.md`, `design/specs/accept.md`, `design/architecture/state-machine.md` | V1 used an accepted-first lifecycle (unknown files auto-accepted). V2 introduced a `pending` state and requires explicit operator `accept`. Schema version 1 had no `pending` status value. |
| [web-control-plane-initial-extension-superseded.md](web-control-plane-initial-extension-superseded.md) | `design/web/webui-architecture-phase1.md`, `design/web/web-control-plane-architecture-phase2.md` | The original web control plane scoping sketch was a high-level intent document. Replaced by Phase 1 and Phase 2 architecture specs with detailed component, API, and security specifications. |

---

## Synthesised Deprecation Record

A single synthesised reference that describes all deprecated concepts, why they were
retired, and what replaced them is at:

- **[design/rationale/deprecated-concepts.md](../rationale/deprecated-concepts.md)**

Do not read the files in this folder for current design guidance. Use the deprecated-concepts
document as the entry point and follow its cross-references to current authoritative documents.

---

*Parent: [design/README.md](../README.md)*
