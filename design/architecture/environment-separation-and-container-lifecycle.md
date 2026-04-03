# Environment Separation and Container Lifecycle

Status: proposed
Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Purpose

Define a clean separation between development, staging, and production container
lifecycles for `nightfall-photo-ingress`, with explicit boundaries for tooling,
validation scope, and artifact promotion.

This proposal introduces a dedicated development container named
`dev-photo-ingress` and keeps staging focused on production-rehearsal validation.

---

## 2. Goals

- Preserve staging as a policy-constrained release validation environment.
- Avoid host-level Node/npm requirements for web UI development.
- Keep development iteration fast without contaminating staging contracts.
- Reuse shared lifecycle primitives to avoid duplicated orchestration logic.

## 3. Non-Goals

- Replacing the production installer flow.
- Changing runtime service names, config schema, or core ingest semantics.
- Introducing distributed orchestration or cloud services.

---

## 4. Environment Roles

| Environment | Container Name | Primary Role | Source of Truth Artifact |
|---|---|---|---|
| Development | `dev-photo-ingress` | fast local iteration and debugging | workspace sources + editable install (optional) |
| Staging | `staging-photo-ingress` | release rehearsal, smoke/live validation, evidence | built wheel (`dist/*.whl`) |
| Production | `photo-ingress` (default install target) | stable unattended operation | same wheel promoted from staging |

---

## 5. Capability Matrix

| Capability | Development | Staging | Production |
|---|---|---|---|
| Node/npm toolchain | yes | no (default) | no |
| Vite dev server | yes | no (default) | no |
| Editable Python install | optional | no | no |
| Wheel-based install | optional | yes | yes |
| Hot reload source mounts | yes | no | no |
| Operator smoke/live evidence workflow | optional | yes | limited operational checks only |
| Canonical systemd unit validation | optional | yes | yes |
| Runtime hardening and least-change policy | no | yes | yes |

---

## 6. Control Plane Ownership

### 6.1 Tooling split

- Keep `staging/stagingctl` focused on staging lifecycle only.
- Introduce a dedicated dev lifecycle tool (proposed path: `dev/devctl`) for
  `dev-photo-ingress`.

### 6.2 Avoiding code duplication

To avoid duplicate orchestration logic:

- Factor common container operations into a shared shell library
  (`lib/container-common.sh`), such as:
  - launch/wait helpers
  - file push/pull wrappers
  - proxy setup helpers
  - snapshot helpers
  - consistent logging/error helpers
- Keep command surfaces separate (`stagingctl` vs `devctl`) while sharing helper
  internals.

---

## 7. Lifecycle Contracts

### 7.1 Development (`dev-photo-ingress`)

Expected lifecycle:

1. create/reset container
2. install dev toolchain (Python + Node/npm)
3. run API in dev mode
4. run Vite dev server
5. iterate with source sync or bind mounts

Expected properties:

- disposable state by default
- fast bootstrap and reset
- no evidence retention requirement

### 7.2 Staging (`staging-photo-ingress`)

Expected lifecycle:

1. create baseline container from approved profile constraints
2. install wheel artifact and canonical units
3. auth setup + path discovery
4. smoke and smoke-live with evidence capture
5. reset to clean snapshot as needed

Expected properties:

- deterministic, policy-compliant runtime
- no dev-only toolchain requirement
- validates deployable artifacts, not editable source trees

### 7.3 Production (`photo-ingress`)

Expected lifecycle:

1. install promoted artifact into target container
2. enable timer/path units
3. operate unattended with runbook-based maintenance

Expected properties:

- minimal runtime dependencies
- no development tools
- predictable upgrade/rollback behavior

---

## 8. Promotion Model

1. Develop and test in `dev-photo-ingress`.
2. Build wheel artifact in CI or local controlled build.
3. Install same wheel into `staging-photo-ingress` and run smoke/live checks.
4. Promote unchanged artifact to production install target.

This guarantees staging and production validate the same package artifact.

---

## 9. Migration Notes

Current branch history may include staging-hosted web UI dev commands.
Target-state architecture moves web UI development to `dev-photo-ingress` and keeps
staging constrained to release validation.

During migration:

- documentation should treat staging-hosted web UI dev as transitional only
- new runbook guidance should prioritize dev container workflows

---

## 10. Implementation Plan (Documented, Not Yet Executed)

### Phase A: Documentation alignment

1. publish this architecture proposal
2. add deployment doc for planned dev container workflow
3. update indexes and runbook maps

### Phase B: Tooling scaffold

1. create `dev/devctl` command surface for `dev-photo-ingress`
2. extract shared helpers into `lib/container-common.sh`
3. update `stagingctl` to consume shared helpers without behavior drift

### Phase C: Workflow migration

1. remove staging-specific web UI dev guidance from operator runbooks
2. update web UI architecture docs to reference dev container workflow
3. validate staging smoke contracts remain unchanged

### Phase D: Enforcement

1. policy tests assert staging remains wheel-first and free of dev-only assumptions
2. docs and command help consistently reflect environment boundaries

---

## 11. References

- `staging/README.md`
- `docs/operator/maintenance.md`
- `docs/deployment/environment-setup.md`
- `design/web/webui-architecture-phase1.md`
- `design/rationale/architecture-decision-log.md`
