# metricsctl Consolidation — RCA Analysis & 3-Phase Migration Plan

**Status:** analysis complete — awaiting Phase 1 approval  
**Date:** 2026-04-10  
**Owner:** Systems Engineering  
**Issue:** [#8 — Plan: metricsctl consolidation to dev/bin canonical surface (deferred)](https://github.com/artherion77/nightfall-photo-ingress/issues/8)  
**See also:** [metrics-ctl-design.md](metrics-ctl-design.md), [devctl-design.md](devctl-design.md), [build-governor-design.md](build-governor-design.md)

---

## Table of Contents

1. [Summary](#1-summary)
2. [Caller Matrix](#2-caller-matrix)
3. [Path Resolution Risk Map](#3-path-resolution-risk-map)
4. [Compatibility Surface Comparison](#4-compatibility-surface-comparison)
5. [RCA Matrix](#5-rca-matrix)
6. [3-Phase Migration Plan](#6-3-phase-migration-plan)
7. [Migration Checklist](#7-migration-checklist)

---

## 1. Summary

This document provides the deep follow-up analysis called for in Issue #8.
The consolidation proposal is:

- Move Python implementation from `./metricsctl` (repo root) to `./dev/lib/metricsctl.py`
- Merge `./dev/bin/metrics-runner` into `./dev/bin/metricsctl`
- Keep `./dev/bin/metricsctl` as the sole canonical operator entrypoint

The fast caller/risk review in Issue #8 identified three high-level blockers — path
resolution coupling, command-surface compatibility, and caller-graph stabilization.
This document expands each into a full analysis with evidence, an RCA matrix, a formal
3-phase migration plan, and an actionable checklist for a future implementation agent.

**Key finding:** A naive file move is not safe. Eight critical path resolutions in
`./metricsctl` are anchored to `Path(__file__).resolve().parent`. All eight break if the
file is relocated without first introducing a location-independent root-finding helper.
The migration must proceed in the order defined by the phases below.

---

## 2. Caller Matrix

### 2.1 Direct callers of `./metricsctl` (repo-root Python script)

| Caller | File | Invocation | Commands Used |
|--------|------|------------|---------------|
| govctl — `metrics.collect.backend` | `dev/govctl-targets.yaml:209–215` | `"$metrics_python" ./metricsctl collect-backend` | `collect-backend` |
| govctl — `metrics.status` | `dev/govctl-targets.yaml:218–228` | `"$metrics_python" ./metricsctl status` | `status` |
| govctl — `metrics.run-now` | `dev/govctl-targets.yaml:230–240` | `"$metrics_python" ./metricsctl run-now` | `run-now` |
| govctl — `metrics.collect.frontend` | `dev/govctl-targets.yaml:242–252` | `"$metrics_python" ./metricsctl collect-frontend` | `collect-frontend` |
| govctl — `metrics.aggregate` | `dev/govctl-targets.yaml:254–264` | `"$metrics_python" ./metricsctl aggregate` | `aggregate` |
| govctl — `metrics.generate.dashboard` | `dev/govctl-targets.yaml:266–276` | `"$metrics_python" ./metricsctl generate-dashboard` | `generate-dashboard` |
| govctl — `metrics.publish` | `dev/govctl-targets.yaml:278–288` | `"$metrics_python" ./metricsctl publish` | `publish` |
| govctl — `metrics.install` | `dev/govctl-targets.yaml:290–300` | `"$metrics_python" ./metricsctl install` | `install` |
| govctl — `metrics.stop` | `dev/govctl-targets.yaml:302–312` | `"$metrics_python" ./metricsctl stop` | `stop` |
| `dev/bin/metricsctl` bash wrapper | `dev/bin/metricsctl:7` | `exec "$REPO_ROOT/metricsctl" "$@"` | all (pass-through) |

### 2.2 Direct callers of `./dev/bin/metricsctl` (bash wrapper)

| Caller | File | Invocation | Commands Used |
|--------|------|------------|---------------|
| `dev/bin/metrics-runner` | `dev/bin/metrics-runner:49,53,57` | `exec "$METRICSCTL" run-now\|status\|publish` | `run-now`, `status`, `publish` |
| poller_runner (systemd unit gen) | `metrics/runner/poller_runner.py:263` | `{repo_root}/dev/bin/metricsctl run-now` embedded in generated `ExecStart` | `run-now` |
| Static systemd template | `metrics/systemd/nightfall-metrics-poller.service:9` | `ExecStart=.../dev/bin/metricsctl run-now` | `run-now` |
| MCP model mappings (via govctl) | `.mcp/model.json:203–219` | `./dev/bin/govctl run metrics.*` → govctl calls `./metricsctl` | `status`, `run-now`, `publish`, `install`, `stop` (indirectly) |
| `test_mcp_metrics_tasks.py` | `tests/unit/test_mcp_metrics_tasks.py:40–44` | assertion: `mappings["metrics.*"] == ["./dev/bin/govctl run metrics.* --json"]` | all MCP metrics mappings validated |
| docs (non-executable) | `docs/development-handbook.md:58` | documentation reference | N/A |
| design docs (non-executable) | `design/infra/metrics-ctl-design.md` (multiple) | documentation/design references | N/A |

### 2.3 Direct callers of `./dev/bin/metrics-runner`

| Caller | File | Invocation | Commands |
|--------|------|------------|----------|
| Operator (manual) | N/A | `metrics-runner run [--max-retries N] [--timeout-seconds N]` | `run` → `run-now` |
| Operator (manual) | N/A | `metrics-runner status` | `status` |
| Operator (manual) | N/A | `metrics-runner publish-github` | `publish` |
| Design/planning docs | `design/infra/metrics-ctl-design.md`, `planning/` | documentation/workflow references | `run`, `status`, `publish-github` |

### 2.4 Call-chain summary

```
Operator / CI
  ├── govctl run metrics.*        → "$metrics_python" ./metricsctl <cmd>  [9 targets; govctl-targets.yaml]
  ├── MCP → govctl run metrics.*  → "$metrics_python" ./metricsctl <cmd>  [5 mappings; .mcp/model.json]
  ├── dev/bin/metricsctl          → ./metricsctl "$@"                     [bash pass-through wrapper]
  ├── dev/bin/metrics-runner      → dev/bin/metricsctl <cmd>              [operator alias shim; 3 verbs]
  └── systemd ExecStart           → dev/bin/metricsctl run-now            [generated by poller_runner.py]
```

**Key inconsistency:** govctl targets call `./metricsctl` directly while systemd unit
generation and `metrics-runner` both route through `./dev/bin/metricsctl`. This split is
the primary source of operator confusion about the canonical entrypoint and the primary
risk driver for any relocation.

---

## 3. Path Resolution Risk Map

### 3.1 Current path-derivation patterns in `./metricsctl`

**DEV_LIB bootstrap (lines 18–24):**
```python
DEV_LIB = Path(__file__).resolve().parent / "dev" / "lib"
# Assumption: __file__ is at repo root
# If moved to dev/lib/: resolves to <repo>/dev/lib/dev/lib  ← WRONG
```

**`_repo_root()` function (lines 75–77):**
```python
def _repo_root() -> Path:
    return Path(__file__).resolve().parent
    # Assumption: script file is at repo root
    # If moved to dev/lib/: returns <repo>/dev/lib  ← WRONG
```

**`venv_bootstrap.ensure_venv()` (dev/lib/venv_bootstrap.py:35–36):**
```python
script = Path(script_path).resolve()
repo_root = script.parent   # assumption: script.parent IS repo root
venv_python = repo_root / venv_name / "bin" / "python"
# If script is in dev/lib/: looks for <repo>/dev/lib/.venv  ← WRONG
```

### 3.2 All paths that break on a naive move to `dev/lib/metricsctl.py`

| Path expression | Current resolution | Resolution after naive move | Breaks? |
|-----------------|--------------------|-----------------------------|---------|
| `DEV_LIB = Path(__file__).parent / "dev" / "lib"` | `<repo>/dev/lib` | `<repo>/dev/lib/dev/lib` | **YES** |
| `_repo_root()` → all derived paths below | `<repo>` | `<repo>/dev/lib` | **YES** |
| `root / "artifacts" / "metrics" / "latest"` | `<repo>/artifacts/metrics/latest` | `<repo>/dev/lib/artifacts/…` | **YES** |
| `root / "metrics" / "runner"` | `<repo>/metrics/runner` | `<repo>/dev/lib/metrics/runner` | **YES** |
| `root / "metrics" / "systemd"` | `<repo>/metrics/systemd` | `<repo>/dev/lib/metrics/systemd` | **YES** |
| `root / "metrics" / "state"` | `<repo>/metrics/state` | `<repo>/dev/lib/metrics/state` | **YES** |
| `root / "metrics" / "output"` | `<repo>/metrics/output` | `<repo>/dev/lib/metrics/output` | **YES** |
| `root / "dev" / "bin" / "devctl"` (preflight) | `<repo>/dev/bin/devctl` | `<repo>/dev/lib/dev/bin/devctl` | **YES** |
| `.venv` lookup via `ensure_venv(Path(__file__))` | `<repo>/.venv` | `<repo>/dev/lib/.venv` | **YES** |

All 8 critical path resolutions break. A naive move is not safe.

### 3.3 Required refactors for location-independence

1. **Introduce `find_repo_root(sentinel="pyproject.toml")`** in `dev/lib/` — walks up from
   `Path.cwd()` until the sentinel file is found (cap walk depth at 12 levels to avoid
   run-away traversal on misconfigured machines). Falls back to `Path(__file__).resolve().parent`
   chain if sentinel not found within depth limit, with a logged warning.

2. **Add `repo_root: Path | None = None` parameter to `venv_bootstrap.ensure_venv()`** —
   when `repo_root` is provided, use it directly for `.venv` location instead of deriving
   from `script.parent`. Existing callers that omit the parameter retain current behavior
   (backward-compatible).

3. **Replace `_repo_root()` implementation** — use `find_repo_root()` instead of
   `Path(__file__).resolve().parent`.

4. **Replace `DEV_LIB` bootstrap line** — derive via `find_repo_root()` result so it is
   location-independent from day one.

---

## 4. Compatibility Surface Comparison

### 4.1 `metricsctl` command surface (full CLI, 20 subcommands)

| Command | Module | Flags | Aliased in `metrics-runner` |
|---------|--------|-------|------------------------------|
| `init-module1` | M1 | `--run-id` | — |
| `validate-module1` | M1 | — | — |
| `paths` | — | — | — |
| `collect-backend` | M2 | `--run-id`, `--pytest-target`, `--skip-pytest` | — |
| `collect-frontend` | M3 | `--run-id` | — |
| `aggregate` | M4 | `--run-id` | — |
| `generate-dashboard` | M5 | `--run-id` | — |
| `install` | M6 | `--frequency-minutes`, `--max-history-runs` | — |
| `reconfigure` | M6 | `--frequency-minutes`, `--max-history-runs` | — |
| `start` | M6 | — | — |
| `stop` | M6 | — | — |
| `status` | M6 | — | `metrics-runner status` |
| `run-now` | M6 | `--max-retries`, `--timeout-seconds` | `metrics-runner run` |
| `uninstall` | M6 | — | — |
| `publish` | M7 | — | `metrics-runner publish-github` |
| `retention-prune` | M8 | `--max-history-runs` | — |
| `extensions-status` | M8 | — | — |
| `cleanup-runtime` | — | `--include-history` | — |
| `dashboard-build-stamp` | — | — | — |
| `thumbnail-gc` | — | `--config` | — |

### 4.2 `metrics-runner` command surface (operator-facing aliases)

| Command | Maps to | Flags forwarded |
|---------|---------|-----------------|
| `run [--max-retries N] [--timeout-seconds N]` | `metricsctl run-now` | Yes — `$@` pass-through |
| `status` | `metricsctl status` | No flags |
| `publish-github` | `metricsctl publish` | No flags |
| `help` / `-h` / `--help` | usage text | N/A |

### 4.3 Compatibility requirements

1. **Verb `run` → `run-now`:** The alias `run` does not exist in `metricsctl`'s CLI. Any operator
   script calling `metricsctl run` (without going through `metrics-runner`) will receive a
   parse error today. The mapping must be documented; optionally a hidden alias can be added.

2. **Verb `publish-github` → `publish`:** The alias `publish-github` does not exist in
   `metricsctl`'s CLI. Same risk as above.

3. **Flag pass-through:** `metrics-runner run --max-retries 2 --timeout-seconds 2400` correctly
   forwards both flags through `exec "$METRICSCTL" run-now "$@"`. This must continue to work.

4. **Must preserve during migration:** All three `metrics-runner` verbs (`run`, `status`,
   `publish-github`) must remain functional through Phases 1 and 2. Phase 3 decides removal.

### 4.4 Deprecatable behaviors

- The `metrics-runner` script itself (replaceable by a shim or equivalent `metricsctl` aliases)
- The `publish-github` verb (alias for `publish`; can be deprecated with clear docs)
- The `run` verb (alias for `run-now`; can be deprecated with clear docs)
- `./metricsctl` at repo root (replaceable by deprecation shim after Phase 2)

---

## 5. RCA Matrix

| # | Symptom | Root Cause | Evidence | Impact | Required Change | Risk |
|---|---------|------------|----------|--------|-----------------|------|
| 1 | Moving `./metricsctl` to `dev/lib/` breaks all artifact path resolution | `_repo_root()` anchors to `Path(__file__).resolve().parent` | `metricsctl:77` | All 9 govctl targets fail; artifact, state, systemd paths resolve to non-existent locations | Introduce `find_repo_root()` sentinel helper; replace `_repo_root()` | **HIGH** |
| 2 | Moving `./metricsctl` breaks venv bootstrap | `venv_bootstrap.ensure_venv()` derives `.venv` location from `script.parent` | `venv_bootstrap.py:36` | Script runs without venv; wrong Python or missing packages | Add explicit `repo_root` parameter to `ensure_venv()` | **HIGH** |
| 3 | Moving `./metricsctl` breaks devctl preflight invocation | `_devctl_dashboard_drift_preflight()` constructs devctl path via `_repo_root()` | `metricsctl:62` | Dashboard generation fails; devctl not found | Fix `_repo_root()` first (RCA #1 blocks) | **HIGH** |
| 4 | Moving `./metricsctl` breaks `DEV_LIB` sys.path injection | `DEV_LIB = Path(__file__).resolve().parent / "dev" / "lib"` assumes script at repo root | `metricsctl:18` | `venv_bootstrap` and `repo_lock` imports fail at startup | Make `DEV_LIB` derivation location-independent via sentinel root | **HIGH** |
| 5 | Removing `metrics-runner` breaks operator workflows | `metrics-runner` provides `run`, `status`, `publish-github` verbs not present in `metricsctl` | `dev/bin/metrics-runner:46–67` | Operators and scripts calling `metrics-runner run` lose their entrypoint | Keep shim or add `run`/`publish-github` aliases to `metricsctl`; doc migration | **MEDIUM** |
| 6 | Split call surfaces cause inconsistent tooling guidance | govctl calls `./metricsctl` directly; systemd/MCP/metrics-runner use `./dev/bin/metricsctl` | `govctl-targets.yaml:211–309` vs `poller_runner.py:263` | Operator confusion; relocation breaks govctl but not systemd | Standardize all callers to single canonical surface before any move | **MEDIUM** |
| 7 | govctl targets bypass the canonical `dev/bin/metricsctl` wrapper | 9 govctl targets invoke `"$metrics_python" ./metricsctl` directly | `govctl-targets.yaml` (9 targets) | Relocating `./metricsctl` silently breaks all govctl metrics targets | Update 9 govctl targets to use `./dev/bin/metricsctl` | **MEDIUM** |
| 8 | MCP metrics tasks break if govctl targets break | MCP routes through govctl which calls `./metricsctl` directly | `.mcp/model.json:203–219` + `govctl-targets.yaml` | 5 MCP metrics task mappings stop working | Fix govctl targets (RCA #7); MCP model itself needs no change | **MEDIUM** |
| 9 | Systemd unit generation hardcodes `dev/bin/metricsctl` | `poller_runner.py:263` embeds `{repo_root}/dev/bin/metricsctl run-now` | `metrics/runner/poller_runner.py:263` | Reinstalling poller after a second `dev/bin/metricsctl` relocation would produce broken units | No action now; verify after Phase 2 that canonical entrypoint path is stable | **LOW** |
| 10 | `publish-github` does not exist as a `metricsctl` subcommand | `metrics-runner` maps the alias; `metricsctl` has no `publish-github` verb | `dev/bin/metrics-runner:55–58` | Operators invoking `metricsctl publish-github` directly get an unhelpful parse error | Document the mapping; optionally add hidden alias in `metricsctl` | **LOW** |

---

## 6. 3-Phase Migration Plan

---

### Phase 1 — Preparation & Compatibility Layer

**Goals:**
- Make all path resolution in `./metricsctl` explicit and independent of script location
- Standardize all callers to use `./dev/bin/metricsctl` as the single canonical entrypoint
- Define compatibility shim contract for `metrics-runner`
- Add regression coverage for path resolution and caller routing

**Non-goals:**
- Do not move any files
- Do not remove `metrics-runner`
- Do not change any operator-visible CLI surface

**Preconditions:**
- This analysis document reviewed and approved by maintainer
- Existing test suite passes with no open regressions
- No outstanding govctl target or MCP mapping failures

**Work items:**

1. Add `find_repo_root(sentinel: str = "pyproject.toml", max_depth: int = 12) -> Path`
   to `dev/lib/` — walks up from `Path.cwd()` until the sentinel file is found; raises
   `RuntimeError` if not found within depth limit.

2. Add `repo_root: Path | None = None` parameter to `venv_bootstrap.ensure_venv()`;
   when provided, derive `.venv` from it instead of `script.parent`. Default `None`
   preserves existing behavior for current callers.

3. Update `./metricsctl` `_repo_root()` to call `find_repo_root()` instead of
   `Path(__file__).resolve().parent`.

4. Update `./metricsctl` `DEV_LIB` computation (line 18) to use `find_repo_root()` result.

5. Update all 9 `govctl-targets.yaml` `metrics.*` targets to invoke `./dev/bin/metricsctl`
   instead of `./metricsctl`.

6. Add compatibility shim notice to `dev/bin/metrics-runner` — document that it is a
   compatibility layer over `./dev/bin/metricsctl` and will be deprecated.

**Operator-visible behaviors that must remain unchanged:**
- `metricsctl status`, `run-now`, `publish`, `install`, `stop` — identical output
- `metrics-runner run`, `status`, `publish-github` — continue to work
- MCP task mappings produce identical results

**Minimal test updates required in this phase:**
- Add test for `find_repo_root()`: found, not-found (depth exceeded), called from subdirectory
- Add test for `ensure_venv()` with explicit `repo_root` parameter
- Add test confirming `metricsctl._repo_root()` returns correct value when `CWD` ≠ repo root

**Acceptance criteria:**
- All govctl `metrics.full` group targets pass
- `./dev/bin/metricsctl paths` works from any working directory within the repo tree
- `./dev/bin/metrics-runner run/status/publish-github` delegates correctly
- MCP metrics task tests pass (`tests/unit/test_mcp_metrics_tasks.py`)
- Systemd unit generation produces correct `ExecStart` path
- No test regressions

**Risks:**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `find_repo_root()` is slow on deeply nested workspaces | Low | Cap walk depth; module-level cache result |
| CWD-based root discovery fails outside repo tree | Medium | Fall back to `__file__`-relative chain; log warning |
| Updating govctl targets breaks CI temporarily | Low | Run `govctl run metrics.full` before merging |

---

### Phase 2 — Consolidation & Refactor

**Goals:**
- Move `./metricsctl` Python implementation to `./dev/lib/metricsctl.py`
- Update `./dev/bin/metricsctl` to be a thin launcher of `dev/lib/metricsctl.py`
- Convert `./metricsctl` at repo root to a deprecation-warning shim
- Update all documentation to point to `./dev/bin/metricsctl` as sole canonical entrypoint

**Non-goals:**
- Do not remove `metrics-runner`
- Do not change any operator-visible CLI surface
- Do not restructure `metrics/runner/` modules

**Preconditions:**
- Phase 1 complete with all acceptance criteria validated
- `find_repo_root()` and decoupled `ensure_venv()` in production use
- No open regressions on govctl targets or MCP task tests

**Work items:**

1. Create `dev/lib/metricsctl.py` containing all `cmd_*` functions, `build_parser()`,
   and `main()` from `./metricsctl` (adjusted imports; no functional changes).

2. Update `dev/bin/metricsctl` (bash) to a thin Python launcher:
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
   exec "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/dev/lib/metricsctl.py" "$@"
   ```
   With fallback to system Python when `.venv` is absent.

3. Convert `./metricsctl` at repo root to a deprecation shim:
   ```python
   #!/usr/bin/env python3
   # DEPRECATED: Use ./dev/bin/metricsctl instead.
   import os, sys, subprocess
   sys.stderr.write("[DEPRECATED] ./metricsctl is deprecated; use ./dev/bin/metricsctl\n")
   os.execv(str(Path(__file__).parent / "dev" / "bin" / "metricsctl"), sys.argv)
   ```

4. Update documentation: `docs/development-handbook.md`, `metrics/README.md`,
   `design/infra/metrics-ctl-design.md` — clarify `./dev/bin/metricsctl` as sole
   canonical entrypoint.

5. Audit `tests/` for hard-coded `./metricsctl` paths; update to `./dev/bin/metricsctl`
   before merging.

6. Confirm `poller_runner._service_unit_content()` embeds `./dev/bin/metricsctl` (already
   does at line 263 — verify unchanged).

7. Confirm static systemd template `metrics/systemd/nightfall-metrics-poller.service`
   already references `./dev/bin/metricsctl` (already does at line 9 — verify unchanged).

**Regression risks and mitigation:**

| Risk | Mitigation |
|------|------------|
| Moving Python to `dev/lib/metricsctl.py` disrupts `sys.path` imports | `dev/bin/metricsctl` launcher sets up `sys.path` before delegating; test all 20 subcommands |
| Test fixtures hard-code `./metricsctl` path | Audit `tests/` in Phase 2 precondition step; update before merging |
| `ensure_venv(Path(__file__))` in new location looks for `.venv` in `dev/lib/` | Phase 1 decouples this; pass `find_repo_root()` result explicitly |
| Deprecation shim at `./metricsctl` silently fails if govctl not updated | Phase 1 updates govctl first; shim is a safety net, not primary path |

**Acceptance criteria:**
- `./metricsctl` (root shim) prints deprecation warning to stderr and exits correctly
- `./dev/bin/metricsctl` produces identical JSON/text output for all 20 subcommands
- `./dev/bin/metrics-runner run/status/publish-github` still works
- All govctl `metrics.*` targets pass
- All MCP metrics task tests pass
- Systemd unit installed and regenerated correctly
- Docs updated; no references to `./metricsctl` as primary entrypoint remain

---

### Phase 3 — Removal & Cleanup

**Goals:**
- Remove `./metricsctl` root-level file after deprecation period
- Resolve `metrics-runner` fate: permanent compatibility shim or removal
- Final documentation cleanup, regression gating, and communication

**Non-goals:**
- Do not change `dev/lib/metricsctl.py` implementation in this phase
- Do not restructure `metrics/runner/` modules

**Preconditions:**
- Phase 2 complete and validated
- Deprecation warning at `./metricsctl` has been visible to operators for ≥ 2 weeks
- No callers of `./metricsctl` root script remain (confirmed via `grep` audit)
- Decision on `metrics-runner` obtained from team/maintainer

**Conditions for removal of `metrics-runner`:**
- All operator workflows migrated to `metricsctl` subcommands
- Documentation updated to remove all `metrics-runner` usage examples
- Regression tests added for `run-now`, `status`, `publish` directly via `metricsctl`
- Team agreement that `run` and `publish-github` aliases are no longer needed

**Work items:**

1. Remove (or archive to `dev/archive/metricsctl-deprecated`) `./metricsctl` from repo root.

2. Update `pyproject.toml` and any package manifests referencing the root `metricsctl` path.

3. Decision on `metrics-runner`:
   - **Keep as permanent shim:** Add prominent `# DEPRECATED` header with version note; no other changes.
   - **Remove:** Audit all docs/scripts for `metrics-runner` references; update all occurrences.

4. Final docs update: `AGENTS.md`, `README.md`, `docs/development-handbook.md`,
   `metrics/README.md`, `design/infra/metrics-ctl-design.md`.

5. Add CI regression gate: grep check confirming that `./metricsctl` does not appear as a
   callable target in `govctl-targets.yaml`, `tests/`, or active `docs/` (except archived files).

6. Update `CHANGELOG.md` or release notes with breaking-change notice if any external
   consumers reference `./metricsctl`.

**Versioning and communication:**
- Comment on Issue #8 when each phase is merged
- Tag a git ref at Phase 2 completion before Phase 3 removal begins
- Document breaking change in release notes if `./metricsctl` removal affects external integrations

**Acceptance criteria:**
- `./metricsctl` at repo root is absent or clearly archived
- `./dev/bin/metricsctl` is the sole canonical entrypoint, confirmed by full test suite
- `metrics-runner` is absent or contains clear deprecation notice
- All docs updated; no stale `./metricsctl` references as primary entrypoint
- CI grep gate passes
- All existing tests pass

---

## 7. Migration Checklist

This checklist is designed for direct execution by a future implementation agent.
Each item is scoped to a single atomic change suitable for one commit.

---

### Phase 1 — Preparation & Compatibility Layer

#### Code changes
- [ ] Add `find_repo_root(sentinel="pyproject.toml", max_depth=12) -> Path` to `dev/lib/`
- [ ] Add tests for `find_repo_root()` in `tests/unit/` (found, not-found, depth-exceeded, from subdirectory)
- [ ] Add `repo_root: Path | None = None` parameter to `venv_bootstrap.ensure_venv()`; maintain backward-compat default
- [ ] Update `tests/unit/test_venv_bootstrap.py` with test for explicit `repo_root` parameter
- [ ] Update `./metricsctl` `_repo_root()` (line 77) to call `find_repo_root()`
- [ ] Update `./metricsctl` `DEV_LIB` computation (line 18) to use `find_repo_root()` result
- [ ] Add test that `metricsctl._repo_root()` returns correct path when `CWD` ≠ repo root

#### Caller updates
- [ ] Update `govctl-targets.yaml:213` (`metrics.collect.backend`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:225` (`metrics.status`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:237` (`metrics.run-now`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:249` (`metrics.collect.frontend`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:261` (`metrics.aggregate`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:273` (`metrics.generate.dashboard`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:285` (`metrics.publish`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:297` (`metrics.install`) to use `./dev/bin/metricsctl`
- [ ] Update `govctl-targets.yaml:309` (`metrics.stop`) to use `./dev/bin/metricsctl`

#### Documentation updates
- [ ] Add compatibility shim notice comment to `dev/bin/metrics-runner`

#### Regression gates (must pass before Phase 2 starts)
- [ ] All govctl `metrics.full` group targets pass
- [ ] `tests/unit/test_mcp_metrics_tasks.py` assertions pass
- [ ] `./dev/bin/metricsctl paths` returns correct repo paths when `CWD` ≠ repo root
- [ ] `./dev/bin/metrics-runner run/status/publish-github` delegates correctly

---

### Phase 2 — Consolidation & Refactor

#### Code changes
- [ ] Create `dev/lib/metricsctl.py` with all `cmd_*` functions and CLI wiring from `./metricsctl`
- [ ] Update `dev/bin/metricsctl` to thin launcher of `dev/lib/metricsctl.py`
- [ ] Convert `./metricsctl` at repo root to deprecation shim (print warning to stderr, delegate to `dev/bin/metricsctl`)
- [ ] Confirm `poller_runner._service_unit_content()` still embeds `./dev/bin/metricsctl` (verify unchanged)
- [ ] Confirm `metrics/systemd/nightfall-metrics-poller.service` references `./dev/bin/metricsctl` (verify unchanged)

#### Caller updates
- [ ] Audit `tests/` for hard-coded `./metricsctl` paths; update all to `./dev/bin/metricsctl`
- [ ] Confirm no remaining `./metricsctl` invocations in `dev/` scripts (outside of shim itself)

#### Test updates
- [ ] Add smoke test: `./dev/bin/metricsctl paths` from repo subdirectory returns correct paths
- [ ] Add regression test: output of `./dev/bin/metricsctl <each-subcommand>` identical to pre-migration `./metricsctl`

#### Documentation updates
- [ ] Update `docs/development-handbook.md` canonical entrypoint table to reference `./dev/bin/metricsctl`
- [ ] Update `metrics/README.md` metricsctl references
- [ ] Update `design/infra/metrics-ctl-design.md` with new canonical layout
- [ ] Update `AGENTS.md` if it references `./metricsctl` as primary entrypoint
- [ ] Add `# DEPRECATED` header to `./metricsctl` root shim

#### Regression gates (must pass before Phase 3 starts)
- [ ] `./metricsctl` shim prints deprecation warning to stderr, then exits with correct behavior
- [ ] `./dev/bin/metricsctl` produces identical output for all 20 subcommands
- [ ] All govctl `metrics.*` targets pass
- [ ] All MCP metrics task tests pass
- [ ] Systemd unit reinstall generates correct `ExecStart` path

---

### Phase 3 — Removal & Cleanup

#### Code changes
- [ ] Remove (or archive) `./metricsctl` from repo root after deprecation window
- [ ] Update `pyproject.toml` / package manifests if they reference `./metricsctl`
- [ ] Decide fate of `dev/bin/metrics-runner` — add deprecation header OR remove

#### Caller updates
- [ ] Final grep audit: confirm no `./metricsctl` invocations remain in scripts/tests/docs outside archive

#### Test updates
- [ ] Remove tests specific to `./metricsctl` root deprecation shim (now redundant)
- [ ] Add regression test for `dev/bin/metrics-runner` if kept as permanent shim

#### Documentation updates
- [ ] Update `AGENTS.md`, `README.md`, `docs/development-handbook.md`, `metrics/README.md`
- [ ] Update `design/infra/metrics-ctl-design.md` with final canonical layout
- [ ] Add removal entry to `CHANGELOG.md` or release notes

#### Regression gates (final)
- [ ] CI grep gate: `./metricsctl` does not appear as a callable target in `govctl-targets.yaml`, `tests/`, or `docs/`
- [ ] Full test suite passes
- [ ] `dev/bin/metricsctl` is the sole canonical entrypoint confirmed by audit
- [ ] `metrics-runner` absent or has deprecation notice routing only to `dev/bin/metricsctl`
