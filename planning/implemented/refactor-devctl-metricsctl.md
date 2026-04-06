# Phase 2 — devctl & metricsctl Python Module Extraction

**Status:** implemented  
**Date:** 2025-07-26  
**Implemented on:** 2026-04-06  
**Supersedes:** build-governor-implementation-plan.md Chunks 8–11  
**Design authority:**
- [devctl-design.md](../../design/infra/devctl-design.md)
- [metrics-ctl-design.md](../../design/infra/metrics-ctl-design.md)

---

## Implementation Summary (2026-04-06)

Execution completed in the planned sequence across sub-phases 2.1 through 2.4.

- Added shared modules under `dev/lib/`: `manifest_hash.py`, `package_meta.py`, `repo_lock.py`, `source_fingerprint.py`, `venv_bootstrap.py` with unit coverage.
- Integrated shared modules into `dev/bin/devctl` (hash + package metadata paths) and `metricsctl` (repo lock + venv bootstrap).
- Migrated govctl preflights in `dev/lib/govctl-preflights.sh` to shared modules and updated `dev/bin/build-metrics-dashboard` to use `source_fingerprint.py`.
- Removed superseded dead code from `dev/bin/devctl` after integration completion.
- Updated `dev/govctl-targets.yaml` to remove redundant dashboard readiness dependency and documented safe overlap.
- Corrected and stabilized follow-up invariants in unit tests for MCP mapping and metrics history artifact expectations.

---

## A) Summary

Phase 2 extracts side-effect-free logic from devctl (Bash) and metricsctl
(Python) into five shared Python modules under `dev/lib/`. This eliminates
inline Python heredocs in Bash, consolidates duplicated lock/hash/fingerprint
implementations, and creates testable building blocks that govctl, devctl, and
metricsctl can share.

Phase 2 does NOT:
- Rewrite devctl from Bash to Python.
- Change any tool's external CLI interface, exit codes, or output format.
- Modify container lifecycle operations (LXC, npm, nvm).
- Alter the govctl executor, resolver, or preflight engine.
- Add runtime dependencies beyond Python stdlib + PyYAML (both already present).

The old Phase 2 skip-flag approach (Chunks 8–10 from the original plan) is
subsumed. Instead of adding flags to tolerate redundant subprocess calls, we
extract the shared computation so the redundancy disappears at the library
level. Section E justifies this per original chunk.

---

## B) Module Inventory and Ownership

Five modules. All live under `dev/lib/` alongside existing govctl modules.

| Module | Responsibility | Consumers | Source of Truth |
|--------|---------------|-----------|-----------------|
| `manifest_hash.py` | SHA256 of package.json + package-lock.json; compare host vs. stored hash | devctl, govctl preflight `stack-drift-free`, metricsctl (future drift check) | devctl-design.md §6.1 |
| `package_meta.py` | Read .node-version, extract semver major, read dependency versions, validate cross-stack consistency | devctl (replaces inline Python), govctl preflight `node-version-match` | devctl-design.md §6.2 |
| `repo_lock.py` | Global repo lock via fcntl.flock; context manager + CLI; reentry via DEVCTL_GLOBAL_LOCK_HELD | metricsctl, govctl-executor (future), devctl (Bash CLI mode) | devctl-design.md §6.3 |
| `source_fingerprint.py` | Deterministic SHA256 of source files by glob; write JSON build stamps | build-metrics-dashboard, metricsctl dashboard-build-stamp | devctl-design.md §6.4 |
| `venv_bootstrap.py` | Detect interpreter mismatch, re-exec under repo venv, reentry guard | metricsctl, future Python CLIs in dev/bin/ | metrics-ctl-design.md §6.1 |

Acceptance criteria per module are defined in the design documents and
referenced from each chunk below.

---

## C) Phases Inside Phase 2

Phase 2 is organized into four sub-phases. Each sub-phase is independently
deployable and testable.

| Sub-phase | Title | Description |
|-----------|-------|-------------|
| 2.1 | Shared modules + tests | Create all five modules with unit tests; no integration with existing tools |
| 2.2 | devctl integration | Replace inline Python heredocs and duplicated Bash functions with calls to shared modules |
| 2.3 | metricsctl integration | Replace metricsctl private functions with imports from shared modules |
| 2.4 | Command-surface refinement + manifest update | Wire govctl preflights to shared modules; update govctl-targets.yaml; remove dead code |

Sub-phase 2.1 has no dependencies on 2.2/2.3/2.4.
Sub-phases 2.2 and 2.3 depend on 2.1 but are independent of each other.
Sub-phase 2.4 depends on 2.2 and 2.3.

---

## D) Chunk List

### Sub-phase 2.1 — Shared Modules + Tests

---

#### Chunk 2.1.1: manifest_hash.py

**Intent:** Create a shared module for deterministic package manifest hashing.

**Scope boundary:**
- Create `dev/lib/manifest_hash.py` with `compute_hash()`, `read_hash_file()`,
  `compare()`, and CLI entry point.
- Create `tests/unit/test_manifest_hash.py`.
- Create test fixtures under `tests/fixtures/manifest_hash/` with known
  package.json + package-lock.json content and pre-computed expected hashes.
- Do NOT modify devctl, govctl, or metricsctl.

**Files to touch:**
- `dev/lib/manifest_hash.py` (create)
- `tests/unit/test_manifest_hash.py` (create)
- `tests/fixtures/manifest_hash/` (create directory + fixture files)

**Deterministic validation:**
```bash
cd /home/chris/dev/nightfall-photo-ingress
python3 -m pytest tests/unit/test_manifest_hash.py -v
# All tests pass
python3 dev/lib/manifest_hash.py compute tests/fixtures/manifest_hash/valid/
# Output matches expected hash from fixtures
```

**Acceptance criteria:**
- `compute_hash()` produces identical output to devctl's `compute_manifest_hash()`
  for the same inputs (verified by fixture tests with pre-computed hashes).
- Hash is computed from `package.json` + `package-lock.json` concatenation in
  that order, SHA256, hex digest.
- Missing files produce a defined sentinel (empty string), not an exception.
- CLI mode (`python3 dev/lib/manifest_hash.py compute <dir>`) prints hash to stdout.
- CLI mode (`python3 dev/lib/manifest_hash.py compare <dir> <hash_file>`) exits 0 on
  match, 1 on mismatch, prints diff to stderr on mismatch.
- ≥90% line coverage.

**Commit boundary:** Single commit: `feat(dev/lib): add manifest_hash module`.

**Dependencies:** None.

---

#### Chunk 2.1.2: package_meta.py

**Intent:** Create a shared module for Node version parsing and dependency
metadata extraction.

**Scope boundary:**
- Create `dev/lib/package_meta.py` with `read_node_version()`,
  `extract_major()`, `dependency_version()`, `check_stack_consistency()`,
  and CLI entry point.
- Create `tests/unit/test_package_meta.py`.
- Create test fixtures under `tests/fixtures/package_meta/`.
- Do NOT modify devctl, govctl, or metricsctl.

**Files to touch:**
- `dev/lib/package_meta.py` (create)
- `tests/unit/test_package_meta.py` (create)
- `tests/fixtures/package_meta/` (create directory + fixture files)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_package_meta.py -v
# All tests pass
python3 dev/lib/package_meta.py node-version .
# Output matches content of .node-version
```

**Acceptance criteria:**
- `read_node_version()` handles both `.node-version` and `.nvmrc` (preference
  order: `.node-version` first). Strips `v` prefix.
- `extract_major()` handles: bare (`5.3.1`), caret (`^5.3.1`), tilde (`~5.3.1`),
  inequality (`>=5.3.1`, `<=5.3.1`, `>5`, `<5`).
- `dependency_version()` reads `devDependencies[name]` from package.json.
  Returns empty string if key absent.
- `check_stack_consistency()` compares major versions of named packages across
  two package.json files. Returns namedtuple with `ok` bool and `mismatches` list.
- CLI mode works for all subcommands.
- ≥90% line coverage.

**Commit boundary:** Single commit: `feat(dev/lib): add package_meta module`.

**Dependencies:** None (parallel with 2.1.1).

---

#### Chunk 2.1.3: repo_lock.py

**Intent:** Create a shared repo lock module with Python context manager and
Bash-callable CLI.

**Scope boundary:**
- Create `dev/lib/repo_lock.py` with `RepoLock` class (context manager),
  `acquire_lock()`, `release_lock()` functional wrappers, and CLI entry point.
- Create `tests/unit/test_repo_lock.py`.
- Do NOT modify devctl, govctl-executor, or metricsctl.

**Files to touch:**
- `dev/lib/repo_lock.py` (create)
- `tests/unit/test_repo_lock.py` (create)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_repo_lock.py -v
# All tests pass
python3 dev/lib/repo_lock.py status
# Prints "unlocked" or "locked" depending on current state
```

**Acceptance criteria:**
- `RepoLock` context manager acquires `fcntl.LOCK_EX` on the lock file.
- Reentry guard: if `DEVCTL_GLOBAL_LOCK_HELD=1` in env, skip acquisition
  (return immediately, context manager is a no-op).
- On acquisition, sets `DEVCTL_GLOBAL_LOCK_HELD=1` in `os.environ`.
- On release, unsets `DEVCTL_GLOBAL_LOCK_HELD` from `os.environ`.
- Default lock file: `/tmp/nightfall-repo.lock`.
- Default timeout: 300 seconds. On timeout: raise exception (Python) or
  exit non-zero with message to stderr (CLI).
- Interop: Python `fcntl.flock(LOCK_EX)` blocks Bash `flock` and vice versa
  on the same file (documented, not unit-testable — verified manually or
  in integration tests).
- CLI subcommands: `acquire`, `release`, `status`.
- ≥90% line coverage.

**Commit boundary:** Single commit: `feat(dev/lib): add repo_lock module`.

**Dependencies:** None (parallel with 2.1.1, 2.1.2).

---

#### Chunk 2.1.4: source_fingerprint.py

**Intent:** Create a shared module for deterministic source file fingerprinting
and build stamp generation.

**Scope boundary:**
- Create `dev/lib/source_fingerprint.py` with `compute_fingerprint()`,
  `write_build_stamp()`, and CLI entry point.
- Create `tests/unit/test_source_fingerprint.py`.
- Create test fixtures under `tests/fixtures/source_fingerprint/` with
  known directory trees and pre-computed expected hashes.
- Do NOT modify build-metrics-dashboard, metricsctl, or poller_runner.

**Files to touch:**
- `dev/lib/source_fingerprint.py` (create)
- `tests/unit/test_source_fingerprint.py` (create)
- `tests/fixtures/source_fingerprint/` (create directory + fixture files)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_source_fingerprint.py -v
# All tests pass
python3 dev/lib/source_fingerprint.py compute tests/fixtures/source_fingerprint/sample/
# Output matches expected hash
```

**Acceptance criteria:**
- `compute_fingerprint()` enumerates matching files via `sorted()` by relative
  path. Hash includes relative path + file content for each file.
- `exclude_dirs` filtering works (e.g., `node_modules`, `.svelte-kit` excluded).
- `write_build_stamp()` writes JSON with `fingerprint` (hex) and `timestamp`
  (ISO-8601 UTC) fields.
- Deterministic: same directory → same hash across runs.
- CLI subcommands: `compute`, `stamp`.
- ≥90% line coverage.

**Commit boundary:** Single commit: `feat(dev/lib): add source_fingerprint module`.

**Dependencies:** None (parallel with 2.1.1–2.1.3).

---

#### Chunk 2.1.5: venv_bootstrap.py

**Intent:** Create a shared venv bootstrap module for Python CLI tools.

**Scope boundary:**
- Create `dev/lib/venv_bootstrap.py` with `ensure_venv()` and
  `is_running_in_venv()`.
- Create `tests/unit/test_venv_bootstrap.py`.
- Do NOT modify metricsctl or any other script.

**Files to touch:**
- `dev/lib/venv_bootstrap.py` (create)
- `tests/unit/test_venv_bootstrap.py` (create)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_venv_bootstrap.py -v
# All tests pass
```

**Acceptance criteria:**
- `ensure_venv()` detects interpreter mismatch (current Python vs. repo `.venv`
  Python) and calls `os.execve` with correct arguments.
- Reentry guard: if guard env var is set, return silently (no re-exec).
- If venv does not exist, return silently (graceful degradation).
- No CLI entry point — this module is import-only.
- Unit tests mock `os.execve` to verify behavior without actually re-execing.
- ≥90% line coverage.

**Commit boundary:** Single commit: `feat(dev/lib): add venv_bootstrap module`.

**Dependencies:** None (parallel with 2.1.1–2.1.4).

---

### Sub-phase 2.2 — devctl Integration

---

#### Chunk 2.2.1: devctl uses manifest_hash.py

**Intent:** Replace devctl's Bash hash functions with calls to the shared
manifest_hash module.

**Scope boundary:**
- Modify `dev/bin/devctl`: replace `compute_manifest_hash()`,
  `read_hash_file()`, `compare_manifest_hash()` (lines 66–97) with subprocess
  calls to `python3 dev/lib/manifest_hash.py`.
- Callers of these functions (`_recalculate_host_hash`, `_drift_check_stack`,
  `_assert_stack_no_drift`) updated to use the new invocation.
- Do NOT change any other devctl function.
- Do NOT change exit codes or log format.

**Files to touch:**
- `dev/bin/devctl` (modify — replace 3 Bash functions with subprocess calls)

**Deterministic validation:**
```bash
# Run the existing devctl contracts test to verify no behavior change
python3 -m pytest tests/unit/test_devctl_contracts.py -v
# Manual: compute hash via old and new path, compare outputs
```

**Acceptance criteria:**
- devctl's hash-related subcommands produce identical results before/after.
- The three replaced Bash functions are removed (not commented out).
- No new environment variables or flags.
- test_devctl_contracts.py passes unchanged.

**Commit boundary:** Single commit: `refactor(devctl): use manifest_hash module`.

**Dependencies:** 2.1.1.

---

#### Chunk 2.2.2: devctl uses package_meta.py

**Intent:** Replace devctl's inline Python heredocs for dependency parsing
and version checking with calls to the shared package_meta module.

**Scope boundary:**
- Modify `dev/bin/devctl`: replace `_json_dependency_version()` (lines 145–161,
  inline Python) with `python3 dev/lib/package_meta.py dep-version`.
- Replace `assert_web_stack_major_consistency()` (lines 162–199, inline Python)
  with `python3 dev/lib/package_meta.py check-consistency`.
- Replace `get_node_version()` and `extract_major_from_semver()` (lines 115–144)
  with `python3 dev/lib/package_meta.py node-version` where appropriate.
- Do NOT change any other devctl function.

**Files to touch:**
- `dev/bin/devctl` (modify — replace 4 functions/heredocs)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_devctl_contracts.py -v
# Manual: run devctl ensure-stack-ready and verify log output unchanged
```

**Acceptance criteria:**
- All inline `python3 - <<'PY'` heredocs related to package metadata are removed.
- devctl's behavior (exit codes, log output, error messages) is unchanged.
- test_devctl_contracts.py passes unchanged.

**Commit boundary:** Single commit: `refactor(devctl): use package_meta module`.

**Dependencies:** 2.1.2.

---

### Sub-phase 2.3 — metricsctl Integration

---

#### Chunk 2.3.1: metricsctl uses repo_lock.py

**Intent:** Replace metricsctl's private `_repo_lock()` context manager with
an import from the shared repo_lock module.

**Scope boundary:**
- Modify `metricsctl`: replace `_repo_lock()` (lines 74–87) with
  `from dev.lib.repo_lock import RepoLock`.
- Add `sys.path` manipulation at top of metricsctl to import from `dev/lib/`
  (consistent with how govctl modules are invoked).
- Update `cmd_generate_dashboard()` to use `RepoLock()` context manager.
- Do NOT change any other metricsctl function.

**Files to touch:**
- `metricsctl` (modify — replace ~15 lines)

**Deterministic validation:**
```bash
# Verify metricsctl still works
python3 metricsctl --help
# Verify lock behavior: run generate-dashboard, confirm no deadlock
# Run existing metricsctl tests if available
```

**Acceptance criteria:**
- `cmd_generate_dashboard()` acquires the lock via `RepoLock()`.
- `DEVCTL_GLOBAL_LOCK_HELD=1` is set before the devctl subprocess call
  (preventing deadlock) — same behavior as before.
- `_repo_lock()` private function is removed from metricsctl.
- metricsctl --help output unchanged.
- All metricsctl subcommands work identically.

**Commit boundary:** Single commit: `refactor(metricsctl): use shared repo_lock`.

**Dependencies:** 2.1.3.

---

#### Chunk 2.3.2: metricsctl uses venv_bootstrap.py

**Intent:** Replace metricsctl's private `_maybe_reexec_venv()` with an import
from the shared venv_bootstrap module.

**Scope boundary:**
- Modify `metricsctl`: replace `_maybe_reexec_venv()` (lines 23–48) with:
  ```python
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent / "dev" / "lib"))
  from venv_bootstrap import ensure_venv
  ensure_venv(Path(__file__))
  ```
- Do NOT change any other metricsctl function.

**Files to touch:**
- `metricsctl` (modify — replace ~25 lines with ~5 lines)

**Deterministic validation:**
```bash
# Run from system Python — should re-exec into venv
python3 metricsctl --help
# Run from venv Python — should skip re-exec
.venv/bin/python metricsctl --help
# Both should produce identical help output
```

**Acceptance criteria:**
- metricsctl launches correctly from both system Python and venv Python.
- `_maybe_reexec_venv()` private function is removed from metricsctl.
- No infinite re-exec loops (verified by reentry guard).
- metricsctl --help output unchanged.

**Commit boundary:** Single commit: `refactor(metricsctl): use shared venv_bootstrap`.

**Dependencies:** 2.1.5.

---

### Sub-phase 2.4 — Command-Surface Refinement + Manifest Update

---

#### Chunk 2.4.1: govctl preflights use shared modules

**Intent:** Replace reimplemented logic in govctl preflights with calls to
shared modules.

**Scope boundary:**
- Modify `dev/lib/govctl-preflights.sh`: where the `stack-drift-free` check
  reimplements manifest hashing, replace with a call to
  `python3 dev/lib/manifest_hash.py compare`.
- Where the `node-version-match` check parses `.node-version` independently,
  replace with a call to `python3 dev/lib/package_meta.py node-version`.
- Do NOT change preflight result format (exit codes, output messages).

**Files to touch:**
- `dev/lib/govctl-preflights.sh` (modify)

**Deterministic validation:**
```bash
python3 -m pytest tests/unit/test_govctl_preflights.sh -v 2>&1 || true
# Run govctl check on a target that uses these preflights
./dev/bin/govctl check dev.stack-ready.webui
# Verify output is structurally unchanged
```

**Acceptance criteria:**
- `stack-drift-free` preflight delegates hash computation to manifest_hash.py.
- `node-version-match` preflight delegates version reading to package_meta.py.
- All 41 preflight tests pass unchanged.
- No change to preflight JSON output schema.

**Commit boundary:** Single commit: `refactor(govctl): preflights use shared modules`.

**Dependencies:** 2.2.1, 2.2.2 (devctl integration must be done first so hash
outputs are known-consistent).

---

#### Chunk 2.4.2: build-metrics-dashboard uses source_fingerprint.py

**Intent:** Replace inline Python fingerprinting in build-metrics-dashboard
with calls to the shared source_fingerprint module.

**Scope boundary:**
- Modify `dev/bin/build-metrics-dashboard`: replace the inline Python heredoc
  (lines ~61–88) that computes source fingerprints with
  `python3 dev/lib/source_fingerprint.py stamp`.
- Do NOT change the build logic, output directory, or npm commands.

**Files to touch:**
- `dev/bin/build-metrics-dashboard` (modify — replace ~30 lines of inline Python)

**Deterministic validation:**
```bash
# Verify stamp output format is unchanged
python3 dev/lib/source_fingerprint.py stamp webui/dashboard/ /tmp/test-stamp.json
cat /tmp/test-stamp.json
# Should have fingerprint + timestamp fields
```

**Acceptance criteria:**
- build-metrics-dashboard produces identical build stamps before/after.
- Inline Python heredoc for fingerprinting is removed.
- Build still succeeds end-to-end when run via govctl.

**Commit boundary:** Single commit: `refactor(build-metrics-dashboard): use source_fingerprint module`.

**Dependencies:** 2.1.4.

---

#### Chunk 2.4.3: Dead code removal

**Intent:** Remove replaced Bash functions from devctl and replaced private
functions from metricsctl that are now dead code.

**Scope boundary:**
- Verify all callers have been migrated (Chunks 2.2.1, 2.2.2, 2.3.1, 2.3.2).
- Remove dead functions from devctl:
  - `compute_manifest_hash()`, `read_hash_file()`, `compare_manifest_hash()`
  - `_json_dependency_version()` inline heredoc
  - `assert_web_stack_major_consistency()` inline heredoc
  - `get_node_version()`, `extract_major_from_semver()` (if fully replaced)
- Confirm no remaining callers via grep.
- Do NOT remove any function that still has a caller.

**Files to touch:**
- `dev/bin/devctl` (modify — remove dead functions)

**Deterministic validation:**
```bash
# Verify no remaining callers
grep -n 'compute_manifest_hash\|read_hash_file\|compare_manifest_hash' dev/bin/devctl
# Should return zero results (only the removed function definitions)
grep -n '_json_dependency_version\|assert_web_stack_major_consistency' dev/bin/devctl
# Should return zero results
# Run full test suite
python3 -m pytest tests/unit/test_devctl_contracts.py -v
```

**Acceptance criteria:**
- All replaced functions are removed.
- No grep hits for removed function names in devctl (except comments if any).
- All existing tests pass.

**Commit boundary:** Single commit: `chore(devctl): remove dead code after module extraction`.

**Dependencies:** 2.2.1, 2.2.2, 2.4.1 (all consumers migrated first).

---

#### Chunk 2.4.4: govctl manifest update

**Intent:** Update govctl-targets.yaml to leverage the shared modules for
reduced redundancy in orchestrated runs.

**Scope boundary:**
- Review each target in `dev/govctl-targets.yaml` that calls devctl or
  build-metrics-dashboard.
- Where govctl preflights now provide the same checks as devctl internal
  validation (via shared modules), document the overlap in manifest comments.
- Update `metrics.build.dashboard` target command if build-metrics-dashboard
  no longer needs `devctl ensure-stack-ready` to be called separately
  (because the preflight + shared module handle drift detection).
- Do NOT change govctl executor, resolver, or CLI code.

**Files to touch:**
- `dev/govctl-targets.yaml` (modify — command adjustments + comments)

**Deterministic validation:**
```bash
./dev/bin/govctl list
# All 21 targets and 7 groups still listed
./dev/bin/govctl run --dry-run metrics.build.dashboard
# Execution plan is correct
python3 -m pytest tests/unit/test_govctl_cli.sh -v 2>&1 || true
# All CLI tests pass
```

**Acceptance criteria:**
- `govctl list` output unchanged (all targets/groups present).
- Dry-run execution plans are correct.
- All 53 CLI tests pass.
- Comments in manifest document why certain redundant checks are safe to skip.

**Commit boundary:** Single commit: `refactor(govctl): update manifest for shared modules`.

**Dependencies:** 2.4.1, 2.4.2 (preflights and build script already using shared modules).

---

## E) Command-Surface Changes — Disposition of Original Chunks 8–11

The original Phase 2 (Chunks 8–11) proposed adding skip flags to tolerate
redundant subprocess calls. The new design eliminates the redundancy at the
library level instead:

| Original Chunk | Proposal | Disposition | Rationale |
|---------------|----------|-------------|-----------|
| **8: devctl skip flags** (`DEVCTL_SKIP_CONSISTENCY_CHECK`, `DEVCTL_SKIP_NODE_VERSION_CHECK`) | Add env vars to skip validation passes | **Dropped** | With `manifest_hash.py` and `package_meta.py` as shared modules, govctl preflights and devctl call the same code. No redundant re-computation to skip. |
| **9: build-metrics-dashboard --skip-ensure-ready** | Add flag to bypass embedded devctl call | **Partially absorbed** | Chunk 2.4.2 replaces the inline fingerprinting. The `devctl ensure-stack-ready` call may still exist but is idempotent. If govctl's dependency graph guarantees stack readiness before the build target runs, the devctl call becomes a fast no-op (hash match → no work). Skip flag unnecessary. |
| **10: metricsctl --skip-drift-preflight** | Add flag to suppress devctl subprocess call | **Deferred** | The drift preflight function stays as-is per metrics-ctl-design.md §5.3 ("Phase 1: do not change"). When manifest_hash.py is integrated, the function can be refined to do a direct hash check first and only call devctl on mismatch (metrics-ctl-design.md Phase 3). This is a future optimization, not Phase 2 scope. |
| **11: govctl manifest update for skip flags** | Pass skip flags in target commands | **Replaced** by Chunk 2.4.4 | Manifest updates target commands to reflect shared-module integration instead of skip flags. |

**Net effect:** Three skip-flag additions are replaced by five shared modules.
The modules provide stronger guarantees (single source of truth) and avoid the
"silent failure" risk that skip flags introduce (where an operator sets a skip
flag and misses a genuine problem).

---

## F) Risk Notes

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Hash divergence** — Python module produces different hash than devctl Bash for edge cases | Medium | High | Fixture-based tests with pre-computed hashes from both implementations. Run equivalence tests before removing Bash functions (Chunk 2.4.3 is last). |
| **Lock interop regression** — Python fcntl.flock and Bash flock on same file behave differently on some filesystems | Low | High | Both use advisory locking on the same file. Integration test (manual): Python acquire → Bash flock blocks. Document that lock file must be on a local filesystem (not NFS). |
| **Import path fragility** — `sys.path` manipulation to import from `dev/lib/` breaks if directory structure changes | Medium | Medium | Each module has a `__main__` guard that works as `python3 dev/lib/module.py` (argv-based, no import needed). Python imports use a two-line preamble that computes path from `__file__`. |
| **Semver parsing edge cases** — `extract_major()` fails on unusual version strings in wild package.json files | Low | Low | Test with all formats seen in the repo's actual package.json files. Function is defensive: returns -1 or raises ValueError on unparseable input. |
| **Venv re-exec loop** — Bug in reentry guard causes infinite os.execve | Low | High | Guard var is set before execve. Unit test explicitly verifies: guard set → no execve. |
| **Partial migration state** — Some callers migrated, some not, for same function | Medium | Medium | Each chunk has a clear "files to touch" list. Chunk 2.4.3 (dead code removal) runs grep to verify zero remaining callers before deletion. |

---

## G) Execution Prompt for Implementation Agents

You are implementing Phase 2 of the nightfall-photo-ingress build tooling
refactoring. Follow these rules strictly:

1. **Implement exactly ONE chunk at a time.** Complete the chunk, run its
   deterministic validation, and confirm all acceptance criteria pass before
   moving to the next chunk.

2. **Respect the dependency graph.** Do not start a chunk until all its
   listed dependencies are fully committed. The dependency graph is:

   ```
   Sub-phase 2.1 (all independent, can be done in any order):
     2.1.1 (manifest_hash)
     2.1.2 (package_meta)
     2.1.3 (repo_lock)
     2.1.4 (source_fingerprint)
     2.1.5 (venv_bootstrap)

   Sub-phase 2.2 (depends on 2.1):
     2.2.1 → depends on 2.1.1
     2.2.2 → depends on 2.1.2

   Sub-phase 2.3 (depends on 2.1):
     2.3.1 → depends on 2.1.3
     2.3.2 → depends on 2.1.5

   Sub-phase 2.4 (depends on 2.2 and 2.3):
     2.4.1 → depends on 2.2.1, 2.2.2
     2.4.2 → depends on 2.1.4
     2.4.3 → depends on 2.2.1, 2.2.2, 2.4.1
     2.4.4 → depends on 2.4.1, 2.4.2
   ```

3. **Make minimal diffs.** Each chunk changes only the files listed in
   "Files to touch". Do not refactor, clean up, or "improve" code outside
   the chunk scope.

4. **Run deterministic validation after every chunk.** The validation
   commands are listed in each chunk. If validation fails, fix the issue
   within the chunk scope before committing.

5. **Use the exact commit message format.** Each chunk specifies a commit
   boundary with a commit message. Use that message.

6. **Read the design documents before implementing.** The authoritative
   specifications for each module are in:
   - `design/infra/devctl-design.md` — sections §6.1–§6.4
   - `design/infra/metrics-ctl-design.md` — sections §6.1–§6.3

   If this plan and a design document disagree, the design document wins.

7. **Do not add features not specified.** Do not add logging, type hints
   (beyond what the design specifies), docstrings (unless the function
   signature is non-obvious), or error handling for scenarios that the
   design does not mention.

8. **Test fixtures are known-good data.** When creating fixture files for
   hash equivalence tests, first compute the expected hash using the existing
   Bash implementation, then encode that expected value in the test. Do not
   compute expected values from your own code.

9. **After completing all chunks in a sub-phase**, run the full test suite:
   ```bash
   python3 -m pytest tests/unit/ -v
   ```
   All 147+ tests must pass. If a pre-existing test breaks, you introduced a
   regression — fix it before proceeding.

10. **Stop after each chunk and report.** Provide: chunk ID, files changed,
    test results, acceptance criteria status (pass/fail per criterion).
