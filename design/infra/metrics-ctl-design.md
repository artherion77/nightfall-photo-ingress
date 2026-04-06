# metricsctl Python Module Extraction — Design Document

**Status:** proposed  
**Date:** 2025-07-25  
**Owner:** Systems Engineering  
**See also:** [devctl-design.md](devctl-design.md), [build-governor-design.md](build-governor-design.md), [AGENTS.md](../../AGENTS.md)

---

## Table of Contents

1. [Summary](#1-summary)
2. [Problem Statement](#2-problem-statement)
3. [Design Goals and Constraints](#3-design-goals-and-constraints)
4. [Current State Analysis](#4-current-state-analysis)
5. [Extraction Candidates](#5-extraction-candidates)
6. [Module Specifications](#6-module-specifications)
7. [What Is Not Being Refactored](#7-what-is-not-being-refactored)
8. [Migration Strategy](#8-migration-strategy)
9. [Acceptance Criteria](#9-acceptance-criteria)
10. [Open Questions](#10-open-questions)

---

## 1. Summary

This document proposes extracting reusable infrastructure logic from `metricsctl` (403 lines, Python) into shared modules under `dev/lib/`. Unlike devctl (which is Bash and needs Python extraction for testability), metricsctl is already Python. The refactoring here is about **decoupling** — breaking tight coupling to devctl subprocess calls and isolating shared patterns (venv bootstrap, repo lock, drift detection) so they can be composed by govctl, devctl, and future tooling without subprocess chains.

metricsctl remains the CLI entry point. Its dispatcher pattern is clean and does not change. What changes is where the infrastructure plumbing lives.

---

## 2. Problem Statement

### 2.1 devctl Subprocess Coupling

`_devctl_dashboard_drift_preflight()` (lines 88–106) calls devctl as a subprocess to run `ensure-stack-ready dashboard` before dashboard generation. This creates:

- An opaque dependency chain: metricsctl → devctl subprocess → LXC → npm ci → hash update.
- Lock reentry complexity: metricsctl acquires the repo lock, then sets `DEVCTL_GLOBAL_LOCK_HELD=1` before calling devctl so devctl doesn't deadlock on the same lock.
- Diagnosis difficulty: if the drift preflight fails, the operator sees a devctl error inside a metricsctl context, with no structured output to distinguish which tool owns the failure.

When govctl orchestrates `metrics.generate.dashboard`, this creates a triple-nesting: govctl → metricsctl → devctl. govctl already handles preflight checks (`container-running`, `stack-drift-free`) that partially overlap with what devctl's `ensure-stack-ready` does internally. The overlap is harmless but wasteful.

### 2.2 Lock Implementation Is Duplicated

`_repo_lock()` (lines 74–87) is a clean Python context manager for the global repo lock. The identical lock semantics are reimplemented in:

- devctl (Bash `flock` on FD 200)
- govctl-executor (Bash `flock` on FD 201)

All three implementations work correctly and interoperate via the same lock file. But the Python implementation is the most composable (context manager, exception-safe), and could serve as the canonical implementation for all Python callers including `mcp_server.py`.

### 2.3 Venv Bootstrap Is Not Reusable

`_maybe_reexec_venv()` (lines 23–48) is a well-designed pattern for ensuring script execution under the correct Python interpreter. This pattern is needed by:

- Any future Python scripts in `dev/bin/` that depend on repo packages.
- The MCP server (`mcp_server.py`) if it were to support running outside the venv.
- Potential Python replacements for inline Python heredocs in Bash scripts.

Currently the pattern is copy-pasted wherever needed.

### 2.4 Dashboard Fingerprinting Has Two Implementations

The `dashboard-build-stamp` command delegates to `poller_runner` functions (`_compute_dashboard_source_fingerprint`, `_read_dashboard_build_stamp`, `_dashboard_needs_rebuild`). Meanwhile, `build-metrics-dashboard` (Bash script) has its own inline Python fingerprinting logic. These two implementations compute the same hash with the same algorithm but are independent code paths that could drift.

---

## 3. Design Goals and Constraints

### 3.1 Goals

| ID | Goal |
|----|------|
| G1 | Extract `_repo_lock()` to a shared module importable by metricsctl, mcp_server, and future Python tools |
| G2 | Extract `_maybe_reexec_venv()` to a shared module for any repo-rooted Python script |
| G3 | Decouple dashboard drift preflight from devctl subprocess dependency |
| G4 | Consolidate dashboard fingerprinting into a single shared implementation |
| G5 | Preserve metricsctl's existing CLI interface unchanged |

### 3.2 Constraints

| ID | Constraint |
|----|------------|
| C1 | No new runtime dependencies — Python stdlib only for shared modules |
| C2 | metricsctl dispatcher pattern stays as-is — it is clean and correct |
| C3 | Lock interop with Bash callers must be preserved |
| C4 | Module pipeline interfaces (Module 2–8 runners) are out of scope |
| C5 | No changes to systemd units, poller runtime, or cron configuration |
| C6 | Shared modules go under `dev/lib/` consistent with the devctl design |

---

## 4. Current State Analysis

### 4.1 metricsctl Structure

metricsctl is a 403-line Python script organized as:

| Section | Lines | Purpose |
|---------|-------|---------|
| Imports + constants | 1–20 | Standard library + runner imports |
| `_maybe_reexec_venv()` | 23–48 | Venv bootstrap with reentry guard |
| Runner imports | 49–71 | Module 1–8 runner function imports |
| `_repo_lock()` | 74–87 | Global repo lock context manager |
| `_devctl_dashboard_drift_preflight()` | 88–106 | devctl subprocess call for drift fix |
| `_repo_root()` | 108–110 | Repo root discovery |
| Command handlers | 112–300 | 18 thin dispatchers (`cmd_*` functions) |
| `build_parser()` | 302–389 | argparse subcommand registration |
| `main()` | 392–395 | Parse + dispatch |

### 4.2 Command Handler Analysis

All 18 command handlers follow the same pattern:

```python
def cmd_<name>(args: argparse.Namespace) -> int:
    root = _repo_root()
    # Optional: acquire lock, run preflight
    result = runner_function(repo_root=root, **args_kwargs)
    print(json.dumps(result, indent=2))  # or print(message)
    return 0
```

Only `cmd_generate_dashboard` (Module 5) deviates: it acquires `_repo_lock()` and calls `_devctl_dashboard_drift_preflight()` before the runner. This is the only handler with infrastructure coupling.

### 4.3 Coupling Map

```
metricsctl
├── _maybe_reexec_venv()          → coupled to: .venv path convention
├── _repo_lock()                  → coupled to: /tmp/nightfall-repo.lock
├── _devctl_dashboard_drift_preflight()
│   ├── coupled to: dev/bin/devctl binary existence
│   ├── coupled to: DEVCTL_GLOBAL_LOCK_HELD env convention
│   └── coupled to: devctl ensure-stack-ready subcommand
├── metrics.runner.*              → coupled to: Module 2-8 implementations
└── poller_runner utilities       → coupled to: dashboard static dir layout
    ├── _compute_dashboard_source_fingerprint()
    ├── _read_dashboard_build_stamp()
    └── _dashboard_needs_rebuild()
```

---

## 5. Extraction Candidates

### 5.1 Repo Lock → `dev/lib/repo_lock.py`

**Shared with:** [devctl-design.md §6.3](devctl-design.md#63-devlibrepo_lockpy)

This is the same module proposed in the devctl design. metricsctl's `_repo_lock()` becomes an import:

```python
# Before
@contextmanager
def _repo_lock() -> object:
    ...

# After
from dev.lib.repo_lock import RepoLock
```

The metricsctl implementation is the cleanest of the three existing implementations and should inform the shared module's Python interface.

### 5.2 Venv Bootstrap → `dev/lib/venv_bootstrap.py`

**Current location:** metricsctl lines 23–48

**Responsibility:** Detect whether the current Python interpreter is the repo venv. If not, re-execute the current script under the venv Python. Support a reentry guard to prevent infinite re-exec loops.

**Callers today:**
- metricsctl (only current caller)

**Future callers:**
- Any new Python CLI tool in `dev/bin/`
- Potential Python CLI wrappers for modules in `dev/lib/`

**Why extract now:** The pattern is non-trivial (cross-platform path detection, reentry guard, `os.execve` semantics) and would be copy-pasted incorrectly if needed elsewhere.

### 5.3 Drift Preflight Decoupling

**Current location:** metricsctl lines 88–106

**Problem:** `_devctl_dashboard_drift_preflight()` calls `devctl ensure-stack-ready dashboard` as a subprocess. When govctl orchestrates this target, govctl already runs preflight checks (`container-running`, `stack-drift-free`) that overlap with what devctl does internally. The subprocess call is a coarse-grained "do everything" invocation when a fine-grained check may suffice.

**Proposed decoupling:**

Phase 1 (this design): Do not change `_devctl_dashboard_drift_preflight()`. Instead, document that when metricsctl runs under govctl orchestration, the govctl preflight checks make the devctl call redundant but harmless — `ensure-stack-ready` is idempotent by design.

Phase 2 (future): When `dev/lib/manifest_hash.py` is available (from the devctl design), replace the devctl subprocess call with a direct hash comparison:

```python
# Future: direct drift check without subprocess
from dev.lib.manifest_hash import compare
result = compare(host_dir=dashboard_pkg_dir, hash_file=container_hash_path)
if not result.match:
    # Only then call devctl for remediation
    subprocess.run([devctl, "ensure-stack-ready", "dashboard"], ...)
```

This makes the drift check inspectable and avoids a full `ensure-stack-ready` when the stack is already drift-free.

### 5.4 Dashboard Fingerprinting → `dev/lib/source_fingerprint.py`

**Shared with:** [devctl-design.md §6.4](devctl-design.md#64-devlibsource_fingerprintpy)

The `poller_runner` functions (`_compute_dashboard_source_fingerprint`, `_read_dashboard_build_stamp`, `_dashboard_needs_rebuild`) compute a source fingerprint to decide whether the dashboard needs rebuilding. `build-metrics-dashboard` (Bash) has its own inline Python fingerprinting. Both should delegate to a single `source_fingerprint.py` module.

metricsctl's `cmd_dashboard_build_stamp` would then call:

```python
from dev.lib.source_fingerprint import compute_fingerprint, write_build_stamp
```

instead of the current `poller_runner` private functions.

---

## 6. Module Specifications

### 6.1 `dev/lib/venv_bootstrap.py`

```
venv_bootstrap.py
├── ensure_venv(
│       script_path: Path,           # __file__ of calling script
│       venv_name: str = ".venv",    # venv directory name
│       guard_var: str = None,       # reentry env var (auto-generated if None)
│   ) -> None
│     If not running from venv, os.execve under venv Python.
│     If venv doesn't exist, return silently (caller runs with system Python).
│     If guard_var is set in env, return silently (reentry protection).
│
├── is_running_in_venv(venv_name: str = ".venv") -> bool
│     Check if current interpreter matches repo venv.
│
└── No CLI — this module is imported-only; it must run before imports happen.
```

**Invariants:**
- `ensure_venv` call must be the first executable statement after stdlib imports.
- Reentry guard prevents infinite `os.execve` loops.
- Cross-platform: handles `bin/python` (Unix) and `Scripts/python.exe` (Windows).
- If the venv doesn't exist, the function is a no-op (graceful degradation).

**Acceptance criteria:**
- metricsctl can replace `_maybe_reexec_venv()` with `from dev.lib.venv_bootstrap import ensure_venv; ensure_venv(Path(__file__))`.
- Unit test: mock `os.execve`, verify it is called with correct arguments when interpreter mismatch is detected.
- Unit test: verify reentry guard prevents re-exec when env var is already set.

### 6.2 `dev/lib/repo_lock.py`

**Specified in [devctl-design.md §6.3](devctl-design.md#63-devlibrepo_lockpy).**

metricsctl-specific requirements:

- Context manager interface (`with RepoLock() as lock:`) must be a drop-in for current `_repo_lock()`.
- Must set `DEVCTL_GLOBAL_LOCK_HELD=1` in the process environment on acquisition (for devctl subprocess interop).
- Must unset on release.

### 6.3 `dev/lib/source_fingerprint.py`

**Specified in [devctl-design.md §6.4](devctl-design.md#64-devlibsource_fingerprintpy).**

metricsctl-specific requirements:

- The `compute_fingerprint()` function must produce the same digest as `poller_runner._compute_dashboard_source_fingerprint()` for the same directory.
- The `poller_runner` private functions become thin wrappers around the shared module (or are removed, with metricsctl calling the shared module directly).

---

## 7. What Is Not Being Refactored

### 7.1 Module Runner Implementations

The `metrics.runner.*` modules (Module 1–8) are the business logic layer. They are already properly modular: each module has its own runner function with a clean `(repo_root, run_id, ...)` interface. These are not infrastructure and are not candidates for extraction to `dev/lib/`.

### 7.2 Command Dispatcher Pattern

metricsctl's `build_parser()` and `cmd_*` handler pattern is clean. 17 of 18 handlers are trivial dispatchers. This structure does not need change.

### 7.3 Schema Validation

`metrics.runner.schema_contract` provides `validate_manifest_payload` and `validate_metrics_payload`. These are domain-specific validators tied to the metrics schema, not shared infrastructure.

### 7.4 Poller Runtime Management

Module 6 functions (install, start, stop, status, reconfigure, run-now, uninstall) manage systemd units and runtime state. These are tightly coupled to the poller's operational model and have no reuse outside metricsctl.

### 7.5 Retention and Ops (Module 8)

`apply_retention_policy`, `ensure_ops_state`, and `cleanup_runtime_artifacts` are operational housekeeping functions. They are self-contained and not part of the build/orchestration infrastructure being extracted.

---

## 8. Migration Strategy

### Phase 1: Create Shared Modules

Implement `venv_bootstrap.py`, `repo_lock.py`, and `source_fingerprint.py` under `dev/lib/` with full test coverage. (These modules are shared with the devctl design — implementation happens once.)

### Phase 2: Wire Into metricsctl

Replace metricsctl's private implementations with imports from shared modules:

| metricsctl function | Replacement |
|---------------------|-------------|
| `_maybe_reexec_venv()` | `from dev.lib.venv_bootstrap import ensure_venv` |
| `_repo_lock()` | `from dev.lib.repo_lock import RepoLock` |
| `_devctl_dashboard_drift_preflight()` | No change in Phase 2 (stays as subprocess call) |

Each replacement is a single-import swap. metricsctl shrinks by ~50 lines.

### Phase 3: Drift Preflight Refinement (Future)

When `manifest_hash.py` is available, replace the coarse devctl subprocess call with a direct hash check + conditional remediation. This phase depends on the devctl design's module being implemented first.

### Phase 4: Fingerprint Consolidation

Replace `poller_runner` private fingerprinting functions with calls to `source_fingerprint.py`. Update `build-metrics-dashboard` similarly. Remove duplicate implementations.

**Each phase is independently deployable. No phase depends on another being complete first (except Phase 3 → depends on devctl design Phase 1).**

---

## 9. Acceptance Criteria

### Per-Change

| Change | Criterion |
|--------|-----------|
| `_maybe_reexec_venv()` → `venv_bootstrap.py` | metricsctl launches correctly from both system Python and venv Python |
| `_repo_lock()` → `repo_lock.py` | `cmd_generate_dashboard` still acquires lock; devctl subprocess doesn't deadlock |
| Fingerprint consolidation | `./dev/bin/metricsctl dashboard-build-stamp` produces identical output before/after |

### System-Level

| Criterion |
|-----------|
| All metricsctl subcommands produce identical behavior after migration |
| All govctl tests (147) continue to pass |
| metricsctl → devctl lock reentry still works (no deadlock) |
| No new runtime dependencies |
| Shared modules have ≥90% line coverage in unit tests |

---

## 10. Open Questions

### Q1: Import Path Mechanics

metricsctl currently runs at repo root with `sys.path` containing the repo root. The new modules live under `dev/lib/`. The import `from dev.lib.repo_lock import RepoLock` requires either:

- (a) Adding `dev/lib` to `sys.path` (explicit `sys.path.insert` at top of metricsctl).
- (b) Making `dev/lib` a proper Python package with `__init__.py`.
- (c) Using relative path import in the `ensure_venv` bootstrap (module path computed from `__file__`).

**Leaning:** Option (a) — matches how govctl modules are currently invoked (as standalone scripts with `python3 dev/lib/module.py`). The shared modules are utility scripts, not installable packages.

### Q2: `_devctl_dashboard_drift_preflight` Ownership

Should the drift preflight logic stay in metricsctl (calling devctl as a subprocess) or move to a shared module that both metricsctl and govctl can use?

**Leaning:** Keep in metricsctl for now. The function is simple (6 lines of subprocess plumbing) and tightly coupled to the devctl subcommand interface. Moving it to a shared module doesn't reduce coupling — it just moves it. The real decoupling comes in Phase 3 when the hash check replaces the subprocess call.

### Q3: Fingerprint Function Ownership

The fingerprinting functions currently live in `metrics.runner.poller_runner` (which is a large module with many responsibilities). Should fingerprinting move to `dev/lib/source_fingerprint.py` exclusively, or should `poller_runner` keep a thin wrapper that delegates to the shared module?

**Leaning:** Shared module as source of truth. `poller_runner` keeps thin wrappers (e.g., `_compute_dashboard_source_fingerprint(root)` calls `source_fingerprint.compute_fingerprint(root / "dashboard", ...)` with dashboard-specific globs). This preserves `poller_runner`'s interface for the Module 6 runtime while eliminating duplicate hash logic.

### Q4: venv_bootstrap Import Timing

`ensure_venv()` must execute before any non-stdlib imports (since the venv may have different package versions). This means the import of `venv_bootstrap.py` itself must be early — but `venv_bootstrap.py` lives under `dev/lib/`, which may not be on `sys.path` before the venv is active.

**Resolution options:**
- (a) The calling script computes the `dev/lib/` path from `__file__` and appends to `sys.path` before importing `venv_bootstrap`.
- (b) The shared module is vendored as a single-file import at repo root.
- (c) The pattern is kept inline (copy-pasted) in each script, and only the lock/fingerprint modules are shared.

**Leaning:** Option (a). The `sys.path` manipulation is a two-line preamble that each CLI script can have. It's less error-prone than copy-pasting the entire venv bootstrap logic.
