# devctl Update Architecture — Chunk-Wise Implementation Plan

**Status:** implemented  
**Date:** 2026-04-05  
**Design reference:** [devctl-update-architecture.md](../../design/devctl-update-architecture.md)  
**Constraint:** System must remain operational after each chunk.  
**Constraint:** No chunk may break existing automated flows (metricsctl, poller, MCP).

---

## Chunk Overview

| # | Title | Risk | Depends On |
|---|-------|------|-----------|
| 1 | Dual-snapshot variable rename and internal refactor | Low | — |
| 2 | `devctl check` command | Low | 1 |
| 3 | `devctl reset --base` semantics | Low | 1 |
| 4 | Lockfile regeneration and pull-back internals | Medium | 1 |
| 5 | Regression gate internal function | Medium | 1 |
| 6 | `devctl update` command (unified) | High | 1, 4, 5 |
| 7 | Remove public snapshot-create/snapshot-refresh and `create` alias | Low | 6 |
| 8 | MCP model and contract test migration | Low | 6, 7 |

---

## Chunk 1: Dual-Snapshot Variable Rename and Internal Refactor

### Goal

Replace the single `SNAPSHOT_CLEAN="clean-installed"` with dual-snapshot
variables (`SNAPSHOT_BASE`, `SNAPSHOT_CURRENT`) and update all internal
references. No behavioral change yet — `SNAPSHOT_CURRENT` is defined but not
created by any command in this chunk.

### Preconditions

- devctl is operational with the current single-snapshot model.
- All existing tests pass.

### Steps

1. In `dev/bin/devctl`, replace the variable declaration:
   - Remove: `SNAPSHOT_CLEAN="clean-installed"`
   - Add: `SNAPSHOT_BASE="base"` and `SNAPSHOT_CURRENT="current"`

2. Rename `_has_snapshot_clean` → `_has_snapshot_base`.
   Update its body to check for `$SNAPSHOT_BASE`.

3. Add `_has_snapshot_current` that checks for `$SNAPSHOT_CURRENT`.

4. Rename `_require_clean_snapshot` → `_require_base_snapshot`.
   Update its body and error message.

5. Update `_refresh_clean_snapshot` → `_refresh_base_snapshot`.
   Update to use `$SNAPSHOT_BASE`.

6. Add `_refresh_current_snapshot` that creates/replaces `$SNAPSHOT_CURRENT`.

7. Update `cmd_setup`:
   - Delete `$SNAPSHOT_CURRENT` if it exists (INV-05).
   - Call `_refresh_base_snapshot` (not `_refresh_clean_snapshot`).

8. Update `cmd_reset`:
   - Restore from `$SNAPSHOT_CURRENT` if it exists.
   - Fall back to `$SNAPSHOT_BASE` if `$SNAPSHOT_CURRENT` does not exist.
   - (No `--base` flag yet — that's Chunk 3.)

9. Update `cmd_snapshot_create` and `cmd_snapshot_refresh` to use
   `_refresh_base_snapshot`. (These will be removed in Chunk 7, but must
   continue working during migration.)

10. Update `cmd_assert_cached_ready` to check for `$SNAPSHOT_CURRENT` first,
    fall back to `$SNAPSHOT_BASE`.

11. Update `cmd_status` to report both snapshot names.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `devctl setup` creates a snapshot named `base` (not `clean-installed`).
- `devctl reset` restores from `base` (since `current` doesn't exist yet).
- `devctl status` reports `base` snapshot status.
- `devctl snapshot-create` still works (creates `base`).
- `devctl assert-cached-ready` passes when `base` exists.
- All existing unit tests pass after updating snapshot name assertions.

### Risks

- **Existing snapshot named `clean-installed` becomes orphaned.** The operator
  must run `devctl setup` once after this chunk to create the new `base`
  snapshot. Document this as a one-time migration step.
- **Contract tests that assert on snapshot name `clean-installed` will break.**
  These must be updated in this chunk.

### Migration Note

After deploying this chunk, the operator must run:
```
devctl destroy && devctl setup
```
Or manually rename the LXC snapshot:
```
lxc rename dev-photo-ingress/clean-installed dev-photo-ingress/base
```

---

## Chunk 2: `devctl check` Command

### Goal

Add a read-only drift report command that inspects Node version drift, per-stack
manifest drift, and snapshot status without mutating any state.

### Preconditions

- Chunk 1 is complete (dual-snapshot variables exist).

### Steps

1. Add `cmd_check` function in `dev/bin/devctl`:
   - Read `.node-version` → expected.
   - Query container Node version → actual (handle container-not-running).
   - Report Node drift: `{expected} vs {actual}` or "no drift".
   - For each stack {webui, dashboard}:
     - Compute host manifest hash.
     - Read container manifest hash (handle missing).
     - Report drift or "no drift".
   - Report snapshot status: `base` exists? `current` exists? Age of each.
   - Report SvelteKit/Vite major consistency.
   - Exit 0 if no drift; exit 1 if any drift detected.

2. Add `check` to the `case` dispatch in `main()`.

3. `check` is NOT a stateful command — it does not acquire the global lock.

4. Add `check` to the usage text.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `devctl check` exits 0 when no drift exists.
- `devctl check` exits 1 and reports Node drift when `.node-version` differs
  from container.
- `devctl check` exits 1 and reports manifest drift when `package.json` has
  been edited but lockfile not regenerated.
- `devctl check` reports snapshot status (base present, current absent/present).
- `devctl check` works when container is stopped (reports "container not running"
  for container-side checks instead of failing).

### Risks

- Low. Pure read-only command with no side effects.

---

## Chunk 3: `devctl reset --base` Semantics

### Goal

Add `--base` flag to `devctl reset` for explicit base-snapshot restoration.
Without the flag, reset targets `current` (if exists) then `base`.

### Preconditions

- Chunk 1 is complete (dual-snapshot variables and `_has_snapshot_current` exist).

### Steps

1. Update `cmd_reset` to accept a `--base` argument.

2. Logic:
   - If `--base` is passed: restore from `$SNAPSHOT_BASE`. Fail if missing.
   - If `--base` is not passed: restore from `$SNAPSHOT_CURRENT` if it exists,
     else `$SNAPSHOT_BASE`. Fail if neither exists.

3. Update usage text for `reset`.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `devctl reset` restores from `current` when both snapshots exist.
- `devctl reset` restores from `base` when only `base` exists.
- `devctl reset --base` restores from `base` even when `current` exists.
- `devctl reset --base` fails with clear error when `base` is missing.

### Risks

- Low. Additive change to existing command.

---

## Chunk 4: Lockfile Regeneration and Pull-Back Internals

### Goal

Implement `_regenerate_stack` and `_pull_lockfile` as internal functions.
These are not wired to any command yet — they are building blocks for Chunk 6.

### Preconditions

- Chunk 1 is complete (devctl structure is stable).

### Steps

1. Add `_regenerate_stack(stack)` function:
   - Resolve container root path for the given stack.
   - Resolve container hash file path.
   - `lxc exec` into container:
     - `cd $container_root`
     - `rm -rf node_modules .svelte-kit`
     - `npm install` (NOT `npm ci`)
     - Write SHA256 hash of `package.json + package-lock.json` to hash file.
   - Log success or failure.

2. Add `_pull_lockfile(stack)` function:
   - Resolve container root path.
   - Resolve host directory for the stack.
   - `lxc file pull "$CONTAINER/$container_root/package-lock.json" "$host_dir/package-lock.json"`
   - Verify the pulled file exists on host.

3. Add `_recalculate_host_hash(stack)` function:
   - Recompute SHA256 of host `package.json + package-lock.json` after pull-back.
   - This is used to verify consistency post-pull.

4. Add inline comments documenting the distinction between `_install_stack`
   (npm ci, lockfile-authoritative) and `_regenerate_stack` (npm install,
   manifest-authoritative) per INV-08.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `_regenerate_stack webui` can be called manually (via `devctl shell` +
  sourcing devctl functions) and produces a new `package-lock.json` in the
  container.
- `_pull_lockfile webui` copies the container's lockfile to
  `$PROJECT_ROOT/webui/package-lock.json`.
- `_recalculate_host_hash webui` produces a hash that matches the container's
  hash after a pull-back.
- `_install_stack` is unchanged and still uses `npm ci`.

### Risks

- **Medium: `npm install` may resolve different versions than expected** if
  the npm registry state changes between runs. This is inherent to `npm install`
  and is mitigated by the regression gate (Chunk 5). The resolved lockfile is
  committed and becomes the new source of truth.
- **`lxc file pull` path format** must be tested — LXC uses
  `container/path/in/container` syntax. Verify the exact path format works
  with the container name and internal path.

---

## Chunk 5: Regression Gate Internal Function

### Goal

Implement `_run_regression_gate` as an internal function that runs the full
test suite. Not wired to any command yet — building block for Chunk 6.

### Preconditions

- Chunk 1 is complete.
- All test commands (`test-web-typecheck`, `test-metrics-dashboard-typecheck`,
  `test-web-unit`) work correctly.

### Steps

1. Add `_run_regression_gate()` function:
   - Must be called within an active lock scope.
   - Sequentially execute:
     1. `cmd_test_web_typecheck`
     2. `cmd_test_metrics_dashboard_typecheck`
     3. `cmd_test_web_unit`
     4. `"$PROJECT_ROOT/.venv/bin/python" -m pytest tests/unit`
   - If any step fails (non-zero exit), abort and return failure with the name
     of the failing suite.
   - If all steps pass, return success.

2. Set `DEVCTL_GLOBAL_LOCK_HELD=1` for the pytest subprocess call so it does
   not attempt to acquire the lock.

3. Track elapsed time for each suite and report totals.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `_run_regression_gate` executes all four test suites in order.
- If all pass, returns 0.
- If any fails, returns non-zero and reports which suite failed.
- Does not attempt to acquire the global lock (assumes caller holds it).
- Backend pytest runs with `DEVCTL_GLOBAL_LOCK_HELD=1`.

### Risks

- **Medium: Test suite execution time.** The full regression may take 2-5
  minutes. This is acceptable for a gated update operation but should be
  documented. An operator who wants to skip the gate should use `--simulate`
  to preview and then manually snapshot (which is intentionally not supported
  to enforce INV-03).

---

## Chunk 6: `devctl update` Command (Unified)

### Goal

Wire together Chunks 4 and 5 into the full `devctl update` command with
`--scope` and `--simulate` flags.

### Preconditions

- Chunk 1 complete (dual-snapshot variables).
- Chunk 4 complete (`_regenerate_stack`, `_pull_lockfile`).
- Chunk 5 complete (`_run_regression_gate`).

### Steps

1. Add `cmd_update()` function implementing the canonical update flow:

   a. Parse `--scope` (default: auto-detect) and `--simulate` flags.

   b. Read `.node-version` → expected. Query container → actual.

   c. If `--simulate`:
      - Report Node drift status.
      - For each stack, report manifest drift status.
      - Report effective scope.
      - Exit 0 (no drift) or 1 (drift detected). No mutations.

   d. If Node drifted:
      - Escalate scope to `all`.
      - `_install_node_exact "$expected"`.

   e. `assert_web_stack_major_consistency`.

   f. For each stack in resolved scope:
      - `_sync_{stack}_sources`
      - `_regenerate_stack $stack`
      - `_pull_lockfile $stack`

   g. For each stack in {webui, dashboard}:
      - `_assert_stack_no_drift $stack`

   h. `_run_regression_gate`
      - On failure: report, do NOT snapshot, exit non-zero.

   i. `_refresh_current_snapshot`

   j. Report success summary: scope, stacks updated, regression result,
      snapshot created.

2. Add `update` to the `case` dispatch in `main()`.

3. Mark `update` as a stateful command in `_is_stateful_command`.

4. Add `update` to the usage text with full flag documentation.

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- **Node update flow:** Change `.node-version`, run `devctl update`. Verify:
  - Container Node version matches new `.node-version`.
  - Both `webui/package-lock.json` and `metrics/dashboard/package-lock.json`
    are regenerated on host.
  - All tests pass (regression gate).
  - `current` snapshot exists.
  - `base` snapshot is untouched.

- **Package update flow:** Edit `webui/package.json` (add a devDependency),
  run `devctl update --scope webui`. Verify:
  - `webui/package-lock.json` is regenerated on host.
  - `metrics/dashboard/package-lock.json` is NOT modified.
  - Regression gate runs.
  - `current` snapshot created.

- **Auto-detect flow:** Edit `webui/package.json`, run `devctl update` (no
  scope). Verify it auto-detects webui drift and updates only webui.

- **Simulate flow:** Run `devctl update --simulate`. Verify:
  - Reports drift status without mutation.
  - No lockfiles changed. No snapshots created.

- **Escalation flow:** Change `.node-version` AND edit `webui/package.json`,
  run `devctl update --scope webui`. Verify it escalates to `all` because
  of Node drift.

- **Failed regression:** Introduce a breaking change, run `devctl update`.
  Verify: regression fails, no `current` snapshot created, container is not
  snapshotted.

### Risks

- **High: This is the most complex chunk.** The update flow coordinates Node
  install, source sync, npm install, lockfile pull-back, drift assertions,
  regression, and snapshot creation. Careful ordering is essential.
- **`npm install` network dependency.** If the npm registry is unreachable,
  `npm install` will fail. This is acceptable — the operator retries later.
- **Concurrent access.** The global lock prevents concurrent updates, but does
  not prevent a developer from editing files while an update runs. This is
  a known limitation documeted in the design.

---

## Chunk 7: Remove Public snapshot-create/snapshot-refresh and `create` Alias

### Goal

Remove `snapshot-create`, `snapshot-refresh`, and `create` from the public
command surface. Retain internal functions for use by `setup` and `update`.

### Preconditions

- Chunk 6 is complete (`devctl update` is the sanctioned path to `current`).

### Steps

1. Remove `snapshot-create`, `snapshot-refresh`, and `create` from the `case`
   dispatch in `main()`.

2. Remove them from the usage text.

3. Remove them from `_is_stateful_command`.

4. Retain `_refresh_base_snapshot` and `_refresh_current_snapshot` as internal
   functions (used by `cmd_setup` and `cmd_update`).

5. Retain `cmd_snapshot_create` as `_cmd_snapshot_create_internal` if any
   internal caller needs the drift-check-then-snapshot-base flow (evaluate
   whether `cmd_setup` already covers this — if so, remove entirely).

### Expected Artifacts

- Modified: `dev/bin/devctl`

### Acceptance Criteria

- `devctl snapshot-create` produces "Unknown command" error.
- `devctl snapshot-refresh` produces "Unknown command" error.
- `devctl create` produces "Unknown command" error.
- `devctl setup` still works (creates `base` snapshot).
- `devctl update` still works (creates `current` snapshot).
- Usage text does not list removed commands.

### Risks

- **Low.** Removing commands is straightforward. The only risk is external
  scripts (outside this repo) that invoke `devctl snapshot-create` directly.
  Grep the workspace for such references.

---

## Chunk 8: MCP Model and Contract Test Migration

### Goal

Update `.mcp/model.json` and all contract tests to reflect the new command
surface and snapshot semantics.

### Preconditions

- Chunks 1–7 are complete. The new command surface is stable.

### Steps

1. Update `.mcp/model.json`:

   a. Add to `devctl.commands` array: `"update"`, `"check"`.
   b. Remove from `devctl.commands` array: `"snapshot-create"`,
      `"snapshot-refresh"`, `"create"`.

   c. Update `devcontainer.prepare` mapping:
      - Remove `"./dev/bin/devctl snapshot-create"`.
      - Result: `["./dev/bin/devctl setup", "./dev/bin/devctl assert-cached-ready", "./dev/bin/devctl status"]`

   d. Update `mappings.devcontainer.prepare` (redundant mapping section) —
      same change.

   e. Add new mappings:
      ```json
      "devcontainer.check":  ["./dev/bin/devctl check"],
      "devcontainer.update": ["./dev/bin/devctl update"]
      ```

2. Update `tests/unit/test_devcontainer_snapshot_invariants.py`:
   - Update any assertions on snapshot name from `clean-installed` to `base`.
   - Update assertions on `devcontainer.prepare` to not include
     `snapshot-create`.
   - Add assertion that `devctl.commands` includes `update` and `check`.
   - Add assertion that `devctl.commands` does NOT include `snapshot-create`,
     `snapshot-refresh`, or `create`.

3. Update `tests/unit/test_devctl_contracts.py`:
   - Verify no references to removed commands.
   - No changes expected if this file only tests web test commands.

4. Update `docs/deployment/dev-container-workflow.md`:
   - Replace references to `snapshot-refresh` with `update`.
   - Add documentation for `devctl update` and `devctl check`.
   - Update the "expected development lifecycle" section.

5. Run full test suite to verify no regressions.

### Expected Artifacts

- Modified: `.mcp/model.json`
- Modified: `tests/unit/test_devcontainer_snapshot_invariants.py`
- Modified: `docs/deployment/dev-container-workflow.md`
- Potentially modified: other test files with stale references.

### Acceptance Criteria

- `.mcp/model.json` is valid JSON and passes `python3 -m json.tool`.
- `devcontainer.prepare` mapping does not reference `snapshot-create`.
- `devcontainer.check` and `devcontainer.update` mappings exist.
- All unit tests pass.
- `devctl check` is discoverable via MCP `tools/list`.
- `devctl update` is discoverable via MCP `tools/list`.
- `dev-container-workflow.md` accurately reflects the new command surface.

### Risks

- **Low.** This is a documentation and configuration update. The main risk is
  missing a stale reference in a test file — mitigated by running the full
  test suite.

---

## Execution Order Summary

```
Chunk 1 ─────────────────────────────────────── (foundation)
  │
  ├── Chunk 2 (check command)                    (independent)
  ├── Chunk 3 (reset --base)                     (independent)
  ├── Chunk 4 (lockfile regen internals)         (independent)
  └── Chunk 5 (regression gate internals)        (independent)
        │         │
        └────┬────┘
             │
        Chunk 6 (devctl update — wires 4+5)      (depends on 1, 4, 5)
             │
        Chunk 7 (remove old commands)             (depends on 6)
             │
        Chunk 8 (MCP + test migration)            (depends on 6, 7)
```

Chunks 2, 3, 4, and 5 are independent of each other and can be implemented in
parallel after Chunk 1. Chunk 6 is the critical integration point. Chunks 7 and
8 are cleanup.

---

## Post-Implementation Validation

After all chunks are complete, the operator must perform:

1. `devctl destroy` (clean slate)
2. `devctl setup` (creates `base` snapshot)
3. `devctl check` (should report no drift)
4. Edit `webui/package.json` (add a harmless devDependency)
5. `devctl check` (should report webui manifest drift)
6. `devctl update --simulate` (should report what would happen)
7. `devctl update --scope webui` (should regenerate lockfile, run regression, create `current`)
8. `devctl check` (should report no drift)
9. `devctl reset` (should restore from `current`)
10. `devctl reset --base` (should restore from `base`)
11. Revert the `package.json` edit; commit the regenerated lockfile.
12. Full `./dev/bin/metricsctl run-now` to verify automated flows are unaffected.
