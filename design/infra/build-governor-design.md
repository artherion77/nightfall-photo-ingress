# Build Governor — Design Document

**Status:** proposed  
**Date:** 2025-07-24  
**Owner:** Systems Engineering  
**See also:** [devctl-update-architecture.md](devctl-update-architecture.md), [AGENTS.md](../../AGENTS.md)

---

## Table of Contents

1. [Summary](#1-summary)
2. [Problem Statement](#2-problem-statement)
3. [Design Goals and Constraints](#3-design-goals-and-constraints)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Command Surface](#5-command-surface)
6. [Preflight Checks](#6-preflight-checks)
7. [Target Manifest Format](#7-target-manifest-format)
8. [Machine-Readable Outputs](#8-machine-readable-outputs)
9. [Safety and Privacy Considerations](#9-safety-and-privacy-considerations)
10. [Operational UX](#10-operational-ux)
11. [Integration Notes](#11-integration-notes)
12. [Open Questions and Decision Points](#12-open-questions-and-decision-points)
13. [Executor Refactoring: FD-Safe Process Tree](#13-executor-refactoring-fd-safe-process-tree)
14. [Appendix: Mapping to Existing Repo Artifacts](#14-appendix-mapping-to-existing-repo-artifacts)
15. [Token Authority Model](#15-token-authority-model)
16. [Artifact Immutability and Promotion](#16-artifact-immutability-and-promotion)
17. [Build Governor Enforcement Responsibilities](#17-build-governor-enforcement-responsibilities)
18. [Preflight Execution Context Contract](#18-preflight-execution-context-contract)
19. [Token Placeholder Semantics](#19-token-placeholder-semantics)

---

## 1. Summary

The Build Governor is a proposed thin orchestration layer that coordinates all
build, test, and deploy targets in nightfall-photo-ingress through a single
entry point. It does **not** replace or rewrite existing tools (`devctl`,
`stagingctl`, `metricsctl`, `build-metrics-dashboard`). Instead, it provides:

- A unified manifest declaring every buildable/testable target and its
  dependencies.
- A single CLI (`govctl`) that resolves a dependency graph, runs preflight
  checks, delegates to existing tools, and emits machine-readable results.
- Deterministic, auditable build/test/deploy runs with JSONL structured output
  alongside the existing human-readable log streams.

The design is minimal and non-invasive: existing scripts keep their current
interfaces, and `govctl` wraps them without modification.

---

## 2. Problem Statement

### 2.1 Fragmented Entry Points

The repository has four independent orchestration scripts, each with its own
subcommand surface, conventions, and precondition checks:

| Script | Subcommands | Scope |
|--------|-------------|-------|
| `devctl` | 14 | Dev container lifecycle, web builds, test dispatch |
| `stagingctl` | 8 | Staging container lifecycle, smoke, evidence |
| `metricsctl` | 20+ | Metrics pipeline (8 modules), poller runtime |
| `build-metrics-dashboard` | 1 | Dashboard SvelteKit build + fingerprint |

An operator running a full validation cycle must manually sequence calls across
these tools, know preconditions (container running, snapshot present, stacks
drift-free), and interpret independent exit codes.

### 2.2 No Cross-Target Dependency Graph

Targets have implicit dependencies that are only encoded in operator knowledge:

- `stagingctl install` requires a wheel built by `python -m build`, which
  requires the venv and source tree to be current.
- `build-metrics-dashboard` calls `devctl ensure-stack-ready dashboard`
  internally, but there is no external signal that this has happened or whether
  it needs to happen.
- `./dev/bin/metricsctl generate-dashboard` acquires the global repo lock and calls
  `devctl` internally for drift preflight, but the caller cannot inspect this
  chain.
- `devctl test-web-e2e` requires `devctl ensure-stack-ready webui` to have run
  first.

Without a declared dependency graph, automation (CI, MCP orchestration, agents)
cannot safely parallelize independent targets or correctly sequence dependent
ones.

### 2.3 Human-Only Output

All existing tools emit colored log lines to stdout/stderr using `nf_log_info`,
`nf_log_ok`, `nf_log_warn`, and `nf_log_fail` (via `lib/container-common.sh`).
Exit codes are binary (0 = success, non-zero = failure). There is no structured
output for:

- Pass/fail per-target with timing.
- Aggregate summary across a multi-target run.
- Machine-consumable drift reports (devctl `check` emits only human text).

The MCP server (`mcp_server.py`) and agent workflows must parse log text to
infer outcomes. Evidence collection in `stagingctl smoke` (JSONL assertions) is
the only exception, and it is not available for dev-container or metrics targets.

### 2.4 Repeated Precondition Logic

Container-exists, container-running, snapshot-present, cache-mounts-active, and
drift-free checks are duplicated across `devctl`, `stagingctl`,
`build-metrics-dashboard`, and `metricsctl`. Each tool re-implements its
own subset, using slightly different error messages and failure modes.

---

## 3. Design Goals and Constraints

### 3.1 Goals

| ID | Goal |
|----|------|
| G1 | Single entry point for any combination of build/test/deploy targets |
| G2 | Declared dependency graph so targets run in correct order |
| G3 | Machine-readable JSONL output alongside human log passthrough |
| G4 | Preflight check framework that consolidates precondition logic |
| G5 | Zero modification to existing tool internals (wrap, don't rewrite) |
| G6 | Composable: run one target, a named group, or the full graph |

### 3.2 Constraints

| ID | Constraint |
|----|------------|
| C1 | Non-invasive — existing `devctl`, `stagingctl`, `metricsctl`, `build-metrics-dashboard` must remain fully functional standalone |
| C2 | Shell-native — implemented in Bash, consistent with the existing `dev/bin/` toolchain; sources `lib/container-common.sh` |
| C3 | No new runtimes — must not introduce languages, package managers, or services beyond what the repo already uses (Bash, Python 3.11+, Node 22) |
| C4 | Respect the global repo lock — integrate with `/tmp/nightfall-repo.lock` and `DEVCTL_GLOBAL_LOCK_HELD` reentry guard |
| C5 | Offline-capable — the manifest is a local YAML file, not fetched from a remote registry |
| C6 | Minimal footprint — target is a single script (`dev/bin/govctl`) plus one manifest file (`dev/govctl-targets.yaml`) |

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       govctl CLI                        │
│  (parse args → load manifest → resolve graph → execute) │
└────────────┬───────────────┬───────────────┬────────────┘
             │               │               │
     ┌───────▼──────┐ ┌─────▼──────┐ ┌──────▼──────────┐
     │  Preflight   │ │  Executor  │ │ Result Emitter   │
     │  Checker     │ │  (delegate │ │ (JSONL + human   │
     │              │ │  to tools) │ │  log passthrough) │
     └───────┬──────┘ └─────┬──────┘ └──────────────────┘
             │               │
     ┌───────▼───────────────▼───────────────────────────┐
     │        Existing tool layer (unchanged)             │
     │  devctl · stagingctl · metricsctl                  │
     │  build-metrics-dashboard · python -m build         │
     └───────────────────────────────────────────────────┘
```

### 4.1 Components

**Manifest loader** — Reads `dev/govctl-targets.yaml`, validates schema,
expands group aliases.

**Graph resolver** — Topological sort of requested targets and their declared
`requires` edges. Detects cycles at load time.

**Preflight checker** — Runs declared `preflight` checks for each target before
execution. Checks are named, reusable, and short-circuit on first failure
(unless `--continue-on-error`).

**Executor** — For each target in resolved order: acquire global lock (if
target declares `lock: true`), run the declared `command`, capture exit code
and wall-clock time, release lock.

**Result emitter** — Writes one JSONL line per target event (started, passed,
failed, skipped). Passes the underlying tool's stdout/stderr through to the
terminal unmodified.

---

## 5. Command Surface

```
govctl <target|group> [options]
govctl list [--format human|json]
govctl check [<target|group>] [--format human|json]
govctl graph [<target|group>] [--format human|dot]
```

### 5.1 Run Targets

```bash
# Run a single target
govctl backend.test.unit

# Run a named group
govctl test.all

# Run multiple targets (graph-resolved)
govctl backend.test.unit web.test.unit

# Run everything
govctl all
```

### 5.2 Options

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | off | Print resolved execution plan without running |
| `--continue-on-error` | off | Don't abort on first target failure |
| `--json` | off | Emit only JSONL (suppress human log passthrough) |
| `--log-dir <path>` | `artifacts/govctl/` | Directory for per-target log capture and summary |
| `--parallel` | off | Run independent targets concurrently (future; see §12) |

### 5.3 Inspect Commands

```bash
# List all targets and groups
govctl list

# Run preflight checks only (no execution)
govctl check backend.test.unit

# Print dependency graph
govctl graph test.all --format dot | dot -Tpng -o graph.png
```

---

## 6. Preflight Checks

Preflight checks are named, reusable predicates. Each target in the manifest
declares zero or more checks. The governor runs them before executing the
target's command.

### 6.1 Built-In Checks

| Check name | What it verifies | Maps to |
|------------|-----------------|---------|
| `container-exists:<name>` | LXC container `<name>` exists | `lxc info <name>` exit 0 |
| `container-running:<name>` | LXC container `<name>` is Running | `lxc info <name>` status field |
| `snapshot-exists:<container>/<snap>` | Named snapshot present | `lxc info <container>` snapshots list |
| `cache-mounts-active` | All 4 bind-mount caches attached to dev container | `lxc config device list` |
| `stack-drift-free:<stack>` | Manifest hash matches for named stack | Compare host SHA256(pkg+lock) vs container hash |
| `node-version-match` | Container Node version matches `.node-version` | `lxc exec node --version` vs file content |
| `venv-exists:<path>` | Python venv directory exists in container | `lxc exec test -d <path>` |
| `wheel-exists` | At least one `.whl` in `dist/` | `ls dist/*.whl` |
| `bridge-network:<bridge>` | Container attached to named bridge | `lxc config device show` contains bridge |

### 6.2 Check Semantics

- A check returns 0 (pass) or 1 (fail) and a one-line reason string.
- On failure, the governor emits a `preflight_failed` JSONL event and skips
  the target (or aborts, depending on `--continue-on-error`).
- `govctl check <target>` runs only preflights and exits, useful for
  diagnosing environment state without side effects.

---

## 7. Target Manifest Format

The manifest lives at `dev/govctl-targets.yaml`. Below is the proposed schema
with representative entries derived from actual repository tooling.

```yaml
# dev/govctl-targets.yaml
version: 1
defaults:
  lock: false
  timeout_seconds: 300

targets:

  # --- Development container foundations ---
  dev.ensure-running:
    description: "Ensure dev container exists and is running"
    command: |
      lxc info dev-photo-ingress >/dev/null 2>&1 || ./dev/bin/devctl setup
      lxc start dev-photo-ingress 2>/dev/null || true
    preflight: []
    lock: false

  dev.stack-ready.webui:
    description: "Sync webui sources and fix drift if needed"
    command: "./dev/bin/devctl ensure-stack-ready webui"
    requires: [dev.ensure-running]
    preflight:
      - container-running:dev-photo-ingress
      - cache-mounts-active
    lock: true

  dev.stack-ready.dashboard:
    description: "Sync dashboard sources and fix drift if needed"
    command: "./dev/bin/devctl ensure-stack-ready dashboard"
    requires: [dev.ensure-running]
    preflight:
      - container-running:dev-photo-ingress
      - cache-mounts-active
    lock: true

  # --- Backend targets ---
  backend.build.wheel:
    description: "Build Python wheel into dist/"
    command: "python -m build --wheel --outdir dist/"
    requires: []
    preflight:
      - venv-exists:/opt/ingress
    lock: false

  backend.test.unit:
    description: "Run backend unit tests"
    command: "pytest tests/unit -q"
    requires: []
    preflight: []
    lock: false
    timeout_seconds: 120

  backend.test.integration:
    description: "Run backend integration tests"
    command: "pytest tests/integration -q"
    requires: []
    preflight: []
    lock: false
    timeout_seconds: 180

  # --- Web targets ---
  web.typecheck:
    description: "SvelteKit typecheck (webui)"
    command: "./dev/bin/devctl test-web-typecheck"
    requires: [dev.stack-ready.webui]
    preflight:
      - container-running:dev-photo-ingress
      - node-version-match
    lock: true

  web.typecheck.dashboard:
    description: "SvelteKit typecheck (metrics dashboard)"
    command: "./dev/bin/devctl test-metrics-dashboard-typecheck"
    requires: [dev.stack-ready.dashboard]
    preflight:
      - container-running:dev-photo-ingress
      - node-version-match
    lock: true

  web.test.unit:
    description: "Vitest unit tests for webui"
    command: "./dev/bin/devctl test-web-unit"
    requires: [dev.stack-ready.webui]
    preflight:
      - container-running:dev-photo-ingress
      - stack-drift-free:webui
    lock: true
    timeout_seconds: 120

  web.test.e2e:
    description: "Playwright end-to-end tests"
    command: "./dev/bin/devctl test-web-e2e"
    requires: [dev.stack-ready.webui]
    preflight:
      - container-running:dev-photo-ingress
      - stack-drift-free:webui
    lock: true
    timeout_seconds: 300

  web.build:
    description: "Production SvelteKit build (webui)"
    command: |
      lxc exec dev-photo-ingress -- bash -c \
        'cd /opt/nightfall-webui && npm run build'
    requires: [dev.stack-ready.webui]
    preflight:
      - container-running:dev-photo-ingress
      - stack-drift-free:webui
    lock: true

  # --- Metrics targets ---
  metrics.build.dashboard:
    description: "Build metrics dashboard statics + fingerprint"
    command: "./dev/bin/build-metrics-dashboard"
    requires: [dev.stack-ready.dashboard]
    preflight:
      - container-running:dev-photo-ingress
    lock: true

  metrics.collect.backend:
    description: "Collect backend metrics (Module 2)"
    command: "./dev/bin/metricsctl collect-backend"
    requires: []
    preflight: []
    lock: true

  metrics.collect.frontend:
    description: "Collect frontend metrics (Module 3)"
    command: "./dev/bin/metricsctl collect-frontend"
    requires: []
    preflight: []
    lock: true

  metrics.aggregate:
    description: "Aggregate collected metrics (Module 4)"
    command: "./dev/bin/metricsctl aggregate"
    requires: [metrics.collect.backend, metrics.collect.frontend]
    preflight: []
    lock: true

  metrics.generate.dashboard:
    description: "Generate dashboard from aggregated data (Module 5)"
    command: "./dev/bin/metricsctl generate-dashboard"
    requires: [metrics.aggregate, metrics.build.dashboard]
    preflight: []
    lock: true

  metrics.publish:
    description: "Publish metrics surface (Module 7)"
    command: "./dev/bin/metricsctl publish"
    requires: [metrics.generate.dashboard]
    preflight: []
    lock: true

  # --- Staging targets ---
  staging.install:
    description: "Build wheel and install into staging container"
    command: "./dev/bin/stagingctl install"
    requires: [backend.build.wheel]
    preflight:
      - container-running:staging-photo-ingress
      - bridge-network:br-staging
    lock: false

  staging.smoke:
    description: "Run headless smoke assertions in staging"
    command: "./dev/bin/stagingctl smoke"
    requires: [staging.install]
    preflight:
      - container-running:staging-photo-ingress
    lock: false

  staging.smoke-live:
    description: "Authenticated live poll + secret scan"
    command: "./dev/bin/stagingctl smoke-live"
    requires: [staging.install]
    preflight:
      - container-running:staging-photo-ingress
    lock: false

  # --- Drift inspection (read-only) ---
  dev.check:
    description: "Read-only drift report"
    command: "./dev/bin/devctl check"
    requires: []
    preflight:
      - container-running:dev-photo-ingress
    lock: false

groups:
  test.backend:
    targets: [backend.test.unit, backend.test.integration]

  test.web:
    targets: [web.typecheck, web.typecheck.dashboard, web.test.unit]

  test.all:
    targets: [test.backend, test.web]

  build.all:
    targets: [backend.build.wheel, web.build, metrics.build.dashboard]

  staging.full:
    targets: [staging.install, staging.smoke]

  metrics.full:
    targets:
      - metrics.collect.backend
      - metrics.collect.frontend
      - metrics.aggregate
      - metrics.generate.dashboard
      - metrics.publish

  all:
    targets: [test.all, build.all, staging.full, metrics.full]
```

### 7.1 Schema Rules

- `targets.<name>.command` — Shell command string. Executed via `bash -c`.
- `targets.<name>.requires` — List of target names that must complete
  successfully before this target runs. May reference groups (expanded at load).
- `targets.<name>.preflight` — List of named check strings (see §6).
- `targets.<name>.lock` — Boolean. If `true`, acquire `/tmp/nightfall-repo.lock`
  before execution and set `DEVCTL_GLOBAL_LOCK_HELD=1`.
- `targets.<name>.timeout_seconds` — Override default timeout for this target.
- `groups.<name>.targets` — Ordered list of target or group names.

---

## 8. Machine-Readable Outputs

### 8.1 JSONL Event Stream

Every `govctl` run writes a JSONL file to `<log-dir>/run-<timestamp>.jsonl`.
Each line is a self-contained JSON object:

```jsonc
// Run started
{"event":"run_started","timestamp":"2025-07-24T10:00:00Z","targets":["test.all"],"resolved":["backend.test.unit","backend.test.integration","dev.stack-ready.webui","web.typecheck","web.typecheck.dashboard","web.test.unit"]}

// Preflight pass
{"event":"preflight_passed","target":"web.test.unit","check":"container-running:dev-photo-ingress","timestamp":"..."}

// Preflight fail
{"event":"preflight_failed","target":"web.test.unit","check":"stack-drift-free:webui","reason":"manifest hash mismatch: host=abc123 container=def456","timestamp":"..."}

// Target started
{"event":"target_started","target":"backend.test.unit","command":"pytest tests/unit -q","timestamp":"..."}

// Target passed
{"event":"target_passed","target":"backend.test.unit","exit_code":0,"duration_seconds":14.2,"timestamp":"..."}

// Target failed
{"event":"target_failed","target":"backend.test.unit","exit_code":1,"duration_seconds":8.7,"timestamp":"..."}

// Target skipped (dependency failed or preflight failed)
{"event":"target_skipped","target":"web.test.unit","reason":"dependency dev.stack-ready.webui failed","timestamp":"..."}

// Run finished
{"event":"run_finished","timestamp":"...","total_targets":6,"passed":5,"failed":1,"skipped":0,"duration_seconds":87.3}
```

### 8.2 Per-Target Logs

Each target's stdout and stderr are tee'd to
`<log-dir>/run-<timestamp>/<target-name>.log`. The human log stream is passed
through to the terminal in real time, preserving the colored `nf_log_*` output
operators are accustomed to.

### 8.3 Summary File

At run completion, `govctl` writes `<log-dir>/run-<timestamp>/summary.json`:

```json
{
  "run_id": "20250724T100000-a1b2c3",
  "requested": ["test.all"],
  "resolved": ["backend.test.unit", "..."],
  "results": {
    "backend.test.unit": {"status": "passed", "exit_code": 0, "duration_seconds": 14.2},
    "web.typecheck": {"status": "failed", "exit_code": 1, "duration_seconds": 3.1}
  },
  "totals": {"passed": 5, "failed": 1, "skipped": 0},
  "duration_seconds": 87.3
}
```

---

## 9. Safety and Privacy Considerations

### 9.1 No Credential Handling

`govctl` never reads, stores, or passes credentials. Authentication workflows
(`stagingctl auth-setup`, MSAL device-code flows) remain entirely within their
existing tools. `govctl` only invokes the declared `command` string.

### 9.2 Lock Safety

Targets that declare `lock: true` acquire the existing
`/tmp/nightfall-repo.lock` via `flock(1)` with the same timeout semantics as
`devctl` (`REPO_LOCK_TIMEOUT_SEC`, default 300s). The `DEVCTL_GLOBAL_LOCK_HELD`
reentry guard is set so that downstream tools (e.g., `metricsctl` calling
`devctl`) do not deadlock.

### 9.3 No Privilege Escalation

`govctl` runs as the invoking user. It does not use `sudo`, `setuid`, or
modify file permissions beyond writing to its own `<log-dir>`. LXC operations
inherit the caller's existing LXC permissions (typically via the `lxd` group).

### 9.4 Command Allowlist

`govctl` only executes commands declared in `govctl-targets.yaml`. It does not
accept arbitrary shell strings from the CLI. The manifest is a local file under
version control; changes are reviewable.

### 9.5 Secret Scan Passthrough

Stagingctl's secret-scan assertions run unmodified inside their existing
container sandbox. `govctl` captures the exit code and log output but does not
inspect or index scanned content.

### 9.6 Log Sensitivity

Per-target log files may contain environment details (paths, container names,
versions). The `<log-dir>` (`artifacts/govctl/`) should be `.gitignore`d to
prevent accidental commit of ephemeral run data. No secrets are expected in
build/test output, but the operator should treat log artifacts with the same
care as existing `stagingctl evidence` outputs.

---

## 10. Operational UX

### 10.1 Typical Operator Workflows

**Quick backend validation:**
```bash
govctl backend.test.unit
```

**Full test suite before committing:**
```bash
govctl test.all
```

**Pre-release validation (build + staging smoke):**
```bash
govctl build.all staging.full
```

**Diagnose environment state:**
```bash
govctl check test.all
```

**Dry-run to preview execution plan:**
```bash
govctl test.all --dry-run
```

**Metrics pipeline end-to-end:**
```bash
govctl metrics.full
```

### 10.2 Output Experience

Default mode shows human-readable colored logs from each tool, with a short
header/footer per target added by govctl:

```
──── backend.test.unit ─────────────────────────────────
[devctl] INFO: Running pytest tests/unit -q ...
... (normal pytest output) ...
──── backend.test.unit: PASSED (14.2s) ─────────────────

──── web.typecheck ─────────────────────────────────────
[devctl] INFO: Running svelte-kit sync + svelte-check ...
... (normal svelte-check output) ...
──── web.typecheck: PASSED (3.8s) ──────────────────────

═══════════════════════════════════════════════════════
  govctl: 6 targets — 5 passed, 1 failed, 0 skipped
  Total: 87.3s
  Log: artifacts/govctl/run-20250724T100000/
═══════════════════════════════════════════════════════
```

### 10.3 Failure Behavior

- By default, `govctl` aborts on the first target failure (fail-fast). Targets
  that do not depend on the failed target are skipped.
- With `--continue-on-error`, all runnable targets execute regardless of
  independent failures. The final summary reports all results.
- An exit code of 0 means all targets passed. Non-zero means at least one
  target failed or was skipped due to preflight failure.

### 10.4 Discoverability

`govctl list` prints all targets and groups with descriptions, so operators
and agents can discover available targets without reading the manifest file.

---

## 11. Integration Notes

### 11.1 MCP Server Integration

The MCP model (`.mcp/model.json`) currently maps task names to specific
`devctl`/`stagingctl` commands. With `govctl`, the MCP task mappings can
optionally route through the governor for targets that benefit from preflight
checks and structured output.

Example: the MCP mapping for `backend.test.unit` could change from:
```json
{"command": "cd $WORKSPACE && pytest tests/unit"}
```
to:
```json
{"command": "cd $WORKSPACE && ./dev/bin/govctl backend.test.unit --json"}
```

The `--json` flag gives the MCP server structured JSONL it can parse without
regex, replacing the current text-scraping approach.

**Non-breaking:** Existing MCP task mappings continue to work unchanged. The
`govctl` integration is opt-in per task.

### 11.2 Agent Workflows

LLM agents (via AGENTS.md policy) can use `govctl` as the preferred entry
point, consistent with the "prefer MCP endpoints first" policy. Benefits:

- `govctl check <target> --format json` gives agents a machine-parseable
  environment health report.
- `govctl <target> --json` gives agents structured pass/fail results
  without log parsing.
- `govctl graph <target> --format dot` lets agents understand dependency
  relationships.
- `govctl list --format json` lets agents discover available targets
  programmatically.

### 11.3 Contract-Test Mode

Existing `DEVCTL_CONTRACT_TEST_ROOT` support is preserved. When set, `devctl`
subcommands invoked by `govctl` still respect the contract-test bypass. No
changes to the contract-test flow are required.

### 11.4 CI/CD (Future)

The JSONL output and summary.json are designed to be CI-friendly. A future CI
pipeline could:

1. Run `govctl all --json --continue-on-error`
2. Parse `summary.json` for pass/fail status.
3. Archive `artifacts/govctl/run-*/` as build artifacts.

This is not in scope for initial implementation but the output format is
designed with it in mind.

### 11.5 Relationship to devctl update

The `devctl update` command (see devctl-update-architecture.md) performs
drift remediation with a built-in regression gate (typecheck → unit tests →
pytest). `govctl` does not replace this workflow. Instead, `devctl update`
remains the correct tool for "fix my environment and prove it's good."
`govctl` orchestrates targets that assume the environment is already good (or
uses preflight checks to verify before running).

A future extension could add a `dev.update` target that wraps `devctl update`,
allowing `govctl dev.update test.all` as a single "update and validate"
invocation.

---

## 12. Open Questions and Decision Points

### Q1: Parallel Execution

Should `govctl` support running independent targets concurrently?

- **Pro:** Backend pytest tests and container-based web tests have no shared
  state and could run simultaneously, reducing wall-clock time.
- **Con:** The global repo lock serializes all container operations anyway.
  Parallel is only beneficial for targets that don't need the lock (e.g.,
  `backend.test.unit` alongside a non-lock target).
- **Proposed:** Ship without `--parallel` initially. Add it when there is a
  demonstrated need. The dependency graph already captures enough information
  to enable it later without manifest changes.

### Q2: YAML Parser in Bash

Parsing YAML natively in Bash is fragile. Options:

- **Option A:** Use Python's `yaml.safe_load()` via a small helper script
  (the repo already has Python 3.11+ and PyYAML is in the standard ecosystem).
  `govctl` would call `python3 -c 'import yaml; ...'` to load the manifest
  and emit a normalized intermediate format (e.g., a flat key=value list or
  JSON) that Bash can consume.
- **Option B:** Use a restricted YAML subset that can be parsed with `grep`/
  `awk` (flat keys, no multi-line strings, no anchors). This limits manifest
  expressiveness but avoids the Python dependency.
- **Proposed:** Option A. Python is already a hard dependency; a 10-line parser
  helper is less fragile than hand-rolled Bash YAML parsing.

### Q3: Manifest Location

Should the manifest live at `dev/govctl-targets.yaml` (alongside the scripts)
or at project root (for discoverability)?

- **Proposed:** `dev/govctl-targets.yaml` — keeps all build tooling under
  `dev/`, consistent with `devctl`, `stagingctl`, etc. The `govctl` script
  itself lives at `dev/bin/govctl`.

### Q4: Timeout Handling

How should `govctl` enforce target timeouts?

- **Proposed:** Use `timeout(1)` (coreutils) to wrap the `bash -c` invocation.
  On timeout, emit a `target_failed` event with `reason: "timeout"` and kill
  the process group.

### Q5: govctl Self-Bootstrap

Does `govctl` need its own preflight (e.g., verify `yq` or Python is
available)?

- **Proposed:** Yes. `govctl` performs a one-time self-check on first
  invocation: verify `python3` is available, verify `lxc` is available, verify
  `flock` is available. Failures produce a clear error message. This check
  is cached for the duration of the run.

### Q6: Artifact Retention

Should `govctl` prune old run artifacts from `artifacts/govctl/`?

- **Proposed:** Not initially. The operator can use `find` or adapt the
  existing `./dev/bin/metricsctl retention-prune` pattern later. Adding retention
  complexity is premature until artifact volume is a real concern.

---

## 13. Executor Refactoring: FD-Safe Process Tree

**Status:** implemented  
**Date:** 2025-07-26  
**Addresses:** GitHub issue #12 — govctl test.all intermittently times out in
`dev.stack-ready.webui` after cold container start.

### 13.1 Problem

The original executor ran target commands using:

```bash
(
    cd "$GOVCTL_EXEC_PROJECT_ROOT"
    timeout "$timeout_sec" bash -c "$command"
) 2>&1 | tee "$target_log" || exit_code="${PIPESTATUS[0]:-1}"
```

`timeout(1)` (GNU coreutils) by default creates a **new process group** via
`setpgid()` so it can later kill the entire group if the time limit expires.
When `lxc` is installed via snap, the `snap-confine` security wrapper
performs process-group and session checks during setup. When `snap-confine`
runs inside a non-leader process group created by `timeout`, it intermittently
hangs or exits with status 1, causing the outer `timeout` to fire (exit 124).

The failure is non-deterministic because `snap-confine`'s behaviour depends on
kernel scheduling of the `setpgid()` race between `timeout` and the child exec
chain.

### 13.2 Root Cause Analysis Summary

Hypotheses that were systematically ruled out:

| Hypothesis | Test | Result |
|---|---|---|
| Container readiness race | Artifact logs show "ready" before hang | Ruled out |
| flock reentry deadlock | Tested explicit FD reentry | Ruled out |
| Cold boot time exceeding timeout | 5/5 manual cold starts succeed | Ruled out |
| `tee` pipeline buffering | Tested without tee: same hang | Ruled out |
| `set -e` / `pipefail` propagation | Verified not set in executor | Ruled out |
| Inherited FD (flock FD) | Closed ALL FDs > 2 in child: still hangs | Ruled out |
| `timeout` process group (`setpgid`) | `timeout --foreground`: passes | **Confirmed** |

Key evidence:

- Closing all inherited FDs in the child (including the flock FD) does NOT
  prevent the hang. The issue is not FD-related.
- `timeout --foreground` (which skips `setpgid()`) resolves the issue
  immediately — even with all FDs inherited, even through the full devctl stack.
- `lxc exec --force-noninteractive` also works, confirming the interaction is
  between snap-confine's process group detection and timeout's `setpgid()`.

### 13.3 Design Change

A single-line change to the executor's command invocation:

```diff
- timeout "$timeout_sec" bash -c "$command"
+ timeout --foreground "$timeout_sec" bash -c "$command"
```

The `--foreground` flag tells `timeout` to **not** create a new process group.
The child command inherits the caller's process group, which is what
`snap-confine` expects.

**Trade-off:** Without a dedicated process group, `timeout` cannot
`kill(-pgid)` the entire group on expiry. Instead it sends SIGTERM to the
direct child only. For govctl's use case this is acceptable because:

1. `bash -c` receives SIGTERM, which propagates to its foreground job.
2. devctl/lxc exec handle SIGTERM correctly (tested).
3. govctl already has per-target timeout events and the run aborts on failure.

### 13.4 Compatibility

- Lock semantics: unchanged (flock held by parent, `DEVCTL_GLOBAL_LOCK_HELD=1`
  prevents reentry).
- Tee pipeline: unchanged (kept for real-time log passthrough).
- JSONL event output: unchanged.
- Process tree depth: unchanged (same nesting, just no `setpgid`).
- No changes to `govctl-targets.yaml`, preflight system, or graph resolution.

---

## 14. Appendix: Mapping to Existing Repo Artifacts

This table maps every proposed `govctl` target back to the existing tool,
script, or command it delegates to.

| govctl Target | Delegates To | Source Script | Lock | Notes |
|---------------|-------------|---------------|------|-------|
| `dev.ensure-running` | `lxc info` / `devctl setup` | `dev/bin/devctl` | No | Idempotent container bootstrap |
| `dev.stack-ready.webui` | `devctl ensure-stack-ready webui` | `dev/bin/devctl` | Yes | Sync + drift fix |
| `dev.stack-ready.dashboard` | `devctl ensure-stack-ready dashboard` | `dev/bin/devctl` | Yes | Sync + drift fix |
| `dev.check` | `devctl check` | `dev/bin/devctl` | No | Read-only drift report |
| `backend.build.wheel` | `python -m build --wheel` | pyproject.toml | No | setuptools backend |
| `backend.test.unit` | `pytest tests/unit` | pyproject.toml | No | pytest.ini_options testpaths |
| `backend.test.integration` | `pytest tests/integration` | pyproject.toml | No | pytest.ini_options testpaths |
| `web.typecheck` | `devctl test-web-typecheck` | `dev/bin/devctl` | Yes | svelte-kit sync + svelte-check |
| `web.typecheck.dashboard` | `devctl test-metrics-dashboard-typecheck` | `dev/bin/devctl` | Yes | Dashboard-specific typecheck |
| `web.test.unit` | `devctl test-web-unit` | `dev/bin/devctl` | Yes | svelte-check + vitest run |
| `web.test.e2e` | `devctl test-web-e2e` | `dev/bin/devctl` | Yes | Playwright |
| `web.build` | `npm run build` via `lxc exec` | webui/package.json | Yes | SvelteKit → adapter-static |
| `metrics.build.dashboard` | `build-metrics-dashboard` | `dev/bin/build-metrics-dashboard` | Yes | SvelteKit → tar → fingerprint |
| `metrics.collect.backend` | `./dev/bin/metricsctl collect-backend` | metricsctl | Yes | Module 2 |
| `metrics.collect.frontend` | `./dev/bin/metricsctl collect-frontend` | metricsctl | Yes | Module 3 |
| `metrics.aggregate` | `./dev/bin/metricsctl aggregate` | metricsctl | Yes | Module 4 |
| `metrics.generate.dashboard` | `./dev/bin/metricsctl generate-dashboard` | metricsctl | Yes | Module 5 (internal devctl preflight) |
| `metrics.publish` | `./dev/bin/metricsctl publish` | metricsctl | Yes | Module 7 |
| `staging.install` | `stagingctl install` | `dev/bin/stagingctl` | No | Builds wheel + deploys to staging container |
| `staging.smoke` | `stagingctl smoke` | `dev/bin/stagingctl` | No | JSONL evidence collection |
| `staging.smoke-live` | `stagingctl smoke-live` | `dev/bin/stagingctl` | No | Authenticated poll + secret scan |

### 14.1 Existing Shared Infrastructure Reused

| Artifact | Path | Usage in govctl |
|----------|------|-----------------|
| Container helpers | `lib/container-common.sh` | Sourced for `nf_log_*` functions, `nf_require_container_*` |
| Global repo lock | `/tmp/nightfall-repo.lock` | Acquired via `flock` for lock-requiring targets |
| Reentry guard | `DEVCTL_GLOBAL_LOCK_HELD` env | Set by govctl before delegating to lock-aware tools |
| Node version pin | `.node-version` | Read by `node-version-match` preflight check |
| Manifest hashes | `/opt/nightfall-manifest/*.hash` | Read by `stack-drift-free:*` preflight check |
| MCP model | `.mcp/model.json` | Reference for task name consistency (govctl targets mirror MCP task names where applicable) |
| Evidence directory | `artifacts/govctl/` | New — follows the `artifacts/` convention from `artifacts/metrics/` |
| Build output | `dist/` | Reused by `backend.build.wheel` → `staging.install` chain |

### 14.2 New Artifacts Introduced

| Artifact | Path | Description |
|----------|------|-------------|
| `govctl` script | `dev/bin/govctl` | Single Bash entry point (~300–500 lines estimated) |
| Target manifest | `dev/govctl-targets.yaml` | Declarative target/group/preflight definitions |
| Run logs | `artifacts/govctl/run-<ts>/` | Per-run directory with JSONL events + per-target logs |
| .gitignore entry | `artifacts/govctl/` | Ephemeral run data excluded from VCS |

---

## 15. Token Authority Model

**Status:** proposed  
**Date:** 2025-07-27  
**Motivation:** Root-cause analysis of staging auth failures (see
`audit/staging-token-mismatch-root-cause.md`) identified that the API token
has no single canonical source, no build-time injection contract, and no
runtime validation contract. This section formalizes the token lifecycle as a
build governor concern.

### 15.1 Invariants

| ID | Invariant |
|----|-----------|
| T1 | There is exactly one canonical token definition per deployment environment: the `[web] api_token` value in the environment's authoritative INI configuration artifact. No alternate authoritative token source is permitted. |
| T2 | The frontend (SvelteKit) consumes the token exclusively via `PUBLIC_API_TOKEN` in `webui/.env`. This frontend value is a derived build-time materialization of T1 and must be byte-identical to the canonical token at build time. The value is then baked into static JS; it is never fetched or injected at runtime. |
| T3 | The backend (FastAPI) consumes the canonical token exclusively via `[web] api_token` in the INI config file loaded at process start. It is never read from environment variables, command-line flags, or secondary files. |
| T4 | The staging config template (`staging/container/photo-ingress.conf`) must contain a `[web]` section with `api_token` defined. A template missing this section is a build-time defect, not a runtime misconfiguration. |
| T5 | Token values must not appear in build logs, JSONL events, preflight check output, or `govctl` summary artifacts. |
| T6 | Token comparison must use constant-time comparison (`hmac.compare_digest` or equivalent). Direct string equality is prohibited. |

For audit purposes, token-bearing artifacts are classified as follows:

- Canonical definition: environment INI `[web] api_token` (authoritative).
- Derived materializations: `webui/.env` `PUBLIC_API_TOKEN` and built SPA `_app/env.js` token payload.
- Runtime consumptions: FastAPI process load from INI and SPA request header use of baked token.

### 15.2 Token Sources Per Environment

| Environment | Frontend Token Source | Backend Token Source |
|-------------|----------------------|----------------------|
| Development | `webui/.env` → SvelteKit build → `_app/env.js` | `conf/photo-ingress.dev.conf` `[web] api_token` |
| Staging | `webui/.env` → SvelteKit build → `_app/env.js` (baked in dev container, synced to staging) | `staging/container/photo-ingress.conf` `[web] api_token` |
| Production | `webui/.env` → SvelteKit build → `_app/env.js` (baked in dev container, promoted from staging) | `/etc/nightfall/photo-ingress.conf` `[web] api_token` |

### 15.3 Divergence Prohibition

The build governor treats frontend-backend token divergence as a defect class
equivalent to a broken build. The following divergence scenarios are defined:

| Scenario | Nature | Detection Point |
|----------|--------|-----------------|
| `webui/.env` contains a different token than the config template `[web] api_token` | Source divergence | Pre-build preflight |
| Config template is missing the `[web]` section entirely | Template defect | Pre-build preflight |
| Build artifact (`_app/env.js`) contains a token not present in any config file | Artifact drift | Post-build verification |
| Running API container has a `[web] api_token` that differs from the build artifact token | Deployment drift | Staging smoke |

### 15.4 Non-Goals

- Token rotation protocol. Rotation requires operational procedures beyond
  build orchestration.
- Secret management integration (Vault, SOPS, etc.). The token is a low-risk
  internal staging/dev credential. External secret managers are out of scope.
- Multi-token or role-based access. The current design uses a single bearer
  token per environment.

---

## 16. Artifact Immutability and Promotion

**Status:** proposed  
**Date:** 2025-07-27  
**Motivation:** The staging auth failure was partly caused by a mismatch between
the SPA build artifact and the runtime configuration. This section defines the
immutability contract for build artifacts and the promotion model that prevents
rebuild-induced drift.

### 16.1 Invariants

| ID | Invariant |
|----|-----------|
| A1 | A SvelteKit SPA build is an immutable artifact. Once produced by `web.build`, its contents must not be modified, patched, or re-baked before or during deployment. |
| A2 | The token baked into the SPA at build time is final. There is no post-build token injection, substitution, or templating step. |
| A3 | Staging deployment consumes the same build artifact as production. There is no separate staging build. |
| A4 | A Python wheel produced by `backend.build.wheel` is an immutable artifact. `staging.install` consumes it without modification. |
| A5 | Artifact identity is established by content hash (SHA-256) at build time. Any artifact whose content hash does not match the recorded build hash is rejected. |

### 16.2 Promotion Model

```
  Build Phase                 Staging Phase              Production Phase
  ───────────                 ─────────────              ────────────────
  web.build                   staging.install            (future: promote)
  ┌─────────────┐             ┌─────────────────┐        ┌───────────────┐
  │ SvelteKit   │             │ Deploy artifact  │        │ Deploy same   │
  │ build in    │──artifact──▶│ to staging LXC   │──same──▶│ artifact to   │
  │ dev container│  (no re-   │ container        │ artifact│ production    │
  │             │   build)    │                  │         │               │
  └─────────────┘             └─────────────────┘        └───────────────┘

  backend.build.wheel         staging.install            (future: promote)
  ┌─────────────┐             ┌─────────────────┐        ┌───────────────┐
  │ python -m   │             │ pip install .whl │        │ pip install   │
  │ build       │──artifact──▶│ in staging LXC   │──same──▶│ same .whl in  │
  │ --wheel     │  (no re-   │ container        │ artifact│ production    │
  │             │   build)    │                  │         │               │
  └─────────────┘             └─────────────────┘        └───────────────┘
```

### 16.3 Guarantees

| ID | Guarantee |
|----|-----------|
| P1 | Promotion never triggers a rebuild. The artifact deployed to production is byte-identical to the artifact validated in staging. |
| P2 | If the staging smoke suite passes against an artifact, that exact artifact is eligible for promotion. A rebuild invalidates eligibility. |
| P3 | The config template deployed alongside the artifact is versioned in the same commit. Config and artifact provenance are linked. |
| P4 | Artifact fingerprinting (SHA-256 of the build output directory or wheel file) is recorded in the govctl JSONL event stream at build time and verified at deployment time. |

### 16.4 Failure Modes

| Failure | Cause | Consequence |
|---------|-------|-------------|
| Artifact hash mismatch at deploy | Build output was modified after `web.build` or `backend.build.wheel` completed | `staging.install` refuses deployment |
| Token embedded in artifact differs from staging config | `webui/.env` was changed after last `web.build`, or config template was edited without rebuild | Staging smoke fails with 401 on all endpoints |
| No artifact present at deploy time | `staging.install` invoked without prior `web.build` or `backend.build.wheel` | Dependency graph prevents execution (`requires` edge) |

### 16.5 Non-Goals

- Image-based promotion (Docker/OCI). The current deployment model uses LXC
  containers with file-level artifact deployment.
- Rollback automation. Rollback is a manual operational procedure (restore
  from LXC snapshot).
- Multi-artifact atomic promotion. Each artifact type (SPA, wheel) is promoted
  independently.

---

## 17. Build Governor Enforcement Responsibilities

**Status:** proposed  
**Date:** 2025-07-27  
**Motivation:** Sections 15 and 16 define invariants and guarantees. This
section defines what the build governor validates, what it refuses, and where
enforcement occurs in the target execution lifecycle.

### 17.1 Enforcement Points

The build governor enforces correctness at three points in target execution:

| Point | Phase | What Runs |
|-------|-------|-----------|
| Pre-build | Before `web.build` or `backend.build.wheel` | Token consistency preflight, template completeness preflight |
| Post-build | After `web.build` or `backend.build.wheel` completes | Artifact fingerprint recording |
| Pre-deploy | Before `staging.install` | Artifact hash verification, token/config consistency check |

### 17.2 New Preflight Checks

These checks extend the preflight framework defined in §6.

| Check Name | Enforces | Validation Logic |
|------------|----------|------------------|
| `token-source-consistent` | T1, T2, T3 | Reads `PUBLIC_API_TOKEN` from `webui/.env` and `api_token` from the staging config template `[web]` section. Fails if values differ. |
| `config-template-complete:<file>` | T4 | Parses the named INI file and verifies the `[web]` section exists with a non-empty `api_token` key. |
| `artifact-hash-recorded:<target>` | A5 | Verifies that the JSONL event log for the current run contains a `build_fingerprint` event for the named target. Required before any target that consumes the build output. |
| `artifact-hash-verified:<artifact-path>` | A5, P1 | Computes SHA-256 of the artifact at the given path and compares against the recorded fingerprint. Fails on mismatch. |

### 17.3 Refusal Semantics

The build governor refuses to proceed (emits `preflight_failed`, skips target)
under these conditions:

| Condition | Preflight That Catches It | Error Category |
|-----------|---------------------------|----------------|
| Frontend and backend token values diverge | `token-source-consistent` | Source divergence |
| Staging config template missing `[web]` section | `config-template-complete:staging/container/photo-ingress.conf` | Template defect |
| Staging config template has empty `api_token` | `config-template-complete:staging/container/photo-ingress.conf` | Template defect |
| `staging.install` invoked but no fingerprint recorded for `web.build` | `artifact-hash-recorded:web.build` | Missing provenance |
| `staging.install` invoked but artifact hash does not match recorded fingerprint | `artifact-hash-verified:webui/build/` | Artifact tamper |

### 17.4 JSONL Event Extensions

New event types for the JSONL stream (extends §8):

```jsonc
// Emitted after web.build or backend.build.wheel completes successfully
{"event":"build_fingerprint","target":"web.build","sha256":"abc123...","artifact_path":"webui/build/","timestamp":"..."}

// Emitted when artifact hash verification passes at deploy time
{"event":"artifact_verified","target":"staging.install","artifact":"web.build","expected_sha256":"abc123...","actual_sha256":"abc123...","timestamp":"..."}

// Emitted when artifact hash verification fails
{"event":"artifact_rejected","target":"staging.install","artifact":"web.build","expected_sha256":"abc123...","actual_sha256":"def456...","timestamp":"..."}
```

### 17.5 Target Manifest Additions

The following preflight declarations would be added to the targets defined in §7:

```yaml
  web.build:
    preflight:
      - container-running:dev-photo-ingress
      - stack-drift-free:webui
      - token-source-consistent                              # new
      - config-template-complete:staging/container/photo-ingress.conf  # new

  staging.install:
    preflight:
      - container-running:staging-photo-ingress
      - bridge-network:br-staging
      - artifact-hash-recorded:web.build                     # new
      - artifact-hash-recorded:backend.build.wheel           # new
      - artifact-hash-verified:webui/build/                  # new
      - artifact-hash-verified:dist/*.whl                    # new
      - token-source-consistent                              # new
```

### 17.6 What The Build Governor Does Not Enforce

| Concern | Reason |
|---------|--------|
| Runtime token validation correctness | Responsibility of `api/auth.py`; verified by staging smoke tests, not build preflights |
| Token rotation | Operational procedure, not a build concern |
| Secret storage security | Out of scope (see §15.4) |
| Network-level auth (TLS, mTLS) | Infrastructure concern, not build orchestration |
| Correctness of test assertions | Tests validate behavior; the governor validates preconditions |
| Container image integrity | The LXC container is managed by devctl/stagingctl, not by govctl directly |

---

## 18. Preflight Execution Context Contract

**Status:** proposed  
**Date:** 2026-04-08  
**Motivation:** Chunk 4 of the staging-token-hardening roadmap failed because
the preflight execution context was under-specified. This section formalizes
the contract so that preflights are deterministically implementable and
verifiable in isolation.

### 18.1 Working Directory

All preflight checks execute with the working directory set to the repository
root. The repository root is resolved at `govctl` startup as
`GOVCTL_PREFLIGHTS_PROJECT_ROOT` (the parent of `dev/bin/`). This directory is
the same as `GOVCTL_EXEC_PROJECT_ROOT` used for target command execution.

Preflight implementations must not assume or change the working directory.

### 18.2 Path Resolution

Preflight check arguments that contain file paths (e.g.,
`config-template-complete:staging/container/photo-ingress.conf`) are resolved
as follows:

| Path form | Resolution |
|-----------|------------|
| Relative (no leading `/`) | Prepend `$GOVCTL_PREFLIGHTS_PROJECT_ROOT/` |
| Absolute (leading `/`) | Use as-is |

The `token-source-consistent` check reads two fixed paths relative to the
project root: `webui/.env` and `staging/container/photo-ingress.conf`. These
paths are intrinsic to the check definition, not supplied as arguments.

### 18.3 Evaluation Order and Short-Circuit Behavior

Preflights declared on a target are evaluated in manifest-declared order
(array index 0 first). The following rules apply:

| Scope | Behavior |
|-------|----------|
| Within a target | All declared preflights are evaluated. There is no early exit on first preflight failure within a single target. Every preflight emits either a `preflight_passed` or `preflight_failed` JSONL event. |
| Across targets | If any preflight for a target fails, the target is marked skipped. In fail-fast mode (the default, without `--continue-on-error`), the entire run stops after the first target whose preflights fail. In continue mode, subsequent independent targets proceed. |

Consequence for verification: a `govctl check <target>` invocation always
produces one JSONL event per declared preflight, regardless of pass or fail.
Verification scripts must inspect per-check events, not the overall exit code,
to determine whether a specific preflight passed.

### 18.4 Isolation Requirement

New preflight checks must be verifiable in isolation from pre-existing
checks on the same target. Specifically:

- A verification that targets a single check (e.g., `token-source-consistent`)
must not depend on the pass/fail state of unrelated checks on the same target
(e.g., `container-running:dev-photo-ingress`).
- `govctl check <target> --format json` emits individual `preflight_passed`
and `preflight_failed` events. Verification scripts must filter by check name,
not by aggregate outcome.

### 18.5 JSONL Session Identity

A "current session" for JSONL inspection is a single `govctl` invocation.
Each invocation generates a unique run ID (`<YYYYMMDD>T<HHMMSS>-<6-char-hex>`)
and writes all events to `artifacts/govctl/run-<run-id>/events.jsonl`.
Preflight events within that file belong to exactly one session. There is no
cross-invocation session concept.

---

## 19. Token Placeholder Semantics

**Status:** proposed  
**Date:** 2026-04-08  
**Motivation:** The staging config template (`staging/container/photo-ingress.conf`)
contains the literal value `inspect-chunk3-token` — a legacy test artifact.
The template already uses the pattern `STAGING_CLIENT_ID_PLACEHOLDER` for
credentials that must be replaced before use. This section extends that
pattern to API tokens and defines how preflights treat placeholders.

### 19.1 Decision

Accepted. The concrete token value `inspect-chunk3-token` in the staging
config template is replaced with the placeholder `API_TOKEN_PLACEHOLDER`.
The same replacement is applied to `webui/.env` (`PUBLIC_API_TOKEN`).

### 19.2 Placeholder Convention

A placeholder is a value matching the pattern `*_PLACEHOLDER` (suffix match,
case-sensitive). Placeholders signal that the value must be substituted with
a real credential before the artifact is used in a running environment.

### 19.3 Consistency with Invariants T1–T6

| Invariant | Impact |
|-----------|--------|
| T1 | The canonical source (`[web] api_token`) contains a placeholder in the template. The placeholder is not a token — it is a substitution marker. T1 holds because the authoritative value is whatever occupies this field after substitution. |
| T2 | `webui/.env` `PUBLIC_API_TOKEN` must be byte-identical to the config template value. When both contain `API_TOKEN_PLACEHOLDER`, they are consistent. T2 holds. |
| T3 | No impact. The backend reads the INI at runtime after substitution. |
| T4 | The `[web]` section exists and `api_token` is defined (non-empty). T4 holds. The placeholder is a defined value. |
| T5 | Placeholder strings are not secret values. However, preflights must not distinguish between placeholders and real tokens in their output — the redaction rule (T5) applies uniformly. |
| T6 | Constant-time comparison applies to runtime token validation. Preflight comparison of source files also uses constant-time comparison per T6. No change. |

### 19.4 Preflight Treatment of Placeholders

| Check | Placeholder behavior |
|-------|----------------------|
| `token-source-consistent` | Compares the values in `webui/.env` and the config template. If both contain `API_TOKEN_PLACEHOLDER`, the check passes (values are byte-identical). The check does not distinguish placeholders from real tokens. |
| `config-template-complete` | Verifies `[web]` section exists and `api_token` is non-empty. `API_TOKEN_PLACEHOLDER` satisfies non-empty. The check passes. |

### 19.5 Build-Time vs Template-Time Distinction

Placeholders are permitted in version-controlled template files. They are
forbidden at build time in the following sense:

- `govctl` preflights validate source consistency and template completeness.
  Placeholders satisfy both checks.
- The staging smoke suite (`stagingctl smoke`) validates runtime behavior.
  An API endpoint returning 401 for all requests because the token is a
  literal placeholder will fail the smoke suite. This is the intended
  enforcement boundary — smoke, not preflight.
- Preflights do not reject placeholders. Smoke tests do. This separation
  preserves the principle that preflights validate structure, not operational
  readiness.

### 19.6 Affected Files

| File | Field | Old value | New value |
|------|-------|-----------|-----------|
| `staging/container/photo-ingress.conf` | `[web] api_token` | `inspect-chunk3-token` | `API_TOKEN_PLACEHOLDER` |
| `webui/.env` | `PUBLIC_API_TOKEN` | `inspect-chunk3-token` | `API_TOKEN_PLACEHOLDER` |

These file changes are implementation actions for the hardening roadmap,
not part of this design patch. This section defines the semantics only.
