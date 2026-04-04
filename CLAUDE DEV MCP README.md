# CLAUDE DEV MCP README

## Purpose

This repository uses an MCP model plus a local MCP server so LLM workflows execute deterministic, auditable actions through mapped tasks.

Policy: prefer to use MCP endpoints first, over ad-hoc shell commands.

Policy: Host-installations only with explicit user approval. Dev-container installations are allowed and every installation is reported in the task summary.

Policy: After each significant task, if execution shows that extending MCP itself or connected tools would significantly improve efficiency, record an extension proposal in MCP and evaluate it for implementation.

## Design Decision

Implemented strategy:
- LXC snapshot reuse + bind-mount caches (standard).

Why this choice:
- Faster repeated bootstrap/reset cycles for Python, npm, and Playwright artifacts.
- Deterministic clean-state recovery via one canonical snapshot.
- Lower operational complexity than custom image pipelines.

Future option (documentation-only):
- Base image layering can be evaluated later, but is intentionally not implemented in this repository workflow.

## Files

- Model: .mcp/model.json
- Server: mcp_server.py
- Runtime logs: .mcp/logs/<taskId>.log
- Task history: .mcp/tasks/history.json

## LXC Cache Mounts

The dev container setup configures these bind-mount caches:
- npm home: ~/.npm -> /root/.npm
- npm cache: ~/.cache/npm -> /root/.cache/npm
- pip cache: ~/.cache/pip -> /root/.cache/pip
- Playwright cache: ~/.cache/ms-playwright -> /root/.cache/ms-playwright

## devctl Commands (Cached Install Flow)

- ./dev/devctl setup
- ./dev/devctl bootstrap-python
- ./dev/devctl bootstrap-webui
- ./dev/devctl bootstrap-playwright
- ./dev/devctl snapshot-create
- ./dev/devctl reset
- ./dev/devctl assert-cached-ready
- ./dev/devctl status

Typical flow:

```bash
./dev/devctl setup
./dev/devctl bootstrap-python
./dev/devctl bootstrap-webui
./dev/devctl bootstrap-playwright
./dev/devctl snapshot-create
./dev/devctl reset
./dev/devctl status
```

## MCP Tasks (devctl-first)

Canonical MCP tasks now use devctl orchestration for environment prepare/reset.

- devcontainer.prepare
- devcontainer.reset
- backend.test.unit
- backend.test.integration
- web.test.unit

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

- Container missing:
  - Run ./dev/devctl setup
- Cache mounts missing:
  - Run ./dev/devctl setup and then ./dev/devctl status
- Snapshot missing:
  - Run ./dev/devctl snapshot-create
- Reset fails:
  - Ensure clean snapshot exists and run ./dev/devctl assert-cached-ready
- Test task unavailable:
  - Verify task key exists in .mcp/model.json under mappings
