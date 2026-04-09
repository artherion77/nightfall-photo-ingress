# design/web/ — Web Control Plane & UI Design

This directory contains all design documents for the `photo-ingress` web control plane
and its associated SvelteKit user interface. These documents cover the API-layer design,
frontend component architecture, design tokens, and phased feature roadmaps for the web
layer of the system.

## Documents

| File | Phase | Purpose |
|------|-------|---------|
| [web-control-plane-api-phase1.md](web-control-plane-api-phase1.md) | Phase 1 | REST API specification with endpoint reference, authentication, pagination semantics, and response schemas |
| [webui-architecture-phase1.md](webui-architecture-phase1.md) | Phase 1 | SvelteKit application structure, API client layer, stores, routing, layout system, and adapter configuration |
| [webui-component-mapping-phase1.md](webui-component-mapping-phase1.md) | Phase 1 | Component decomposition derived from UI mockup analysis; interaction logic, visual transforms, and scroll behaviour |
| [webui-design-tokens-phase1.md](webui-design-tokens-phase1.md) | Phase 1 | Dark-mode design token catalogue; CSS custom property naming scheme; token categories and usage rules |
| [web-control-plane-architecture-phase2.md](web-control-plane-architecture-phase2.md) | Phase 2 | Reverse-proxy integration, SSR migration path, API versioning policy, session management, and feature additions |
| [web-control-plane-architecture-phase3.md](web-control-plane-architecture-phase3.md) | Phase 3 | Advanced features: multi-account support, photo-wheel infinite scroll upgrade, KPI config API |
| [photowheel-visual-design-decisions.md](photowheel-visual-design-decisions.md) | — | Authoritative design decisions for PhotoWheel viewport, card geometry, overlap, and thumbnail loading |

## Delivery Roadmaps

Execution roadmaps are under `design/web/roadmaps/`; design-rationale documents
remain in `design/web/`.

| File | Purpose |
|---|---|
| [roadmaps/web-control-plane-phase1-implementation-roadmap.md](roadmaps/web-control-plane-phase1-implementation-roadmap.md) | Phase 1 chunk sequence, status, and acceptance gates |
| [roadmaps/web-control-plane-integration-plan.md](roadmaps/web-control-plane-integration-plan.md) | End-to-end phased integration plan |
| [roadmaps/web-control-plane-phase1-scope.md](roadmaps/web-control-plane-phase1-scope.md) | Phase 1 scope decisions and critique dispositions |
| [web-control-plane-techstack-decision.md](web-control-plane-techstack-decision.md) | Stack rationale and dependency decisions |
| [web-control-plane-project-structure.md](web-control-plane-project-structure.md) | Intended and rationale-backed project structure |

## Document Taxonomy

The web-control-plane documentation is intentionally split into three classes:

1. **Architecture and design specs (this folder):**
	- Source-of-truth design behavior and target architecture.
2. **Delivery roadmaps and implementation sequencing (`design/web/roadmaps/`):**
	- Chunk sequencing, execution checkpoints, and implementation status tracking.
3. **Superseded records (`design/superseeded/`):**
	- Historical context retained for auditability.

## Scope

This category covers **web control plane and UI design only**. It is separate from the
core CLI/pipeline design documents in `design/` (ingest, registry, accept/reject workflows)
and from the runtime architecture documents in `design/architecture/`.

## Related Core Design Documents

| Topic | Document |
|---|---|
| Domain model and bounded context | [design/domain/domain-model.md](../domain/domain-model.md) |
| Registry schema (shared by API and CLI) | [design/specs/registry.md](../specs/registry.md) |
| Accept / reject / purge flows (API mirrors these) | [design/specs/accept.md](../specs/accept.md), [design/specs/reject.md](../specs/reject.md), [design/specs/purge.md](../specs/purge.md) |
| System invariants the web layer must preserve | [design/architecture/invariants.md](../architecture/invariants.md) |
| UI mockup images | [design/ui-mocks/](../ui-mocks/) |

For the CLI-layer domain architecture, see [`design/domain-architecture-overview.md`](../domain-architecture-overview.md).

---

*Parent: [design/README.md](../README.md)*
