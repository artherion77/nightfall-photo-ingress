# Migration Roadmap

**Status:** stub — not yet authored  
**Owner:** Systems Engineering  
**Created:** 2026-04-03

---

## Scope

When authored, this document will record the planned migration roadmap for
photo-ingress, covering:

- Upgrade path from staging deployments to production.
- Sequencing of planned feature additions (additional provider adapters, web control
  plane phases) against deployment lifecycle stages.
- Transition strategy for any future schema version changes beyond v2.
- Rollback procedures and version boundary contracts.

This is a **planning artefact**. Schema migration technical specifications are owned
by `design/architecture/schema-and-migrations.md` (see
`planning/planned/critical-architecture-completion-plan.md`).

---

## Current State

No migration roadmap is presently defined. The project is at schema version 2 with
a clean v2 bootstrap requirement (no in-place upgrade from v1 schemas). The current
deployment path is covered in `docs/deployment/environment-setup.md`.

---

*For schema and migration technical specifications, see [design/architecture/schema-and-migrations.md](../design/architecture/schema-and-migrations.md).*  
*For deployment environment setup, see [docs/deployment/environment-setup.md](../docs/deployment/environment-setup.md).*
