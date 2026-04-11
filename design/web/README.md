# design/web/ — Web Control Plane Documentation

This directory contains consolidated architecture, API, decisions, and detailed design documents for the web control plane.

## Directory Structure

- `architecture.md`
	- Consolidated architecture (Phase 1, Phase 1.5, and stable planning architecture content)
- `api.md`
	- Consolidated API specification and versioning policy
- `design-decisions.md`
	- Consolidated decisions, invariants, and rationale
- `detailed-design/`
	- `staging-footer.md`
	- `photowheel.md`
	- `design-tokens.md`

## Planning Documents

Roadmaps and execution plans are managed under:

- `planning/planned/`
- `planning/implemented/`

## Migration Notes

- Legacy source documents merged into consolidated files were moved to `planning/implemented/web-design-source/` for auditability.
- Active Phase 2 planning artifacts were moved to `planning/planned/`.
- Implemented Phase 1 and Phase 1.5 roadmap artifacts were moved to `planning/implemented/`.


---
## Editing Policy (Phase 2 Baseline)

1. The authoritative documents for the Web Control Plane are:
	- architecture.md
	- api.md
	- design-decisions.md
	- detailed-design/*.md
	- design-tokens.md

2. Files under `planning/implemented/` are archival and MUST NOT be edited.

3. Files under `planning/planned/` are active planning documents and MAY be edited.

4. All new design work MUST be added under:
	- design/web/ (architecture, API, decisions, detailed design)
	- planning/planned/ (roadmaps, implementation plans)

5. When a roadmap or plan is completed, it MUST be moved to:
	planning/implemented/

6. Cross-file references MUST use relative paths and MUST NOT point to archived
	pre-consolidation files.

---
