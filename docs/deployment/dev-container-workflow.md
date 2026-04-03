# Development Container Workflow

**Status:** active (initial scaffold)  
**Container target:** `dev-photo-ingress`  
**See also:** [environment-setup.md](environment-setup.md), [../operator/maintenance.md](../operator/maintenance.md), [../../design/architecture/environment-separation-and-container-lifecycle.md](../../design/architecture/environment-separation-and-container-lifecycle.md)

---

## Overview

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

An initial dedicated dev lifecycle scaffold exists at `dev/devctl`.

Current high-level commands:

- `devctl create` — create `dev-photo-ingress` container baseline
- `devctl bootstrap-python` — install Python runtime and project dependencies
- `devctl bootstrap-webui` — install Node/npm and web UI dependencies
- `devctl run-api` — run API process for development
- `devctl run-webui` — run Vite dev server with host-accessible URL
- `devctl reset` — reset disposable dev state
- `devctl destroy` — remove development container

Some commands are scaffolds/placeholders and are explicitly labeled as such by
the tool output.

---

## Expected Development Lifecycle

1. create `dev-photo-ingress`
2. bootstrap runtime/toolchains
3. run API + web UI dev servers
4. iterate against source changes
5. reset or destroy when done

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

`dev/devctl` is intentionally minimal and provides a starting command surface.
Future iterations will harden reset behavior, API run orchestration, and shared
helper coverage with staging controller parity.
