# CLAUDE DEV MCP README

## Purpose

This repository now includes a project-specific MCP model and a minimal orchestration
server so that LLMs (including Claude-like and Copilot-like MCP clients) can operate
through a deterministic, auditable interface instead of issuing ad-hoc shell commands.

Policy: prefer to use MCP endpoints first, over ad-hoc shell commands.

## Why this design

- Model location choice: `.mcp/model.json`
  - `.mcp/` is tooling-neutral and can be shared by multiple clients.
  - Keeps model, logs, and task history colocated under one repo-local control folder.
  - Avoids coupling to one vendor namespace (`.claude` or `.copilot`).
- Server stack choice: Python standard library HTTP server (`mcp_server.py`)
  - No additional runtime dependency required for remote SSH bootstrap.
  - Works with existing Python-centric repo workflow.
  - Easy to run in constrained environments and easy to inspect.

## Files

- Model: `.mcp/model.json`
- Server: `mcp_server.py`
- Runtime logs: `.mcp/logs/<taskId>.log`
- Task history: `.mcp/tasks/history.json`

## Start server in remote SSH workspace

Run from repository root:

```bash
python mcp_server.py --host 0.0.0.0 --port 8765 --workspace . --model .mcp/model.json
```

Recommended remote endpoint format:

- `http://<remote-ssh-host>:8765`

Requirements for remote access:

- SSH access to the host where this workspace is located.
- Network path to selected host/port (or SSH tunnel forwarding).
- Execute permission for `dev/devctl` and `staging/stagingctl` when using mapped tasks.

## Endpoint usage examples

Run a mapped task:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"web.test.unit"}'
```

Check task status:

```bash
curl -sS http://<server>/mcp/status/<id>
```

Read task log:

```bash
curl -sS http://<server>/mcp/log/<id>
```

Run verification:

```bash
curl -sS -X POST http://<server>/mcp/verify \
  -H 'Content-Type: application/json' \
  -d '{"verify":"unit","target":"backend"}'
```

Read canonical runtime context first:

```bash
curl -sS http://<server>/mcp/context
```

## Model extension guidance

Edit `.mcp/model.json` and keep these rules:

- Add new deterministic command lists under `mappings`.
- Add domain-level documentation under `domains`.
- Add verification recipes under `verifications`.
- Never place secrets in the model; only placeholders and env var names.
- Keep task keys stable (for example: `backend.test.unit`, `web.deploy.staging`).

## Security model

- The server rejects arbitrary command requests.
- Only tasks explicitly defined in `.mcp/model.json` can be executed.
- `cwd` is constrained to stay inside this workspace.

## Troubleshooting

- Devcontainer not running:
  - Use `./dev/devctl status`, then `./dev/devctl create` as needed.
- `devctl` missing or not executable:
  - Ensure `dev/devctl` exists and has execute bit (`chmod +x dev/devctl`).
- `stagectl` command mismatch:
  - This repo uses `staging/stagingctl`; compatibility aliases are documented in the model.
- Remote SSH access issues:
  - Verify host firewall/port forwarding or use SSH local forwarding.
- Endpoint returns unknown task:
  - Confirm key exists in `.mcp/model.json` under `mappings`.