# MCP for AGENTS

## Purpose

This repository uses an MCP model plus a local MCP server so LLM workflows execute deterministic, auditable actions through mapped tasks.

Policy: prefer to use MCP endpoints first, over ad-hoc shell commands.

Policy: Host-installations only with explicit user approval. Dev-container installations are allowed and every installation is reported in the task summary.

Policy: After each significant task, if execution shows that extending MCP itself or connected tools would significantly improve efficiency, record an extension proposal in MCP and evaluate it for implementation.

## Design Decision

Implemented strategy:
- LXC snapshot reuse + bind-mount caches (standard).

Why this choice:
- Faster repeated bootstrap/reset cycles for Python and npm artifacts.
- Deterministic clean-state recovery via one canonical snapshot.
- Lower operational complexity than custom image pipelines.

Future option (documentation-only):
- Base image layering can be evaluated later, but is intentionally not implemented in this repository workflow.

## Files

## Rename Addendum

This file supersedes the former repository guidance file:
- `COPILOT  DEV MCP README.md` (renamed to `AGENTS.md` on 2026-04-06)

- Model: .mcp/model.json
- Server: mcp_server.py
- Runtime logs: .mcp/logs/<taskId>.log
- Task history: .mcp/tasks/history.json

## LXC Cache Mounts

The dev container setup configures these bind-mount caches:
- npm home: ~/.npm -> /root/.npm
- npm cache: ~/.cache/npm -> /root/.cache/npm
- pip cache: ~/.cache/pip -> /root/.cache/pip

## devctl Commands (Underlying Tooling)

`devctl` remains the underlying environment-management tool, but it is no longer the canonical automation entry point for MCP or agent workflows. The governor surface is `govctl run ... --json`; direct `devctl` use is reserved for local tool development, container maintenance, or troubleshooting a specific delegated command.

These are the real, exposed `devctl` commands (see `dev/bin/devctl` case statement):

- ./dev/bin/devctl setup
- ./dev/bin/devctl destroy
- ./dev/bin/devctl reset [--base]
- ./dev/bin/devctl update [--scope node|webui|dashboard|all] [--simulate]
- ./dev/bin/devctl check
- ./dev/bin/devctl ensure-stack-ready [webui|dashboard|all]
- ./dev/bin/devctl assert-cached-ready
- ./dev/bin/devctl run-api
- ./dev/bin/devctl status
- ./dev/bin/devctl shell
- ./dev/bin/devctl run-webui
- ./dev/bin/devctl test-web-typecheck
- ./dev/bin/devctl test-metrics-dashboard-typecheck
- ./dev/bin/devctl test-web-unit
- ./dev/bin/devctl test-web-e2e

Typical flow:

```bash
./dev/bin/devctl setup
./dev/bin/devctl reset
./dev/bin/devctl status
```

## govctl Commands (Build Governor)

govctl is the build governor CLI. It reads a declarative target manifest, resolves dependencies via topological sort, runs preflight checks, and executes build/test targets in correct order.

- Manifest: dev/govctl-targets.yaml
- CLI: dev/bin/govctl

Commands:

```bash
./dev/bin/govctl list                          # list all targets and groups
./dev/bin/govctl check [TARGET...]             # run preflight checks
./dev/bin/govctl graph [TARGET...]             # show dependency graph (DOT)
./dev/bin/govctl run TARGET [TARGET...]        # execute targets in dependency order
./dev/bin/govctl run --dry-run TARGET          # show execution plan without running
./dev/bin/govctl run --json TARGET             # machine-readable JSONL output (for MCP)
```

JSON mode (`--json`) writes JSONL events to stdout and stores artifacts under `artifacts/govctl/`.

## MCP Tasks (govctl-only execution surface)

Canonical MCP tasks now route through `govctl run ... --json`, including dev-container lifecycle wrappers. `devctl`, `stagingctl`, `metricsctl`, and direct Python entry points remain implementation details behind `govctl` targets, not MCP-facing command surfaces.

- devcontainer.prepare
- devcontainer.check
- devcontainer.update
- devcontainer.reset
- backend.test.unit
- backend.test.integration
- web.test.unit
- web.test.integration
- web.test.e2e
- staging.create
- staging.ensure-running
- staging.install
- staging.smoke
- staging.smoke-live
- staging.e2e.module1
- metrics.status
- metrics.run-now
- metrics.publish
- metrics.install
- metrics.stop

One-command-surface policy:
- For MCP execution and agent automation, use `govctl run TARGET --json` only.
- Do not add direct `devctl`, `stagingctl`, `metricsctl`, or raw Python commands to `.mcp/model.json` mappings.
- Direct tool invocations are allowed only when implementing or debugging the underlying tools themselves, or when no `govctl` target exists yet.

## Playwright E2E Tests

Policy: Playwright browser E2E test suites run against the staging container
(staging-photo-ingress), NOT the dev container (dev-photo-ingress).

The dev container has no requirement for Playwright browser binaries. Do not
add `npx playwright install` or any browser-install step to the devctl
bootstrap flow.

Canonical E2E execution targets:
- govctl (staging bootstrap): `./dev/bin/govctl run staging.ensure-running --json`
- govctl: `./dev/bin/govctl run staging.e2e.module1 --json`
- MCP: `staging.e2e.module1` task (requires staging-photo-ingress running)

The `devctl test-web-e2e` command remains available only as a contract-test
harness hook (via DEVCTL_CONTRACT_TEST_ROOT override). It is not a workflow
entry point for browser E2E.

Important safety rule:
- MCP must not run arbitrary install commands directly.
- Install actions are executed via devctl bootstrap commands only.

## Continuous MCP Extension Policy

The MCP server supports extension-capture as part of significant task execution.

Execution-time fields on `/mcp/exec`:
- `significantTask` (boolean)
- `extensionRecommendation` (string, optional)

When `significantTask=true` and `extensionRecommendation` is present, MCP records a proposal in:
- `.mcp/tasks/extensions.json`

Endpoints:
- `GET /mcp/extensions` — list extension proposals backlog
- `POST /mcp/extensions/propose` — manually add a proposal

## Start MCP Server

```bash
python mcp_server.py --host 127.0.0.1 --port 8765 --workspace . --model .mcp/model.json
```

Remote endpoint format:
- http://<remote-ssh-host>:8765

## MCP Usage Examples

Prepare container + caches + snapshot:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"devcontainer.prepare"}'
```

Reset to clean snapshot:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"devcontainer.reset"}'
```

Run backend unit tests:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"backend.test.unit"}'
```

Run web unit tests:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"web.test.unit"}'
```

Run backend unit tests through govctl JSON mode (agent-friendly stream):

```bash
./dev/bin/govctl run backend.test.unit --json
```

Run web unit tests through govctl JSON mode:

```bash
./dev/bin/govctl run web.test.unit --json
```

Run devcontainer prepare through the canonical governor surface:

```bash
./dev/bin/govctl run devcontainer.prepare --json
```

Inspect status/log/context:

```bash
curl -sS http://<server>/mcp/status/<id>
curl -sS http://<server>/mcp/log/<id>
curl -sS http://<server>/mcp/context
curl -sS http://<server>/mcp/extensions
```

Submit a significant-task execution with extension recommendation:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{
    "task":"backend.test.integration",
    "significantTask": true,
    "extensionRecommendation": "Add dedicated devctl command for fast triage smoke seeding"
  }'
```

Submit a manual extension proposal:

```bash
curl -sS -X POST http://<server>/mcp/extensions/propose \
  -H 'Content-Type: application/json' \
  -d '{
    "task":"web.test.unit",
    "recommendation":"Add MCP mapping for Node>=20 bootstrap in dev container"
  }'
```

## Security and Policy

- Host installations require explicit user approval.
- Dev-container installations are allowed for development convenience.
- Any installation performed by MCP orchestration is reported in task results.
- MCP server accepts only mapped tasks from .mcp/model.json; no arbitrary command execution.

## Troubleshooting

Agents are encouraged to augment this list with troubleshooting items discovered when working with the repository and correct any documentation drift vs. new repo state. 

- Container missing:
  - Run ./dev/bin/devctl setup
- Cache mounts missing:
  - Run ./dev/bin/devctl setup and then ./dev/bin/devctl status
- Snapshot missing:
  - Run ./dev/bin/devctl setup
- Reset fails:
  - Ensure clean snapshot exists and run ./dev/bin/devctl assert-cached-ready
- Test task unavailable:
  - Verify task key exists in .mcp/model.json under mappings
- Governor task unavailable:
  - Run ./dev/bin/govctl list and verify the target exists in dev/govctl-targets.yaml

## mAOF – Modular Agent Orchestration Framework

The repository uses a modular Agent Orchestration Framework (mAOF) to structure
deterministic, auditable, multi‑agent workflows. mAOF defines a clear state
machine, explicit label‑based transitions, and role separation between Analyst,
Implementation Agent, optional Validator, and the human (or automated)
Supervisor.

mAOF is compatible with MCP, govctl JSON mode, and GitHub Actions. It supports
human‑in‑the‑loop supervision and can be fully automated later.

---

### Goals

- Deterministic, audit‑ready agent workflows  
- Clear separation of responsibilities  
- Zero‑drift, zero‑overreach execution  
- Human supervision possible at every stage  
- Optional second validation ring via GitHub Actions  
- Full compatibility with MCP task surfaces (`govctl run … --json`)  

---

## mAOF State Machine

The mAOF state machine defines the lifecycle of an issue as it moves through
agent‑driven analysis, implementation, and optional validation.

```mermaid
stateDiagram-v2
    [*] --> open

    open --> analysis: supervisor / human sets\nagent:analysis
    analysis --> analysis_done: analyst sets\nagent:analysis-done

    analysis_done --> implement: supervisor / human sets\nagent:implement
    analysis_done --> queued: supervisor / human sets\nagent:queued

    queued --> implement: supervisor / human frees capacity\nagent:implement

    implement --> closed: implementation agent\nRCA + Fix + Validation + Close\nsets agent:done

    closed --> validation: optional supervisor / human\nsets agent:validate

    validation --> done_validated: GH Actions E2E success\nsets agent:done_validated
    validation --> validation_failed: GH Actions E2E fail\nsets agent:validation-failed

    validation_failed --> validation_agent: validator agent\ninvestigate / fix / reopen

    done_validated --> [*]
    closed --> [*]
