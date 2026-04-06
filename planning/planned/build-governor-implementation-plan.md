# Build Governor — Chunk-Wise Implementation Plan

**Status:** planned  
**Date:** 2026-04-06  
**Design reference:** [build-governor-design.md](../../design/infra/build-governor-design.md)  
**Companion design:** [devctl-update-architecture.md](../../design/infra/devctl-update-architecture.md)  
**Constraint:** System must remain operational after each chunk.  
**Constraint:** No chunk may break existing devctl, stagingctl, metricsctl, or MCP flows.  
**Constraint:** Design-only — no Phase 2 features, endpoints, or rewrites in Phase 1.

---

## Phase Summary

| Phase | Title | Chunks | Purpose |
|-------|-------|--------|---------|
| 1 | Build Governor Introduction | 1–7 | Implement govctl as designed: manifest, graph resolver, preflight checks, executor, JSONL output, MCP integration |
| 2 | Command Surface Refinement | 8–11 | Targeted improvements to devctl, stagingctl, and build-metrics-dashboard that reduce orchestration-execution coupling |

Phase 2 is conditional — justified by the command surface assessment in §A
below. Phase 1 is self-contained and delivers a usable governor without
requiring Phase 2.

---

## Command Surface Assessment

### §A. Adequacy Review

Before chunking, each underlying tool was assessed for whether its current
interface is adequate as a delegation target for the governor.

#### devctl — Partially adequate

`devctl` is the most frequently delegated-to tool. Its interface works for
govctl in Phase 1, but has three structural limitations:

1. **`ensure-stack-ready` is monolithic.** It bundles SvelteKit/Vite
   consistency validation, Node version checking, source syncing, and drift
   remediation into one function. govctl's preflight checks (`node-version-match`,
   `stack-drift-free:*`) overlap with validations that `ensure-stack-ready`
   performs internally. In Phase 1 this means redundant checks (govctl runs
   preflight, then devctl re-validates the same conditions). The overhead is
   tolerable but not ideal.

2. **The regression gate is hardcoded.** `cmd_update()` internally dispatches
   `test-web-typecheck` → `test-metrics-dashboard-typecheck` → `test-web-unit`
   → pytest. An external orchestrator cannot run a partial gate or reorder
   steps. This does not block Phase 1 (govctl does not wrap `devctl update`)
   but limits future composability.

3. **No `--skip-ready` or `--skip-lock` flags.** When govctl has already
   verified preconditions and holds the lock, devctl still re-verifies and
   re-acquires. The `DEVCTL_GLOBAL_LOCK_HELD` reentry guard prevents deadlock
   but not the redundant verification.

#### stagingctl — Partially adequate

1. **`install` builds the wheel internally if none is provided.** This is
   tolerable in Phase 1: govctl declares `staging.install` depends on
   `backend.build.wheel`, which ensures `dist/*.whl` exists. stagingctl's
   fallback `python -m build` is never reached because the wheel is already
   present.

2. **Evidence is coupled with smoke execution.** The `smoke` and `smoke-live`
   commands produce JSONL assertions embedded in their execution. There is no
   way to request "run assertions and emit JSONL" without running the entire
   smoke flow. This does not block Phase 1 (govctl captures the exit code and
   tees logs) but limits structured result exposure.

3. **Config substitution is implicit.** `STAGING_CLIENT_ID` and related env
   vars are silently compared against container state. govctl has no visibility
   into config drift. Not blocking for Phase 1.

#### build-metrics-dashboard — Inadequate as-is, tolerable for Phase 1

1. **Hardcoded `devctl ensure-stack-ready dashboard` call** with no skip flag.
   When govctl runs `dev.stack-ready.dashboard` as a dependency and then
   delegates to `build-metrics-dashboard`, the stack readiness check runs
   twice. This is the most significant redundancy in Phase 1.

2. **Hardcoded output path** (`metrics/output/dashboard/static/`). Not relevant
   for Phase 1 but limits future CI integration.

3. **No structured build-success signal** beyond the exit code and the
   `.build-stamp` file. Phase 1 govctl uses exit code + timing; the stamp file
   serves as a secondary verification artifact.

#### metricsctl — Adequate

metricsctl is the best-designed tool for external orchestration:
- Most commands are isolated, thin wrappers over `metrics.runner.*` modules.
- JSON output on all commands.
- Only `generate-dashboard` has an implicit devctl dependency (documented in
  code, not in help text).
- Lock acquisition is limited to `generate-dashboard`.

One issue: `generate-dashboard` internally calls `devctl ensure-stack-ready
dashboard` via `_devctl_dashboard_drift_preflight()`. If govctl has already
ensured dashboard readiness, this is redundant. Tolerable in Phase 1.

#### lib/container-common.sh — Reusable

All functions (`nf_log_info`, `nf_log_ok`, `nf_log_warn`, `nf_log_fail`,
`nf_require_container_exists`, `nf_require_container_running`) are generic.
govctl can source this library directly.

**Caveat:** `nf_log_fail` calls `exit 1`. govctl must use it only in contexts
where hard-abort is acceptable, or define its own soft-fail variant.

### §B. Phase 2 Justification

Phase 2 is justified based on three concrete coupling issues:

1. **Redundant drift validation.** govctl preflight checks and
   `devctl ensure-stack-ready` duplicate the same container/drift validations.
   Phase 2 splits `ensure-stack-ready` so govctl can call individual steps.

2. **build-metrics-dashboard is not composable.** It hardcodes its own
   precondition check and output path. Phase 2 adds skip/override flags.

3. **metricsctl generate-dashboard has an implicit dependency.** Phase 2
   adds a `--skip-drift-preflight` flag so govctl can manage drift externally.

These refinements are incremental — no rewrites, no interface breakage.

---

## Design Consistency Notes

The following inconsistencies were identified between the design document and
the actual repository state. The implementation plan corrects for these.

1. **`backend.build.wheel` preflight.** The design declares
   `preflight: [venv-exists:/opt/ingress]`, but `python -m build` runs on the
   host, not in the container. The venv at `/opt/ingress` is a container-local
   path. The correct preflight is either empty (host build needs only the
   host Python) or `host-python-available` (verify `python3 -m build` is
   available). The manifest in Chunk 3 corrects this.

2. **`staging.install` wheel dependency.** The design declares
   `requires: [backend.build.wheel]`, implying govctl always pre-builds. This
   is correct — stagingctl's fallback build is never reached — but the design
   does not note this interaction. No correction needed; just documented here.

3. **Lock redundancy.** The design says govctl acquires locks for
   `lock: true` targets and sets `DEVCTL_GLOBAL_LOCK_HELD=1`. But several
   delegated commands (`devctl ensure-stack-ready`, `metricsctl
   generate-dashboard`) also acquire the lock internally. The reentry guard
   prevents deadlock, but the double-acquire is visible in lock wait times.
   Phase 1 accepts this. Phase 2 addresses it.

---

## Phase 1 — Build Governor Introduction

Phase 1 delivers a complete, usable `govctl` as described in the design
document. It wraps existing tools without modifying them.

### Phase 1 Overview

| Chunk | Title | Risk | Depends On |
|-------|-------|------|-----------|
| 1 | Manifest schema and parser helper | Low | — |
| 2 | Graph resolver and topological sort | Low | 1 |
| 3 | Target manifest (govctl-targets.yaml) | Low | 1, 2 |
| 4 | Preflight check framework | Medium | 1 |
| 5 | Executor, lock integration, and JSONL emitter | Medium | 1, 2, 4 |
| 6 | govctl CLI shell, inspect commands, and UX | Medium | 1–5 |
| 7 | MCP model integration and artifact housekeeping | Low | 6 |

---

### Chunk 1: Manifest Schema and Parser Helper

#### Intent

Establish the manifest format as a machine-verifiable contract and provide a
reliable mechanism for Bash to consume YAML.

#### Scope

**Included:**
- Define the YAML schema for `govctl-targets.yaml` as a Python validation
  module (`dev/lib/govctl_manifest.py` or inline helper).
- The helper reads `govctl-targets.yaml`, validates it against the schema, and
  emits a normalized JSON representation to stdout.
- Validation covers: required keys (`version`, `targets`), per-target required
  fields (`description`, `command`), type checks on `lock`, `timeout_seconds`,
  `requires`, `preflight`, and group expansion.
- Cycle detection in `requires` edges (fail-fast at parse time).

**Excluded:**
- No govctl script yet.
- No graph resolution beyond cycle detection.
- No preflight logic.

#### Inputs and Outputs

- **Input:** `dev/govctl-targets.yaml` (created in Chunk 3, but the parser is
  testable against fixture YAML before Chunk 3 lands).
- **Output:** JSON to stdout representing the normalized manifest. Schema
  errors produce non-zero exit and a human-readable error message to stderr.

#### Correctness Validation

- Unit test: valid YAML fixtures produce expected JSON output.
- Unit test: YAML with missing required fields, type errors, or circular
  `requires` edges produce non-zero exit and descriptive error messages.
- Idempotency: same YAML produces identical JSON across invocations.

#### Why Independently Committable

The parser is a self-contained utility with no side effects. It can be tested
with fixture YAML files. No existing tool is modified. govctl does not exist
yet, so there is no integration risk.

---

### Chunk 2: Graph Resolver and Topological Sort

#### Intent

Implement the dependency graph resolver that takes a set of requested targets
(or groups), expands groups, and produces a topologically sorted execution
order.

#### Scope

**Included:**
- A Bash function (or small Python helper co-located with the Chunk 1 parser)
  that accepts requested target names and the parsed manifest JSON, and emits
  the resolved execution order as a newline-delimited list.
- Group expansion: if a requested name matches a group, expand to its member
  targets recursively (groups may reference other groups as per the design).
- Transitive dependency inclusion: if target A requires target B, B is
  included even if not explicitly requested.
- Duplicate elimination: each target appears exactly once in the output.

**Excluded:**
- No parallel scheduling. The resolver emits a serial topological order.
- No execution logic.

#### Inputs and Outputs

- **Input:** Parsed manifest JSON (from Chunk 1 helper) and a list of
  requested target/group names.
- **Output:** Newline-delimited list of target names in execution order,
  printed to stdout. Non-zero exit if a requested name is unknown.

#### Dependencies

- Chunk 1 (manifest parser outputs the JSON this resolver consumes).

#### Correctness Validation

- Unit test: requesting a group resolves to expected targets in correct order.
- Unit test: diamond dependencies (A→B, A→C, B→D, C→D) produce D before B and
  C, and B/C before A — single occurrence of D.
- Unit test: requesting an unknown target name exits non-zero with clear error.
- Unit test: requesting a target with no dependencies returns just that target.

#### Why Independently Committable

The resolver is a pure function with deterministic output. It depends on
Chunk 1's JSON format but has no side effects. Testable with fixture JSON.

---

### Chunk 3: Target Manifest (govctl-targets.yaml)

#### Intent

Author the canonical target manifest that declares all build/test/deploy
targets, their dependencies, preflight checks, lock requirements, and group
definitions. This is the authoritative source of truth for govctl's behavior.

#### Scope

**Included:**
- Create `dev/govctl-targets.yaml` with all targets from the design document
  §7, corrected for the consistency notes above:
  - `backend.build.wheel` preflight corrected to empty list (host build, no
    container precondition).
  - All other targets preserved as designed.
- All seven groups from the design.
- Default `lock: false` and `timeout_seconds: 300`.

**Excluded:**
- No runtime behavior. The manifest is a static file.
- No validation tooling (that is Chunk 1).

#### Inputs and Outputs

- **Input:** Design document §7 (corrected per consistency notes).
- **Output:** `dev/govctl-targets.yaml` — a YAML file parseable by Chunk 1.

#### Dependencies

- Conceptually shaped by Chunks 1 and 2 (schema and resolver), but the file
  itself has no runtime dependency. Can be committed in any order relative to
  Chunks 1–2.

#### Correctness Validation

- Chunk 1's parser helper validates the manifest against schema (run after
  both Chunk 1 and Chunk 3 are committed).
- Chunk 2's resolver produces a valid topological order for every group
  (integration test after Chunks 1–3 are committed).
- Manual review: every target's `command` field matches the actual script path
  and syntax in the repository.

#### Why Independently Committable

The manifest is a static YAML file. It has no executable effect until govctl
reads it. Committing it separately allows review of the target definitions
before any runtime logic exists.

---

### Chunk 4: Preflight Check Framework

#### Intent

Implement the reusable, named preflight checks described in the design §6.
Each check is a callable predicate that returns pass/fail with a reason string.

#### Scope

**Included:**
- A library of Bash functions, one per built-in check name, sourced by govctl.
  Location: `dev/lib/govctl-preflights.sh` (or embedded in govctl; decided at
  implementation time).
- Checks implemented:
  - `container-exists:<name>`
  - `container-running:<name>`
  - `snapshot-exists:<container>/<snap>`
  - `cache-mounts-active`
  - `stack-drift-free:<stack>`
  - `node-version-match`
  - `venv-exists:<path>`
  - `wheel-exists`
  - `bridge-network:<bridge>`
- Each function accepts the parameterized part (after the colon) and returns
  exit 0 (pass) or exit 1 (fail). On failure, it prints a one-line reason to
  stdout.
- A dispatch function `govctl_run_preflight <check-string>` parses the check
  name and routes to the correct function.

**Excluded:**
- No JSONL emission (that is Chunk 5).
- No integration with the executor.
- No `govctl check` command (that is Chunk 6).

#### Inputs and Outputs

- **Input:** A single check string (e.g., `container-running:dev-photo-ingress`).
- **Output:** Exit code 0 or 1. On failure, a reason string on stdout.

#### Dependencies

- Sources `lib/container-common.sh` for `nf_require_container_exists` and
  `nf_require_container_running` as internal helpers (but wraps them to
  avoid the hard `exit 1` from `nf_log_fail`).

#### Correctness Validation

- Unit test: each check against a known-good environment returns 0.
- Unit test: each check against a deliberately broken condition (container
  stopped, snapshot deleted, drift injected) returns 1 with a descriptive
  reason string.
- Contract: check functions are side-effect-free (read-only queries).
- The `container-running` and `container-exists` checks must not start or
  create containers.

#### Why Independently Committable

The preflight library is a self-contained set of functions with no side effects.
It can be tested independently with a running LXC environment. No existing
tools are modified.

---

### Chunk 5: Executor, Lock Integration, and JSONL Emitter

#### Intent

Implement the core execution engine: iterate over the resolved target list,
run preflight checks, acquire locks, delegate to commands, capture results,
and emit JSONL events.

#### Scope

**Included:**
- The `govctl_execute()` function that:
  1. Creates the run directory: `artifacts/govctl/run-<timestamp>/`.
  2. Opens a JSONL event file for the run.
  3. Emits `run_started` event.
  4. For each target in resolved order:
     a. Run all declared preflight checks (via Chunk 4 framework).
     b. Emit `preflight_passed` or `preflight_failed` events.
     c. On preflight failure: emit `target_skipped`, continue or abort per
        `--continue-on-error`.
     d. Acquire global repo lock if `lock: true`, setting
        `DEVCTL_GLOBAL_LOCK_HELD=1`.
     e. Emit `target_started` event.
     f. Execute command via `bash -c`, piping stdout/stderr through `tee` to
        both the terminal and `<run-dir>/<target-name>.log`.
     g. Capture exit code and wall-clock duration.
     h. Release lock.
     i. Emit `target_passed` or `target_failed` event.
     j. On failure without `--continue-on-error`: skip remaining targets
        (emit `target_skipped` for each), break.
  5. Emit `run_finished` event with totals.
  6. Write `summary.json` to run directory.
- Timeout enforcement via `timeout(1)` wrapping the `bash -c` invocation.
  Timeout produces a `target_failed` event with `"reason": "timeout"`.
- Exit code: 0 if all targets passed, non-zero otherwise.

**Excluded:**
- No CLI argument parsing (that is Chunk 6).
- No `--parallel` support.
- No `--json` (suppress human output) mode — that is a presentation concern
  in Chunk 6.

#### Inputs and Outputs

- **Input:** Resolved target list (from Chunk 2), parsed manifest JSON (from
  Chunk 1), flags (`continue_on_error`, `log_dir`).
- **Output:**
  - JSONL event file at `artifacts/govctl/run-<ts>/events.jsonl`.
  - Per-target log files at `artifacts/govctl/run-<ts>/<target-name>.log`.
  - Summary JSON at `artifacts/govctl/run-<ts>/summary.json`.
  - Human-readable log passthrough to terminal (with target header/footer
    banners).

#### Dependencies

- Chunk 1 (manifest parser for target metadata).
- Chunk 2 (graph resolver for execution order).
- Chunk 4 (preflight check dispatch).

#### Correctness Validation

- Integration test: execute a known-passing target (e.g., `backend.test.unit`).
  Verify: events.jsonl contains `run_started`, `target_started`,
  `target_passed`, `run_finished` in correct order. summary.json shows
  `passed: 1, failed: 0`.
- Integration test: execute a known-failing target. Verify: events.jsonl
  contains `target_failed` with non-zero exit code. summary.json reflects
  failure.
- Integration test: execute a target with `lock: true`. Verify:
  `DEVCTL_GLOBAL_LOCK_HELD` is set in the command's environment.
- Integration test: execute a target with a preflight that fails. Verify:
  `preflight_failed` and `target_skipped` events emitted. Target command
  never runs.
- Determinism: re-running the same targets produces structurally identical
  JSONL (same event types, same ordering), differing only in timestamps and
  durations.

#### Why Independently Committable

The executor is the integration point for Chunks 1, 2, and 4. It introduces
no external dependencies beyond those chunks. It creates new artifacts
(`artifacts/govctl/`) without modifying existing files. Existing tools are
invoked as black-box commands.

---

### Chunk 6: govctl CLI Shell, Inspect Commands, and UX

#### Intent

Wire the executor into a user-facing CLI with argument parsing, the four
command forms (`<target>`, `list`, `check`, `graph`), and presentation polish.

#### Scope

**Included:**
- Create `dev/bin/govctl` as the entry point script.
- Source `lib/container-common.sh` and `dev/lib/govctl-preflights.sh`.
- Self-bootstrap check on first invocation: verify `python3`, `lxc`, `flock`,
  `timeout` are available; fail with clear message if not.
- Argument parsing:
  - `govctl <target|group> [<target|group> ...] [--dry-run] [--continue-on-error] [--json] [--log-dir <path>]`
  - `govctl list [--format human|json]`
  - `govctl check [<target|group>] [--format human|json]`
  - `govctl graph [<target|group>] [--format human|dot]`
- Run targets: parse args → load manifest (Chunk 1) → resolve graph (Chunk 2)
  → execute (Chunk 5).
- `--dry-run`: resolve graph, print execution plan, exit 0 without executing.
- `--json`: suppress human log passthrough; emit only JSONL to stdout.
- `list`: load manifest, print all targets and groups with descriptions.
  `--format json` emits JSON array.
- `check`: resolve requested targets, run only preflight checks (Chunk 4),
  report results. `--format json` emits structured pass/fail.
- `graph`: resolve requested targets, print dependency edges. `--format dot`
  emits Graphviz dot notation.
- Target header/footer banners:
  ```
  ──── <target-name> ─────────
  ... (tool output) ...
  ──── <target-name>: PASSED (Xs) ─────
  ```
- Run summary banner at end of execution.

**Excluded:**
- No `--parallel` support.
- No `.gitignore` update (that is Chunk 7).
- No MCP model changes (that is Chunk 7).

#### Inputs and Outputs

- **Input:** CLI arguments.
- **Output:** Human-readable or JSON output depending on mode. Side effects:
  JSONL and log files in `artifacts/govctl/`.

#### Dependencies

- Chunks 1–5 (all prior components).

#### Correctness Validation

- Smoke test: `govctl list` produces a list that includes all targets from
  `govctl-targets.yaml`.
- Smoke test: `govctl backend.test.unit --dry-run` prints the execution plan
  without running any commands.
- Smoke test: `govctl check dev.ensure-running --format json` emits valid JSON
  with preflight results.
- Smoke test: `govctl graph test.all --format dot` emits valid dot notation
  that `dot -Tpng` can render.
- Integration test: `govctl backend.test.unit` runs pytest and produces
  `artifacts/govctl/run-*/summary.json` with `passed: 1`.
- UX verification: target banners appear around delegated tool output;
  summary banner appears at end with correct counts.

#### Why Independently Committable

This chunk assembles the CLI from previously-committed components. The script
is new (`dev/bin/govctl`). No existing tools are modified. The CLI is the
first user-visible artifact; once committed, `govctl` is operational.

---

### Chunk 7: MCP Model Integration and Artifact Housekeeping

#### Intent

Register govctl in the MCP task model and ensure artifact paths are properly
excluded from version control.

#### Scope

**Included:**
- Update `.mcp/model.json`:
  - Add `govctl` to the `devctl.commands` section (or a new `govctl` section).
  - Add MCP task mappings that route through govctl where beneficial:
    - `backend.test.unit` → `./dev/bin/govctl backend.test.unit --json`
    - `web.test.unit` → `./dev/bin/govctl web.test.unit --json`
    - Preserve existing direct-delegation mappings as alternatives.
  - Add `govctl-targets.yaml` to the MCP model's awareness (new entry under
    a `manifests` or `config-files` key if the schema supports it).
- Update `.gitignore`:
  - Add `artifacts/govctl/` to exclude ephemeral run data.
- Update `AGENTS.md`:
  - Add govctl to the list of devctl commands and usage examples.
  - Add a govctl usage example showing `--json` mode for agent consumption.

**Excluded:**
- No changes to existing MCP task mappings that don't benefit from govctl
  routing. The integration is opt-in.
- No changes to `mcp_server.py`. The MCP server reads model.json; govctl
  integration is purely declarative.

#### Inputs and Outputs

- **Input:** Current `.mcp/model.json`, `.gitignore`, `AGENTS.md`.
- **Output:** Updated versions of those files with govctl entries.

#### Dependencies

- Chunk 6 (govctl must exist before MCP can route to it).

#### Correctness Validation

- `.mcp/model.json` remains valid JSON after edits.
- MCP task `backend.test.unit` routes through govctl and produces structured
  JSONL output.
- `artifacts/govctl/` is excluded by `.gitignore` (verify with
  `git status` after a govctl run produces artifacts).
- `AGENTS.md` references are accurate (govctl path matches `dev/bin/govctl`).

#### Why Independently Committable

These are configuration and documentation updates. No runtime behavior changes
to existing tools. The MCP routing is opt-in (old mappings are preserved).

---

## Phase 2 — Command Surface Refinement

Phase 2 addresses the coupling issues identified in §A. Each chunk is an
incremental, non-breaking improvement to an existing tool. Phase 2 is
independent of Phase 1 in the sense that Phase 1 works without it — but
Phase 2 reduces redundant work and improves composability.

### Phase 2 Overview

| Chunk | Title | Risk | Depends On |
|-------|-------|------|-----------|
| 8 | devctl ensure-stack-ready: expose skip flags | Medium | Phase 1 |
| 9 | build-metrics-dashboard: composability flags | Low | Phase 1 |
| 10 | metricsctl generate-dashboard: skip drift preflight | Low | Phase 1 |
| 11 | govctl manifest update for refined surfaces | Low | 8, 9, 10 |

---

### Chunk 8: devctl ensure-stack-ready — Expose Skip Flags

#### Intent

Make `devctl ensure-stack-ready` composable by allowing an external
orchestrator to skip validation passes that it has already performed.

#### What Is Suboptimal

`ensure-stack-ready` bundles four distinct operations into one call:
1. SvelteKit/Vite major consistency validation (`assert_web_stack_major_consistency`)
2. Node version verification (`.node-version` vs container)
3. Source sync (tar push to container)
4. Manifest drift check and remediation (`npm ci` on hash mismatch)

An orchestrator that has already run `govctl check` (which verifies node version
and drift state) must still pay for steps 1–2 again when delegating to devctl.

#### Proposed Improvement

Add environment-variable-based skip flags (not CLI flags, to avoid breaking
the existing subcommand interface):
- `DEVCTL_SKIP_CONSISTENCY_CHECK=1` — skip step 1.
- `DEVCTL_SKIP_NODE_VERSION_CHECK=1` — skip step 2.

Source sync (step 3) and drift remediation (step 4) are never skipped — they
are the core purpose of the command.

#### Scope Boundary

- Only `ensure-stack-ready` is modified.
- No changes to any other devctl subcommand.
- No changes to the function's external contract (same arguments, same exit
  code semantics).
- Env vars default to unset (no skip), preserving backward compatibility.

#### Correctness Validation

- Existing devctl tests pass without any skip env vars set.
- With `DEVCTL_SKIP_CONSISTENCY_CHECK=1`, the consistency assertion is not
  run (verified by log output absence or test instrumentation).
- If consistency is genuinely broken and the skip flag is set, the function
  still succeeds (the skip is a trust signal from the orchestrator).

#### Why Independently Committable

Additive change to one function. Default behavior unchanged. No external
contract breakage.

---

### Chunk 9: build-metrics-dashboard — Composability Flags

#### Intent

Allow an external orchestrator to skip the embedded `devctl ensure-stack-ready`
call and override the output path.

#### What Is Suboptimal

`build-metrics-dashboard` always calls `devctl ensure-stack-ready dashboard`
before building. When govctl has already ensured readiness via the
`dev.stack-ready.dashboard` target, this is redundant. Additionally, the
output path is hardcoded, limiting flexibility.

#### Proposed Improvement

- `--skip-ensure-ready` flag: bypass the `devctl ensure-stack-ready dashboard`
  call. The script proceeds directly to `npm run build`.
- `--output-dir <path>` flag: override `HOST_OUTPUT_DIR`.
- Both flags are optional with backward-compatible defaults.

#### Scope Boundary

- Only `dev/bin/build-metrics-dashboard` is modified.
- No changes to devctl, metricsctl, or any other script.
- The build stamp logic is unchanged.

#### Correctness Validation

- Without new flags: behavior is identical to current.
- With `--skip-ensure-ready`: script skips the devctl call and proceeds to
  `npm run build`. If stack is not ready, the build fails (expected — the
  orchestrator is responsible for readiness).
- With `--output-dir /tmp/test-output`: build output appears in the specified
  directory. Build stamp is written relative to the output directory.

#### Why Independently Committable

Additive flags to one script. Default behavior unchanged. No external contract
breakage.

---

### Chunk 10: metricsctl generate-dashboard — Skip Drift Preflight

#### Intent

Allow an external orchestrator to suppress the implicit `devctl
ensure-stack-ready dashboard` call inside `metricsctl generate-dashboard`.

#### What Is Suboptimal

`generate-dashboard` internally calls `_devctl_dashboard_drift_preflight()`,
which invokes `devctl ensure-stack-ready dashboard`. When govctl has already
ensured readiness, this is a redundant container round-trip.

#### Proposed Improvement

- `--skip-drift-preflight` CLI flag on `generate-dashboard`: skip the
  `_devctl_dashboard_drift_preflight()` call.
- Backward-compatible: without the flag, behavior is unchanged.

#### Scope Boundary

- Only `metricsctl`'s `generate-dashboard` subcommand is modified.
- No changes to other metricsctl subcommands.
- No changes to `_devctl_dashboard_drift_preflight()` itself (it remains
  available for direct callers).

#### Correctness Validation

- Without the flag: identical behavior.
- With `--skip-drift-preflight`: the devctl call does not occur. If the
  dashboard stack has actual drift, the build may fail (expected — orchestrator
  is responsible).
- metricsctl's JSON output schema for `generate-dashboard` is unchanged.

#### Why Independently Committable

Additive flag to one subcommand. Default behavior unchanged. JSON output
contract unchanged.

---

### Chunk 11: govctl Manifest Update for Refined Surfaces

#### Intent

Update `govctl-targets.yaml` to leverage the skip flags introduced in
Chunks 8–10, reducing redundant work in orchestrated runs.

#### Scope

**Included:**
- Modify target commands to pass skip flags where govctl preflight checks
  already cover the same ground:
  - `dev.stack-ready.webui` and `dev.stack-ready.dashboard`: set
    `DEVCTL_SKIP_CONSISTENCY_CHECK=1` and `DEVCTL_SKIP_NODE_VERSION_CHECK=1`
    in the command environment (govctl preflight checks `node-version-match`
    have already verified these).
  - `metrics.build.dashboard`: change command to
    `./dev/bin/build-metrics-dashboard --skip-ensure-ready` (the
    `dev.stack-ready.dashboard` dependency has already ensured readiness).
  - `metrics.generate.dashboard`: change command to
    `./metricsctl generate-dashboard --skip-drift-preflight` (the
    `dev.stack-ready.dashboard` dependency has already ensured readiness).

**Excluded:**
- No changes to govctl itself (executor, preflights, CLI).
- No changes to any script. Only the manifest commands change.

#### Dependencies

- Chunks 8, 9, 10 (the skip flags must exist before the manifest references them).

#### Correctness Validation

- `govctl metrics.build.dashboard` completes successfully with the
  `--skip-ensure-ready` flag. Dashboard build stamp is written.
- `govctl metrics.generate.dashboard` completes successfully with
  `--skip-drift-preflight`. Dashboard generation succeeds.
- Full `govctl all` run completes with no regressions. summary.json shows
  all targets passed.
- govctl without Phase 2 flags still works (the targets fall back to default
  behavior if flags are not recognized — though they should be, since Chunks
  8–10 precede this chunk).

#### Why Independently Committable

Only `dev/govctl-targets.yaml` is modified. The skip flags are already
available from Chunks 8–10. If this chunk is reverted, govctl falls back to
Phase 1 manifest behavior (redundant but correct).

---

## Dependency Graph

```
Phase 1:
  Chunk 1 ──┬──→ Chunk 2 ──┐
             │               │
             ├──→ Chunk 3    ├──→ Chunk 5 ──→ Chunk 6 ──→ Chunk 7
             │               │
             └──→ Chunk 4 ──┘

Phase 2 (all depend on Phase 1 completion):
  Chunk 8 ──┐
  Chunk 9 ──┼──→ Chunk 11
  Chunk 10 ─┘
```

Chunks 1, 3, and 4 have no mutual dependencies and could theoretically be
committed in parallel. Chunks 8, 9, and 10 are independent of each other.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| YAML parser fragility (Bash ↔ Python bridge) | Medium | Medium | Chunk 1 uses Python yaml.safe_load; tested with fixtures before integration |
| Lock contention between govctl and nested tools | Low | Medium | DEVCTL_GLOBAL_LOCK_HELD reentry guard already exists; Phase 2 reduces lock nesting |
| Preflight checks false-positive (check passes but tool fails) | Low | Low | Preflight checks read the same state tools read; divergence is a tool bug |
| `timeout(1)` kills background LXC processes | Low | Medium | timeout kills the process group; govctl documents that timed-out targets may leave container state dirty |
| Phase 2 skip flags introduce silent failures | Medium | Medium | Skip flags are opt-in; default is always "run all checks". Documentation warns that skip = trust |

---

## Success Criteria

### Phase 1 Complete When

- `govctl list` enumerates all 21 targets and 7 groups.
- `govctl test.all --dry-run` prints the correct execution order.
- `govctl backend.test.unit` runs pytest and produces valid summary.json.
- `govctl test.all --continue-on-error` runs all test targets and reports
  aggregate results.
- `govctl check test.all --format json` emits structured preflight results.
- `govctl backend.test.unit --json` emits JSONL without human log interleaving.
- `artifacts/govctl/` is git-ignored.
- `.mcp/model.json` includes at least one govctl-routed task.
- `AGENTS.md` documents govctl usage.

### Phase 2 Complete When

- `govctl metrics.build.dashboard` runs without triggering a second
  `devctl ensure-stack-ready dashboard` call.
- `govctl metrics.generate.dashboard` runs without triggering
  `_devctl_dashboard_drift_preflight()`.
- Wall-clock time for `govctl build.all` is measurably reduced compared to
  Phase 1 (due to eliminated redundant drift checks).
