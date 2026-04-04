# CLAUDE DEV MCP README

## Purpose

This repository now includes a project-specific MCP model and a minimal orchestration
server so that LLMs (including Claude-like and Copilot-like MCP clients) can operate
through a deterministic, auditable interface instead of issuing ad-hoc shell commands.

Policy: prefer to use MCP endpoints first, over ad-hoc shell commands.

Policy: Host installations require explicit user approval; Devcontainer installations may be performed by the MCP agent for development convenience. Any such installations will be reported in the MCP task summary.

## Why this design

- Model location choice: `.mcp/model.json`
  - `.mcp/` is tooling-neutral and can be shared by multiple clients.
  - Keeps model, logs, and task history colocated under one repo-local control folder.
  - Avoids coupling to one vendor namespace (`.claude` or `.copilot`).
- Server stack choice: Python standard library HTTP server (`mcp_server.py`)
  - No additional runtime dependency required for remote SSH bootstrap.
  - Works with existing Python-centric repo workflow.
  - Easy to run in constrained environments and easy to inspect.

## Test Toolchain Review

### Option: FastAPI testing with pytest + pytest-asyncio + httpx ASGI transport

Short description:
- Standard async Python testing stack for FastAPI that executes app-level tests quickly without launching a full external HTTP server.

Pros for this repo:
- Fast local and CI runtime for unit and most integration paths.
- Works naturally with the existing Python + pytest setup.
- Good debuggability in regular pytest output and IDE workflows.

Cons for this repo:
- External dependency realism (DB/services) requires extra setup.

Devcontainer/devctl integration effort:
- Python deps: `pytest`, `pytest-asyncio`, `httpx`.
- Optional for service-backed integration: `testcontainers`.

### Option: Svelte testing with Vitest + @testing-library/svelte

Short description:
- Modern Vite-native test runner and component testing utilities for Svelte, optimized for speed and watch/debug cycles.

Pros for this repo:
- Fast startup and execution in Vite/Svelte ecosystems.
- Good developer experience in devcontainer and CI.
- Aligns with existing Vite build tooling.

Cons for this repo:
- Requires adding test scripts/config in web UI package when not yet present.

Devcontainer/devctl integration effort:
- Node deps: `vitest`, `@testing-library/svelte`, `@testing-library/jest-dom`, `jsdom`.

### Option: Browser E2E with Playwright

Short description:
- Headless-capable browser automation with strong CI support, trace tooling, and deterministic execution.

Pros for this repo:
- Better CI ergonomics and parallelization than Selenium-heavy stacks.
- Rich debugging artifacts (traces/screenshots/videos).
- Well-suited for containerized execution.

Cons for this repo:
- Browser binaries increase bootstrap time.

Devcontainer/devctl integration effort:
- Node deps: `@playwright/test`, `playwright`.
- Browser install: `npx playwright install --with-deps chromium`.

### Alternative: Cypress

Short description:
- Browser E2E framework with interactive runner and strong UI-focused DX.

Pros for this repo:
- Excellent local debugging UI.

Cons for this repo:
- Heavier CI/runtime footprint than Playwright for this setup.
- Less aligned with desired lightweight remote-shell/bootstrap path.

Devcontainer/devctl integration effort:
- Node deps: `cypress` (+ optional system deps).

### Alternative: Jest (instead of Vitest)

Short description:
- General-purpose JS test runner with broad ecosystem support.

Pros for this repo:
- Mature ecosystem and many examples.

Cons for this repo:
- Slower and less Vite-native for Svelte projects than Vitest.

Devcontainer/devctl integration effort:
- Node deps: `jest`, `ts-jest` or Babel config, DOM test libs.

### Alternative: Selenium (not recommended)

Short description:
- Browser automation via WebDriver stack.

Pros for this repo:
- Broad cross-browser history and legacy ecosystem coverage.

Cons for this repo:
- Highest operational complexity and lowest velocity for this workflow.

Devcontainer/devctl integration effort:
- Selenium package + browser drivers/grid runtime management.

## Final Toolchain Choice

- Backend unit tests: `pytest + pytest-asyncio + httpx.AsyncClient(ASGITransport)`
- Backend integration tests: `pytest` integration suite (+ optional `testcontainers` where external service realism is required)
- Web unit/component tests: `vitest + @testing-library/svelte`
- Web E2E tests: `playwright`

Rationale (concise):
- Best fit with existing Python/Vite stack and current repository tooling.
- Fastest end-to-end feedback loop in devcontainer and CI contexts.
- Strong debug capability (pytest traces + Playwright traces).
- Lowest complexity increase while preserving realistic integration/E2E paths.

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

Run backend unit tests via MCP:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"backend.test.unit"}'
```

Run backend integration tests via MCP:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"backend.test.integration"}'
```

Run web unit/component tests via MCP:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"web.test.unit"}'
```

Run web E2E bootstrap/validation via MCP:

```bash
curl -sS -X POST http://<server>/mcp/exec \
  -H 'Content-Type: application/json' \
  -d '{"task":"web.e2e"}'
```

## MCP Test Flow (Canonical Tasks)

- `backend.test.unit`
  - Uses pytest unit suite.
  - If devcontainer exists, runs Python bootstrap prerequisite first.
- `backend.test.integration`
  - Uses pytest integration suite.
  - Optional containerized dependency support via testcontainers package bootstrap.
- `web.test.unit`
  - Uses Vitest + Testing Library in devcontainer when available.
  - Falls back to a documented placeholder message when devcontainer is not running.
- `web.e2e`
  - Uses Playwright setup in devcontainer and installs Chromium browser dependencies.

Additional devctl-equivalent MCP tasks:

- `devctl.bootstrap-python-tests`
- `devctl.bootstrap-web-tests`
- `devctl.install-playwright-browsers`

These are modeled in `.mcp/model.json` as deterministic command sequences because
the current `dev/devctl` script does not yet expose those exact subcommands.

## Model extension guidance

Edit `.mcp/model.json` and keep these rules:

- Add new deterministic command lists under `mappings`.
- Add domain-level documentation under `domains`.
- Add verification recipes under `verifications`.
- Never place secrets in the model; only placeholders and env var names.
- Keep task keys stable (for example: `backend.test.unit`, `web.deploy.staging`).
- Keep install steps idempotent and constrained to devcontainer operations by default.

## Security model

- The server rejects arbitrary command requests.
- Only tasks explicitly defined in `.mcp/model.json` can be executed.
- `cwd` is constrained to stay inside this workspace.
- For test orchestration, host package installation is forbidden unless explicitly approved by the user.

## Troubleshooting

- Devcontainer not running:
  - Use `./dev/devctl status`, then `./dev/devctl create` as needed.
- Devcontainer test dependencies:
  - Trigger MCP task `devctl.bootstrap-python-tests` and `devctl.bootstrap-web-tests`.
  - Trigger MCP task `devctl.install-playwright-browsers` for browser binaries.
- `devctl` missing or not executable:
  - Ensure `dev/devctl` exists and has execute bit (`chmod +x dev/devctl`).
- `stagectl` command mismatch:
  - This repo uses `staging/stagingctl`; compatibility aliases are documented in the model.
- Remote SSH access issues:
  - Verify host firewall/port forwarding or use SSH local forwarding.
- Endpoint returns unknown task:
  - Confirm key exists in `.mcp/model.json` under `mappings`.