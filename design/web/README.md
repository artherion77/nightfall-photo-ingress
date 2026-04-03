# design/web/ — Web Control Plane & UI Design

This directory contains all design documents for the `photo-ingress` web control plane
and its associated SvelteKit user interface. These documents cover the API-layer design,
frontend component architecture, design tokens, and phased feature roadmaps for the web
layer of the system.

## Documents

| File | Phase | Purpose |
|------|-------|---------|
| [webui-architecture-phase1.md](webui-architecture-phase1.md) | Phase 1 | SvelteKit application structure, API client layer, stores, routing, layout system, and adapter configuration |
| [webui-component-mapping-phase1.md](webui-component-mapping-phase1.md) | Phase 1 | Component decomposition derived from UI mockup analysis; interaction logic, visual transforms, and scroll behaviour |
| [webui-design-tokens-phase1.md](webui-design-tokens-phase1.md) | Phase 1 | Dark-mode design token catalogue; CSS custom property naming scheme; token categories and usage rules |
| [web-control-plane-architecture-phase2.md](web-control-plane-architecture-phase2.md) | Phase 2 | Reverse-proxy integration, SSR migration path, API versioning policy, session management, and feature additions |
| [web-control-plane-architecture-phase3.md](web-control-plane-architecture-phase3.md) | Phase 3 | Advanced features: multi-account support, photo-wheel infinite scroll upgrade, KPI config API |

## Scope

This category covers **web control plane and UI design only**. It is separate from the
core CLI/pipeline design documents in `design/` (ingest, registry, accept/reject workflows)
and from the runtime architecture documents in `design/architecture/`.

For the CLI-layer domain architecture, see [`design/domain-architecture-overview.md`](../domain-architecture-overview.md).  
For the backend API specification, see the backend source and `docs/` operator documents.
