# Superseded: Dev Container Workflow

This document is retained only as a redirect stub.

The authoritative developer workflow documentation is now:

- `docs/development-handbook.md` for host setup, development container lifecycle,
  governor-first commands, test suites, and dev-to-staging promotion flow.
- `docs/operations-runbook.md` for packaged runtime and operator deployment
  context when a development task crosses into staging or production behavior.

Do not add new substantive workflow content here.
# Development Container Workflow

**Status:** active (initial scaffold)  
**Container target:** `dev-photo-ingress`  
**See also:** [../development-handbook.md](../development-handbook.md), [environment-setup.md](environment-setup.md), [../operator/maintenance.md](../operator/maintenance.md), [../../design/architecture/environment-separation-and-container-lifecycle.md](../../design/architecture/environment-separation-and-container-lifecycle.md)

---

## Overview

For the consolidated developer workflow, command surface policy, and promotion
flow from dev to staging to production, start with
[docs/development-handbook.md](../development-handbook.md).

This document defines the planned workflow for a dedicated development container.
It is intentionally separate from staging so developer tooling does not alter
staging validation guarantees.

The development container is named `dev-photo-ingress` to match the existing
container naming pattern (`staging-photo-ingress`, `photo-ingress`).

---

## Scope and Intent

Development container goals:

- run web UI and API in rapid iteration mode
- avoid host-level Node/npm requirements
- support disposable and frequently reset workflows

This workflow is not a replacement for staging smoke/live validation and does not
change production packaging requirements.

---

## Command Surface

Current high-level development lifecycle commands:

- `devctl setup` — atomic bootstrap of container, Node, Python, and both web stacks
- `devctl check` — read-only drift report (Node, manifests, snapshots)
- `devctl update [--scope node|webui|dashboard|all] [--simulate]` — regenerate lockfiles and run regression gate
- `devctl reset [--base]` — restore `current` snapshot when present, otherwise `base`
- `devctl destroy` — remove development container

Runtime/testing helpers remain available (`ensure-stack-ready`, `run-webui`,
`test-web-*`, `status`, `shell`) and are used by automated workflows.

---

## Expected Development Lifecycle

1. run `devctl setup` to establish baseline (`base` snapshot)
2. run `devctl check` to verify no drift
3. iterate on source or dependency changes
4. run `devctl update --simulate` to preview required work
5. run `devctl update [--scope ...]` to regenerate lockfiles and run regression
6. use `devctl reset` for fast rollback to `current` (or `base` if current is absent)
7. destroy when done (optional)

### Reset mechanic

`devctl setup` creates a `base` snapshot. `devctl update` creates/replaces the
`current` snapshot only after regression succeeds.

`devctl reset` restores `current` first and falls back to `base`.
`devctl reset --base` explicitly restores `base`.

Typical loop:

```bash
./dev/bin/devctl setup
./dev/bin/devctl check

# preview drift response
./dev/bin/devctl update --simulate

# apply updates and refresh current snapshot
./dev/bin/devctl update --scope webui

# iterate ...
./dev/bin/devctl reset
```

---

## Promotion Boundary

Artifact promotion remains unchanged:

1. build wheel
2. install wheel in staging
3. run staging smoke and live validation
4. promote same wheel to production

The dev container accelerates iteration but is not a release gate.

---

## Implementation Notes

To avoid duplicated shell logic between staging and dev controllers, shared helper
functions should be factored into a common library and consumed by both tools.

Proposed helper categories:

- container launch/wait
- snapshot operations
- proxy setup
- logging and error wrappers

---

## Current State

`dev/bin/devctl` now follows the dual-snapshot update model:

- `base` snapshot from `setup`
- `current` snapshot from successful `update`
- explicit drift visibility via `check`

This keeps development iteration fast while preserving deterministic rollback.
