# devctl Python Module Extraction — Design Document

**Status:** proposed  
**Date:** 2025-07-25  
**Owner:** Systems Engineering  
**See also:** [build-governor-design.md](build-governor-design.md), [devctl-update-architecture.md](devctl-update-architecture.md), [AGENTS.md](../../AGENTS.md)

---

## Table of Contents

1. [Summary](#1-summary)
2. [Problem Statement](#2-problem-statement)
3. [Design Goals and Constraints](#3-design-goals-and-constraints)
4. [Current State Analysis](#4-current-state-analysis)
5. [Extraction Candidates](#5-extraction-candidates)
6. [Module Specifications](#6-module-specifications)
7. [What Is Not Being Refactored](#7-what-is-not-being-refactored)
8. [Library Structure](#8-library-structure)
9. [Migration Strategy](#9-migration-strategy)
10. [Acceptance Criteria](#10-acceptance-criteria)
11. [Open Questions](#11-open-questions)

---

## 1. Summary

This document proposes extracting stable, side-effect-free logic from `dev/bin/devctl` (1411 lines, Bash) into Python modules under `dev/lib/`. The goal is to reduce inline Python usage, consolidate duplicated logic, and create reusable building blocks that `govctl`, `metricsctl`, and future tooling can share — without rewriting devctl itself.

devctl remains a Bash script. It becomes a thinner orchestration layer that calls Python modules for pure computation and delegates to LXC/npm for side effects. The existing devctl interface (subcommand surface, exit codes, log format) does not change.

---

## 2. Problem Statement

### 2.1 Inline Python Scattered Across Bash

devctl contains multiple inline Python heredocs (`python3 - <<'PY'`) for operations that require JSON parsing, semantic version comparison, or hash computation. These inline blocks:

- Cannot be unit-tested independently.
- Are invisible to linters and type checkers.
- Duplicate logic that already exists elsewhere (e.g., `govctl_manifest.py` also parses JSON).

Specific instances:

| Location | Lines | Purpose |
|----------|-------|---------|
| `_json_dependency_version()` | 145–161 | Read `devDependencies` from package.json |
| `assert_web_stack_major_consistency()` | 162–199 | Compare SvelteKit/Vite major versions across stacks |
| `_snapshot_age_human()` | 302–328 | Convert timestamp to human-readable age |

### 2.2 Hash Logic Is Not Reusable

`compute_manifest_hash()`, `read_hash_file()`, and `compare_manifest_hash()` (lines 66–97) implement a deterministic SHA256 scheme for comparing host vs. container package state. This exact logic is needed by:

- `govctl` preflight `stack-drift-free` (currently reimplements it).
- `metricsctl` `_devctl_dashboard_drift_preflight` (currently calls devctl as a subprocess).
- `build-metrics-dashboard` (currently calls devctl for the same operation).

There is no shared implementation; each consumer either reimplements or shells out.

### 2.3 Lock Interface Duplication

The global repo lock (`/tmp/nightfall-repo.lock`) is implemented independently in three places:

| Tool | Implementation | FD | Mechanism |
|------|---------------|-----|-----------|
| devctl | `acquire_repo_lock()` / `release_repo_lock()` | 200 | `flock` from Bash |
| govctl-executor | `_govctl_acquire_lock()` / `_govctl_release_lock()` | 201 | `flock` from Bash |
| metricsctl | `_repo_lock()` context manager | N/A | `fcntl.flock` from Python |

All three interoperate correctly via the same lock file, but the implementations are independent and the FD selection (200 vs. 201) is undocumented convention.

---

## 3. Design Goals and Constraints

### 3.1 Goals

| ID | Goal |
|----|------|
| G1 | Extract pure-computation logic from devctl into testable Python modules |
| G2 | Provide a shared manifest-hash library usable by devctl, govctl, and metricsctl |
| G3 | Provide a shared repo-lock library usable across Bash and Python callers |
| G4 | Eliminate inline Python heredocs from devctl where a module call is cleaner |
| G5 | Preserve devctl's existing interface unchanged (commands, exit codes, log format) |

### 3.2 Constraints

| ID | Constraint |
|----|------------|
| C1 | No new runtime dependencies — Python stdlib + PyYAML only (both already present) |
| C2 | devctl remains a Bash script — this is extraction, not a rewrite |
| C3 | All extracted modules must be independently testable via pytest |
| C4 | Backward compatibility — existing devctl invocations must produce identical behavior |
| C5 | Modules live under `dev/lib/` alongside existing govctl Python modules |
| C6 | No changes to LXC operations, cache mounts, or container lifecycle logic |

---

## 4. Current State Analysis

devctl (1411 lines) breaks down into these functional categories:

### Side-Effect-Free Logic (Extraction Candidates)

| Function | Lines | Category | Side Effects |
|----------|-------|----------|-------------|
| `compute_manifest_hash()` | 66–80 | Hash computation | None — reads files, returns SHA256 |
| `read_hash_file()` | 81–86 | Hash I/O | None — reads file, strips whitespace |
| `compare_manifest_hash()` | 87–97 | Hash comparison | None — compares two strings |
| `get_node_version()` | 115–130 | Version parsing | None — reads `.nvmrc`/`.node-version` |
| `extract_major_from_semver()` | 131–144 | Version parsing | None — string extraction |
| `_json_dependency_version()` | 145–161 | JSON parsing (inline Python) | None — reads package.json key |
| `assert_web_stack_major_consistency()` | 162–199 | Validation (inline Python) | None — compares major versions |
| `_snapshot_age_human()` | 302–328 | Time formatting | None — arithmetic + string formatting |
| `_is_stateful_command()` | 200–211 | Command classification | None — pure predicate |

### Stateful Orchestration (NOT Extraction Candidates)

| Function | Lines | Why Not |
|----------|-------|---------|
| `_drift_check_stack()` | 523–560 | Auto-remediates via `npm ci`; state machine |
| `_ensure_stack_ready()` | 591–622 | Multi-step orchestrator with cascading side effects |
| `_install_node_exact()` | 374–403 | Downloads and installs via nvm; container mutation |
| `_sync_webui_sources()` | 349–357 | Tar + push into container |
| `_ensure_cache_mounts()` | 245–264 | LXC device creation |
| `cmd_setup()` | 624+ | Full container lifecycle bootstrap |
| `cmd_update()` | 800+ | Complex conditional orchestrator with simulation mode |

---

## 5. Extraction Candidates

### 5.1 Manifest Hash Module

**Current location:** devctl lines 66–97 (Bash functions)

**Responsibility:** Compute a deterministic SHA256 hash from `package.json` + `package-lock.json` content; compare host hash vs. container-stored hash.

**Inputs:**
- Path to directory containing `package.json` and `package-lock.json`
- (For comparison) path to a stored hash file

**Outputs:**
- Hash string (hex digest)
- Boolean match result
- Difference description on mismatch

**Callers today:**
- devctl: `_recalculate_host_hash()`, `_drift_check_stack()`, `_assert_stack_no_drift()`
- govctl: `stack-drift-free` preflight (reimplements the hash logic)
- metricsctl: `_devctl_dashboard_drift_preflight()` (calls devctl subprocess)
- build-metrics-dashboard: calls devctl `ensure-stack-ready`

### 5.2 Package Metadata Module

**Current location:** devctl lines 115–199 (Bash + inline Python)

**Responsibility:** Parse Node version pins, extract semver components, read package.json dependency versions, validate cross-stack version consistency.

**Inputs:**
- Path to `.node-version` or `.nvmrc`
- Path to `package.json`
- Dependency name to look up

**Outputs:**
- Version string
- Major version integer
- Consistency validation result (pass/fail + reason)

**Callers today:**
- devctl: `get_node_version()`, `_json_dependency_version()`, `assert_web_stack_major_consistency()`
- govctl: `node-version-match` preflight (reads `.node-version` independently)

### 5.3 Repo Lock Module

**Current location:** devctl lines 99–113 (Bash), govctl-executor lines 63–88 (Bash), metricsctl lines 74–87 (Python)

**Responsibility:** Acquire and release the global repo lock via `flock`/`fcntl.flock`. Support reentry detection via `DEVCTL_GLOBAL_LOCK_HELD` environment variable.

**Inputs:**
- Lock file path (default: `/tmp/nightfall-repo.lock`)
- Timeout in seconds (default: 300)

**Outputs:**
- Lock acquisition success/failure
- Context manager interface (Python callers)
- CLI exit code interface (Bash callers via subprocess)

**Callers today:**
- devctl: `acquire_repo_lock()`, `release_repo_lock()`, `_acquire_command_lock()`
- govctl-executor: `_govctl_acquire_lock()`, `_govctl_release_lock()`
- metricsctl: `_repo_lock()` context manager

**Interoperability requirement:** All callers must agree on the same lock file and the same `DEVCTL_GLOBAL_LOCK_HELD` reentry semantics. The Python module must be callable from Bash (as `python3 -m dev.lib.repo_lock acquire`) and from Python (as `from dev.lib.repo_lock import RepoLock`).

### 5.4 Source Fingerprinting Module

**Current location:** build-metrics-dashboard lines 61–88 (inline Python heredoc)

**Responsibility:** Compute a deterministic SHA256 fingerprint of source files (`.svelte`, `.ts`, `.js`, `.css` + config files), excluding `node_modules` and `.svelte-kit`. Write a JSON build stamp.

**Inputs:**
- Root directory to scan
- Glob patterns to include/exclude
- Output stamp path

**Outputs:**
- Fingerprint hex digest
- Build stamp JSON (fingerprint + timestamp)

**Callers today:**
- build-metrics-dashboard (inline Python)
- (No other callers yet, but the pattern is generally useful.)

---

## 6. Module Specifications

### 6.1 `dev/lib/manifest_hash.py`

```
manifest_hash.py
├── compute_hash(directory: Path) -> str
│     Read package.json + package-lock.json, return SHA256 hex digest.
│     Deterministic: sorted file content, UTF-8 encoding.
│
├── read_hash_file(path: Path) -> str
│     Read a single-line hash file, strip whitespace.
│
├── compare(host_dir: Path, hash_file: Path) -> CompareResult
│     Return namedtuple(match: bool, host_hash: str, stored_hash: str)
│
└── CLI: python3 dev/lib/manifest_hash.py compute <dir>
         python3 dev/lib/manifest_hash.py compare <dir> <hash_file>
```

**Invariants:**
- `compute_hash` must produce identical output to devctl's `compute_manifest_hash()` for the same inputs.
- Hash is computed from `cat package.json package-lock.json | sha256sum` equivalent — same file concatenation order.
- Empty or missing files produce a defined sentinel hash (empty string), not an error.

**Acceptance criteria:**
- Unit tests verify hash equivalence with devctl's Bash implementation for representative inputs.
- govctl `stack-drift-free` preflight can delegate to this module.
- devctl can call via `python3 dev/lib/manifest_hash.py compute <dir>` and consume stdout.

### 6.2 `dev/lib/package_meta.py`

```
package_meta.py
├── read_node_version(repo_root: Path) -> str
│     Read .node-version or .nvmrc; strip "v" prefix; return bare version.
│
├── extract_major(semver: str) -> int
│     Handle caret/tilde/inequality prefixes: "^5.3.1" -> 5
│
├── dependency_version(package_json: Path, name: str) -> str
│     Read devDependencies[name] from package.json. Return "" if absent.
│
├── check_stack_consistency(
│       webui_pkg: Path, dashboard_pkg: Path,
│       packages: list[str]  # e.g. ["@sveltejs/kit", "vite"]
│   ) -> ConsistencyResult
│     Compare major versions across stacks.
│     Return namedtuple(ok: bool, mismatches: list[Mismatch])
│
└── CLI: python3 dev/lib/package_meta.py node-version <repo_root>
         python3 dev/lib/package_meta.py dep-version <package_json> <name>
         python3 dev/lib/package_meta.py check-consistency <webui_pkg> <dashboard_pkg>
```

**Invariants:**
- `read_node_version` must produce the same result as devctl's `get_node_version()`.
- `extract_major` must handle caret (`^`), tilde (`~`), inequality (`>=`), and bare version strings.
- `dependency_version` replaces the inline Python heredoc at devctl line 145.

**Acceptance criteria:**
- Unit tests cover all semver prefix formats.
- devctl can replace `_json_dependency_version()` with a subprocess call.
- govctl's `node-version-match` preflight can delegate to this module.

### 6.3 `dev/lib/repo_lock.py`

```
repo_lock.py
├── class RepoLock:
│     __init__(lock_file: Path, timeout_sec: int = 300)
│     acquire() -> bool
│     release() -> None
│     __enter__ / __exit__  — context manager
│     is_reentrant() -> bool  — check DEVCTL_GLOBAL_LOCK_HELD env
│
├── acquire_lock(lock_file: Path, timeout: int) -> bool
│     Functional wrapper for Bash callers.
│     Sets DEVCTL_GLOBAL_LOCK_HELD=1 on success, prints to stderr on timeout.
│
├── release_lock() -> None
│     Releases lock held by current process.
│
└── CLI: python3 dev/lib/repo_lock.py acquire [--timeout 300] [--lock-file /tmp/nightfall-repo.lock]
         python3 dev/lib/repo_lock.py release
         python3 dev/lib/repo_lock.py status  # is lock held?
```

**Invariants:**
- Must interoperate with devctl Bash `flock` (same file, same semantics).
- Reentry guard: if `DEVCTL_GLOBAL_LOCK_HELD=1`, skip acquisition.
- Timeout behavior matches devctl: fail with message, non-zero exit.
- Lock is advisory (`flock`/`fcntl.LOCK_EX`), not mandatory.

**Acceptance criteria:**
- Unit tests verify reentry semantics.
- Integration test: Python acquires lock, Bash `flock` blocks until timeout.
- metricsctl can replace `_repo_lock()` with an import.
- govctl-executor can optionally delegate to CLI mode (future).

### 6.4 `dev/lib/source_fingerprint.py`

```
source_fingerprint.py
├── compute_fingerprint(
│       root: Path,
│       include_globs: list[str],  # e.g. ["*.svelte", "*.ts", "*.js", "*.css"]
│       exclude_dirs: list[str],   # e.g. ["node_modules", ".svelte-kit"]
│   ) -> str
│     Deterministic SHA256 over sorted matching files.
│
├── write_build_stamp(
│       root: Path, stamp_path: Path,
│       include_globs: list[str], exclude_dirs: list[str]
│   ) -> dict
│     Compute fingerprint + write JSON stamp with ISO-8601 timestamp.
│     Return the stamp dict.
│
└── CLI: python3 dev/lib/source_fingerprint.py compute <root> [--include '*.svelte' ...]
         python3 dev/lib/source_fingerprint.py stamp <root> <stamp_path>
```

**Invariants:**
- `compute_fingerprint` must produce the same digest as build-metrics-dashboard's inline Python for the same file set.
- File enumeration order is deterministic: `sorted()` by relative path.
- Hash includes both the relative path and the file content (prevents collision from renamed files with same content).

**Acceptance criteria:**
- Unit tests with a known fixture directory produce deterministic, reproducible hashes.
- build-metrics-dashboard can replace its inline Python with a CLI call.

---

## 7. What Is Not Being Refactored

### 7.1 Container Lifecycle Operations

All LXC operations (`lxc info`, `lxc exec`, `lxc start`, `lxc file push`, `lxc config device`) remain in Bash. These are shell-native, tightly coupled to the LXC CLI, and benefit from pipefail/set -e semantics. Extracting them to Python would add complexity without improving testability.

### 7.2 Cache Mount Management

`_ensure_cache_mounts()` and `_cache_mounts_active()` configure LXC disk devices. This is imperative host-to-container binding with no computational logic worth extracting.

### 7.3 npm/Node Operations

`_install_stack()`, `_regenerate_stack()`, `_install_node_exact()`, and `_pull_lockfile()` are shell orchestrations that call npm/nvm inside the container. The value is in the sequence and error handling, not in computation.

### 7.4 Command Dispatch and Logging

devctl's `main()` case dispatch, `nf_log_*` formatting, and subcommand routing stay in Bash. They are the "thin orchestration layer" that calls into Python modules for computation and LXC for side effects.

### 7.5 devctl update State Machine

The `cmd_update()` function (800+ lines) is a complex conditional orchestrator with simulation mode, regression gates, and snapshot management. It is coupled to LXC state transitions. Attempting to extract it would be a rewrite, not a refactoring.

---

## 8. Library Structure

```
dev/lib/
├── govctl_manifest.py         # (existing) YAML → JSON manifest normalizer
├── govctl_resolve.py          # (existing) Topological sort resolver
├── govctl-preflights.sh       # (existing) Bash preflight checks
├── govctl-executor.sh         # (existing) Bash executor engine
├── manifest_hash.py           # (new) §6.1 — Package manifest hashing
├── package_meta.py            # (new) §6.2 — Node version + dependency parsing
├── repo_lock.py               # (new) §6.3 — Global repo lock
└── source_fingerprint.py      # (new) §6.4 — Source file fingerprinting
```

Each new module:
- Has a `__main__`-guarded CLI entry point for Bash callers.
- Is importable as a Python module for Python callers.
- Uses only stdlib + PyYAML (and PyYAML only where needed).
- Has a corresponding test file in `tests/unit/`.

---

## 9. Migration Strategy

### Phase 1: Create Modules + Tests

Write the four Python modules with full test coverage. Do not change any Bash scripts yet. Validate hash equivalence between Python and Bash implementations using known fixture data.

### Phase 2: Wire In

Replace inline Python heredocs in devctl with subprocess calls to the new modules. Replace govctl preflight reimplementations with calls to the shared modules. Replace metricsctl `_repo_lock()` with an import from `repo_lock.py`.

Each replacement is a single-function swap:
- Old: inline `python3 - <<'PY' ... PY`
- New: `python3 dev/lib/package_meta.py dep-version "$pkg_json" "$dep_name"`

### Phase 3: Remove Duplicates

After all callers are migrated, remove:
- devctl's `compute_manifest_hash()`, `read_hash_file()`, `compare_manifest_hash()` (replaced by `manifest_hash.py`)
- devctl's `_json_dependency_version()` inline Python (replaced by `package_meta.py`)
- devctl's `assert_web_stack_major_consistency()` inline Python (replaced by `package_meta.py`)
- metricsctl's `_repo_lock()` (replaced by `repo_lock.py`)
- build-metrics-dashboard's inline fingerprinting Python (replaced by `source_fingerprint.py`)

**Each phase must be independently deployable and testable. No big-bang migration.**

---

## 10. Acceptance Criteria

### Per-Module

| Module | Criterion |
|--------|-----------|
| `manifest_hash.py` | Hash output matches devctl Bash for 3+ fixture directories |
| `manifest_hash.py` | govctl preflight `stack-drift-free` uses this module |
| `package_meta.py` | All semver prefix formats handled: bare, `^`, `~`, `>=`, `<=`, `>`, `<` |
| `package_meta.py` | devctl inline Python heredocs eliminated |
| `repo_lock.py` | Cross-language interop: Python lock blocks Bash flock and vice versa |
| `repo_lock.py` | Reentry guard verified: nested acquisition succeeds when env is set |
| `source_fingerprint.py` | Deterministic: same directory → same hash across runs |
| `source_fingerprint.py` | build-metrics-dashboard can use CLI mode as drop-in |

### System-Level

| Criterion |
|-----------|
| All existing devctl subcommands produce identical behavior after migration |
| All existing govctl tests (147) continue to pass |
| All existing metricsctl subcommands work identically |
| No new runtime dependencies beyond Python stdlib + PyYAML |
| All new modules have ≥90% line coverage in unit tests |

---

## 11. Open Questions

### Q1: Module Package vs. Flat Files

Should the new modules be a proper Python package (`dev/lib/nightfall_lib/`) or remain flat files (`dev/lib/manifest_hash.py`)? Flat files match the existing govctl pattern. A package would enable relative imports between modules (e.g., `repo_lock` used by `manifest_hash` for a lock-then-hash pattern).

**Leaning:** Flat files initially. Package if cross-module imports become necessary.

### Q2: Bash Function Deprecation Timeline

After Phase 2, the replaced Bash functions in devctl become dead code. Should they be removed immediately (Phase 3) or kept as fallbacks for one release cycle?

**Leaning:** Remove immediately in Phase 3. The Python modules are the single source of truth; dead Bash code creates maintenance burden and confusion.

### Q3: repo_lock.py FD Selection

The current convention is FD 200 (devctl), FD 201 (govctl). The Python implementation uses `fcntl.flock` on a file handle (no explicit FD number). Should the Python module document the FD convention, or is it irrelevant since all implementations use the same lock file with `LOCK_EX`?

**Leaning:** Document but don't enforce. The FD number is an implementation detail of each Bash script. The interop contract is the lock file path + `LOCK_EX` semantics.
