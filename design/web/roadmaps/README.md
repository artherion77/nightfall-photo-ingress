# design/web/roadmaps — Delivery and sequencing index

Status: Active index
Date: 2026-04-06
Owner: Systems Engineering

This folder contains the canonical web-control-plane delivery and sequencing roadmaps.
Design-rationale documents are located one level up in `design/web/`.

## Indexed planning artifacts

| Document | Role | Current use |
|---|---|---|
| [web-control-plane-phase1-implementation-roadmap.md](web-control-plane-phase1-implementation-roadmap.md) | Phase 1 chunk delivery tracker | Primary chunk-status and execution-order tracker |
| [web-control-plane-phase1.5-implementation-roadmap.md](web-control-plane-phase1.5-implementation-roadmap.md) | Phase 1.5 chunk delivery tracker | Thumbnail, interaction model, DOM windowing chunks |
| [web-control-plane-phase2-implementation-roadmap.md](web-control-plane-phase2-implementation-roadmap.md) | Phase 2 chunk delivery tracker | LAN exposure prerequisites and mandatory features |
| [web-control-plane-integration-plan.md](web-control-plane-integration-plan.md) | End-to-end integration sequencing | Baseline implementation plus post-Phase-4 replan |
| [web-control-plane-phase1-scope.md](web-control-plane-phase1-scope.md) | Scope decision log | Records accepted/deferred scope decisions |
| [../web-control-plane-techstack-decision.md](../web-control-plane-techstack-decision.md) | Stack and dependency decisions | Rationale for FastAPI/Uvicorn/SvelteKit/RapiDoc choices |
| [../web-control-plane-project-structure.md](../web-control-plane-project-structure.md) | Intended structure map | Proposed/target structure reference |

## How to use this index

1. Start with architecture intent in `design/web/` docs.
2. Use this index to jump to the matching roadmap artifact in this folder.
3. Update both design and planning docs when implementation reality changes.

## Drift handling rule

When implementation and plan diverge:
- update the phase/chunk status in the roadmap first;
- update affected design docs second;
- keep this index lightweight (links only, no duplicated design content).
