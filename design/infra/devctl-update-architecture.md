# devctl Update Architecture — Dual-Snapshot Model, Lockfile Regeneration, and Regression Gate

**Status:** proposed  
**Date:** 2026-04-05  
**Owner:** Systems Engineering  
**Supersedes:** single-snapshot model (SNAPSHOT_CLEAN="clean-installed")  
**See also:** [dev-container-workflow.md](../docs/deployment/dev-container-workflow.md), [environment-separation-and-container-lifecycle.md](architecture/environment-separation-and-container-lifecycle.md)

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Problem Statement](#2-problem-statement)
3. [Proposed Architecture](#3-proposed-architecture)
4. [Snapshot Model](#4-snapshot-model)
5. [Update Model](#5-update-model)
6. [Command Surface](#6-command-surface)
7. [Regression Gate](#7-regression-gate)
8. [Lockfile Regeneration Model](#8-lockfile-regeneration-model)
9. [Role of ensure-stack-ready After Redesign](#9-role-of-ensure-stack-ready-after-redesign)
10. [Integration Points](#10-integration-points)
11. [Flow Validation Matrix](#11-flow-validation-matrix)
12. [Failure Modes](#12-failure-modes)
13. [Open Questions](#13-open-questions)
14. [Glossary of Invariants](#14-glossary-of-invariants)

---

## 1. Motivation

The Nightfall development container model enforces deterministic, drift-free,
audit-ready development environments. The current model provides a robust
atomic bootstrap path (`devctl setup`) and drift detection via manifest hashing.
However, it has no mechanism for two critical real-world operations:

- **Node version updates** — when `.node-version` changes, `package-lock.json`
  must be regenerated inside the controlled container environment and copied back
  to the host workspace.
- **Dependency updates** — when a developer edits `package.json` (adding,
  removing, or changing a dependency), the lockfile must be regenerated inside the
  container to preserve determinism.

Without these mechanisms, the operator must either (a) manually exec into the
container to run `npm install` and hand-copy lockfiles, or (b) destroy and
rebuild the entire container from scratch. Both paths are error-prone, violate
the deterministic model, and cannot be audited.

---

## 2. Problem Statement

### 2.1 No Update Path Exists

The current `devctl` uses only `npm ci` (lockfile-authoritative install). This
requires a pre-existing, valid `package-lock.json` that is consistent with
`package.json`. When `package.json` is edited or Node version changes, `npm ci`
will either fail or produce incorrect results. There is no `npm install`
(manifest-authoritative) path in devctl.

### 2.2 Single Snapshot Has No Rollback Safety

The single `clean-installed` snapshot is destroyed-then-recreated by
`_refresh_clean_snapshot`. If the new state is broken, the previous known-good
state is lost. The operator must re-run the full 10+ minute `devctl setup` to
recover.

### 2.3 No Regression Gate Before Snapshot

`snapshot-create` enforces drift-free invariants (correct) but does not run the
full test suite before snapshotting. A drift-free snapshot can still be
functionally broken.

### 2.4 No Drift Visibility

Drift is detected and remediated silently inside `_ensure_stack_ready`. There is
no way for the operator to inspect the current drift state without triggering
a potentially expensive remediation.

### 2.5 Confusing Snapshot Semantics

`snapshot-refresh` is an alias for `snapshot-create`. The `create` command is an
alias for `setup`. These redundancies add cognitive load without capability.

---

## 3. Proposed Architecture

### 3.1 Design Principles

1. **Dual-snapshot model** — two named snapshots with distinct semantics.
2. **Single unified update command** with scope and dry-run.
3. **Mandatory regression gate** before any post-update snapshot.
4. **Container-side lockfile regeneration** with pull-back to host.
5. **Explicit drift visibility** via a read-only check command.
6. **Backward compatibility** — `ensure-stack-ready` continues to work for
   automated flows; `setup` continues to be the atomic bootstrap path.

### 3.2 Invariant: npm ci vs npm install

These are fundamentally different operations:

| Operation | Authority | Lockfile | Use Case |
|-----------|-----------|----------|----------|
| `npm ci` | `package-lock.json` | Must exist, must be valid | `_install_stack` — deterministic replay |
| `npm install` | `package.json` | Regenerated from manifest | `_regenerate_stack` — update path |

The system must never conflate these. `_install_stack` (existing) uses `npm ci`.
`_regenerate_stack` (new) uses `npm install`. They serve different invariants.

---

## 4. Snapshot Model

### 4.1 Snapshot Names

| Snapshot | Variable | Created By | Semantics |
|----------|----------|-----------|-----------|
| **base** | `SNAPSHOT_BASE` | `devctl setup` | Full atomic bootstrap. Immutable until next `setup`. |
| **current** | `SNAPSHOT_CURRENT` | `devctl update` | Rolling latest-good state. Created only after regression passes. |

### 4.2 Snapshot Lifecycle

```
devctl setup
  → Destroys BOTH base and current
  → Full atomic bootstrap (Node + Python + npm ci both stacks)
  → Creates base snapshot
  → current does not exist yet

devctl update [--scope ...]
  → Never touches base
  → Runs update flow (npm install, lockfile regen, regression)
  → Creates/replaces current snapshot

devctl reset
  → Restores current if it exists, else base

devctl reset --base
  → Restores base unconditionally (escape hatch)
```

### 4.3 Snapshot State Diagram

```
                        ┌─────────────────────────────┐
                        │   No Container Exists       │
                        └─────────────┬───────────────┘
                                      │ devctl setup
                                      ▼
                        ┌─────────────────────────────┐
                        │   base exists               │
                        │   current does not exist    │
                        └─────────────┬───────────────┘
                                      │ devctl update (regression passes)
                                      ▼
                        ┌─────────────────────────────┐
                        │   base exists               │
                        │   current exists            │
                        └─────────────┬───────────────┘
                                      │ devctl update (regression passes again)
                                      ▼
                        ┌─────────────────────────────┐
                        │   base exists (unchanged)   │
                        │   current replaced          │
                        └─────────────────────────────┘

  At any point:
    devctl setup  → returns to "base exists, current does not exist"
    devctl reset  → restores container to current (or base if no current)
```

### 4.4 Why Two Snapshots (Not One, Not N)

- **One snapshot (current model):** No rollback safety. Destroyed on every
  refresh. If the new state is broken, full rebuild required.
- **Two snapshots:** Safe rollback to base. Base never touched by incremental
  updates. Operator can always escape to a known-good bootstrap state.
- **N snapshots:** Additional complexity (naming, pruning, selection) with no
  corresponding benefit. The model only needs "original bootstrap" and "latest
  validated update".

---

## 5. Update Model

### 5.1 Unified Update Command

```
devctl update [--scope node|webui|dashboard|all] [--simulate]
```

**Scope resolution:**

| `--scope` | Behavior |
|-----------|----------|
| *(omitted)* | Auto-detect: check Node drift → check both manifests → determine minimal scope |
| `node` | Force Node reinstall + both stacks rebuild + lockfile regen |
| `webui` | Force webui-only rebuild + lockfile regen (escalates to `node` if Node drifted) |
| `dashboard` | Force dashboard-only rebuild + lockfile regen (escalates to `node` if Node drifted) |
| `all` | Force both stacks rebuild + lockfile regen (installs Node only if drifted) |

### 5.2 Update Flow (Canonical)

```
 1. Acquire global repo lock
 2. Read .node-version → expected_node
 3. Query container Node version → actual_node
 4. IF expected_node ≠ actual_node:
      scope ← "all" (escalate)
      _install_node_exact(expected_node)
 5. assert_web_stack_major_consistency()
 6. FOR EACH stack IN resolve_stacks(scope):
      a. _sync_{stack}_sources()
      b. _regenerate_stack(stack)          ← npm install (NOT npm ci)
      c. _pull_lockfile(stack)             ← lxc file pull → host
 7. Recalculate host manifest hashes (with new lockfiles)
 8. FOR EACH stack IN {webui, dashboard}:
      _assert_stack_no_drift(stack)        ← verify ALL stacks, not just updated
 9. _run_regression_gate()                 ← full test suite
10. IF regression passed:
      _create_snapshot("current")
11. Release global repo lock
```

### 5.3 Simulate Mode

When `--simulate` is passed, the command performs steps 1–4 (detection only, no
mutation) and reports:

- Node drift: `{expected} vs {actual}` or "no drift"
- Per-stack manifest drift: hash comparison or "no drift"
- Effective scope: what would be rebuilt
- Estimated operations: which stacks reinstall, whether lockfiles regenerate

No container state is mutated. No lockfiles are changed. No snapshots created.

---

## 6. Command Surface

### 6.1 New Commands

| Command | Purpose |
|---------|---------|
| `devctl update [--scope ...] [--simulate]` | Unified update: lockfile regen, regression gate, snapshot |
| `devctl check` | Read-only drift report across all dimensions |

### 6.2 Modified Commands

| Command | Change |
|---------|--------|
| `devctl reset` | Default target becomes `current` (if exists), else `base`. Gains `--base` flag. |
| `devctl setup` | Destroys both `base` AND `current` snapshots. Creates only `base`. |
| `devctl assert-cached-ready` | Checks for `current` snapshot first, falls back to `base`. |

### 6.3 Removed Public Commands

| Command | Reason |
|---------|--------|
| `snapshot-create` | Subsumed by `devctl update`. Manual snapshot creation without regression is an anti-pattern. Retained as internal function only. |
| `snapshot-refresh` | Alias of `snapshot-create`; removed for the same reason. |
| `create` | Alias of `setup`; removed to reduce surface ambiguity. |

### 6.4 Unchanged Commands

All other commands remain unchanged: `destroy`, `ensure-stack-ready`,
`run-api`, `run-webui`, `test-web-typecheck`, `test-metrics-dashboard-typecheck`,
`test-web-unit`, `test-web-e2e`, `status`, `shell`.

### 6.5 Resulting Command Surface

```
devctl setup                              Atomic bootstrap (base snapshot)
devctl destroy                            Delete container
devctl reset [--base]                     Restore to current or base snapshot
devctl update [--scope S] [--simulate]    Update with lockfile regen + regression
devctl check                              Read-only drift report
devctl ensure-stack-ready [target]        Fast-path sync + npm ci drift fix
devctl assert-cached-ready                Verify snapshots and cache mounts
devctl run-api                            API dev server (scaffold)
devctl run-webui                          Vite dev server
devctl test-web-typecheck                 Svelte/TS typecheck (webui)
devctl test-metrics-dashboard-typecheck   Svelte/TS typecheck (dashboard)
devctl test-web-unit                      Vitest unit/component tests
devctl test-web-e2e                       Playwright e2e tests
devctl status                             Container/snapshot/mount status
devctl shell                              Interactive shell
```

16 commands (same count as before: 3 removed, 2 added, `reset` gains a flag).

---

## 7. Regression Gate

### 7.1 Definition

The regression gate is a mandatory full test suite execution that must pass
before `devctl update` may create or replace the `current` snapshot.

### 7.2 Test Suite Composition

```
_run_regression_gate():
  1. devctl test-web-typecheck
  2. devctl test-metrics-dashboard-typecheck
  3. devctl test-web-unit
  4. .venv/bin/python -m pytest tests/unit
```

**Why all suites, not just the affected stack:**

- A webui dependency change can break backend contract tests that read
  `webui/package.json` (e.g., `test_devcontainer_snapshot_invariants.py`).
- A Node version change affects both web stacks and any tests that shell out
  to Node tooling.
- The regression gate is the only protection between "update succeeded
  technically" and "update produced a valid development environment."

### 7.3 Gate Semantics

- On **pass**: proceed to snapshot creation.
- On **fail**: abort. Do not create snapshot. Report which suite failed and
  its exit code. Container state is "dirty" — operator must fix the root cause
  and re-run `devctl update`, or `devctl reset` to revert to last-known-good.

### 7.4 Lock Interaction

The regression gate runs inside the global lock scope. All test commands that
are stateful (`test-web-unit`, `test-web-typecheck`, etc.) check for
`DEVCTL_GLOBAL_LOCK_HELD=1` and skip lock acquisition (reentry guard).

---

## 8. Lockfile Regeneration Model

### 8.1 New Internal Function: _regenerate_stack

```
_regenerate_stack(stack):
  container_root = resolve_container_root(stack)    # /opt/nightfall-webui or /opt/nightfall-metrics-dashboard
  hash_file = resolve_container_hash_file(stack)     # /opt/nightfall-manifest/{webui,dashboard}.hash

  lxc exec $CONTAINER -- bash -c "
    set -euo pipefail
    cd $container_root
    rm -rf node_modules .svelte-kit
    npm install                                       ← manifest-authoritative
    cat package.json package-lock.json | sha256sum | awk '{print \$1}' > $hash_file
  "
```

### 8.2 New Internal Function: _pull_lockfile

```
_pull_lockfile(stack):
  container_root = resolve_container_root(stack)
  host_dir = resolve_host_dir(stack)                 # $PROJECT_ROOT/webui or $PROJECT_ROOT/metrics/dashboard

  lxc file pull "$CONTAINER$container_root/package-lock.json" "$host_dir/package-lock.json"
```

### 8.3 Distinction from _install_stack

| Function | npm command | Lockfile handling | Purpose |
|----------|------------|-------------------|---------|
| `_install_stack` | `npm ci` | Reads existing lockfile; fails if stale | Deterministic replay (setup, ensure-stack-ready) |
| `_regenerate_stack` | `npm install` | Produces new lockfile from package.json | Update path (devctl update) |

These two functions must never be interchanged. `_install_stack` enforces
lockfile authority. `_regenerate_stack` enforces manifest authority.

### 8.4 Lockfile Pull-Back Ordering

The pull-back must happen AFTER `_regenerate_stack` and BEFORE host-side hash
recalculation. The sequence is:

```
_regenerate_stack(stack)     → container has new lockfile + new hash
_pull_lockfile(stack)        → host now has regenerated lockfile
recalculate_host_hash(stack) → host hash matches container hash
_assert_stack_no_drift(stack) → verification passes
```

---

## 9. Role of ensure-stack-ready After Redesign

`ensure-stack-ready` is unchanged. It remains the fast-path entry point for
all test and run commands. Its behavior:

1. Check Node version → if drifted, reinstall Node + `_install_stack` both.
2. Sync sources → `_drift_check_stack` → `npm ci` reinstall if manifest hash
   changed.

**Critical boundary:** `ensure-stack-ready` uses `npm ci`, not `npm install`.
This means it **cannot** handle the case where `package.json` has been edited
but `package-lock.json` has not been regenerated. In that case, `npm ci` will
fail with a manifest/lockfile mismatch error.

**This is correct and intentional.** The failure signals to the operator:
"You changed package.json. Run `devctl update` to regenerate lockfiles."

`ensure-stack-ready` handles:
- Source file changes (non-manifest) → sync only, no reinstall.
- Lockfile-consistent manifest changes → `npm ci` reinstall.
- Node version drift → full reinstall with existing lockfiles.

`ensure-stack-ready` does NOT handle:
- Lockfile-inconsistent manifest changes (package.json edited, lockfile stale).
- Lockfile regeneration.

This separation is a feature, not a bug. Automated flows (metricsctl, poller,
MCP) should never regenerate lockfiles — that is an operator-controlled action.

---

## 10. Integration Points

### 10.1 metricsctl

**Current integration:** `cmd_generate_dashboard` calls
`devctl ensure-stack-ready dashboard` with `DEVCTL_GLOBAL_LOCK_HELD=1`.

**After redesign:** No changes required. `ensure-stack-ready` continues to work.
If the operator has not run `devctl update` after a `package.json` change,
`ensure-stack-ready` will fail with an `npm ci` error, which is the correct
behavior — metricsctl should not silently regenerate lockfiles.

### 10.2 mcp_server.py

**Current integration:** Runs task mappings from `.mcp/model.json` via
subprocess with `DEVCTL_GLOBAL_LOCK_HELD=1`.

**After redesign:** Add new task mappings:

```json
"devcontainer.check":  ["./dev/bin/devctl check"],
"devcontainer.update": ["./dev/bin/devctl update"]
```

Update `devcontainer.prepare` mapping to remove `snapshot-create` (replaced by
update flow which is operator-initiated, not part of automated prepare):

```json
"devcontainer.prepare": [
  "./dev/bin/devctl setup",
  "./dev/bin/devctl assert-cached-ready",
  "./dev/bin/devctl status"
]
```

Add `update` and `check` to `devctl.commands` array.

### 10.3 Poller Runtime

**No changes required.** The poller (`metricsctl run-now`) calls
`run_backend_collection` (host-side pytest), `run_frontend_collection`
(host-side static analysis), then `run_dashboard_generation` which calls
`devctl ensure-stack-ready dashboard`. The update flow is operator-initiated
and never invoked by the poller.

### 10.4 Contract Tests

Tests that reference devctl paths or snapshot names will require updates:

- `test_devcontainer_snapshot_invariants.py` — must be updated to reflect
  removal of `snapshot-create` from `devcontainer.prepare` mapping and any
  snapshot name changes.
- Any test that asserts on the snapshot name `clean-installed` must be updated
  to assert on `base`.

---

## 11. Flow Validation Matrix

| Flow | Uses Container? | Uses devctl? | Entry Point | Affected by Redesign? |
|------|----------------|-------------|-------------|----------------------|
| webui dev server | Yes | `run-webui` → `ensure-stack-ready webui` | `devctl run-webui` | No — ensure-stack-ready unchanged |
| Dashboard generation | Yes (preflight) | `ensure-stack-ready dashboard` | `metricsctl generate-dashboard` | No — ensure-stack-ready unchanged |
| Frontend collection | No | No | `metricsctl collect-frontend` | No |
| Backend pytest | No (host venv) | `setup` + `reset` in MCP mappings | `.venv/bin/python -m pytest` | Minor — reset targets `current` by default |
| Backend coverage | No | No | `metrics/runner/backend_collector.py` | No |
| Web unit tests | Yes | `test-web-unit` → `ensure-stack-ready webui` | `devctl test-web-unit` | No |
| Web typecheck | Yes | `test-web-typecheck` → `ensure-stack-ready webui` | `devctl test-web-typecheck` | No |
| Dashboard typecheck | Yes | `test-metrics-dashboard-typecheck` → `ensure-stack-ready dashboard` | `devctl test-metrics-dashboard-typecheck` | No |
| Web E2E | Yes | `test-web-e2e` → `ensure-stack-ready webui` | `devctl test-web-e2e` | No |
| Schema validation | No | No | `metrics/runner/schema_contract.py` | No |
| Poller runtime | No (except dashboard preflight) | `ensure-stack-ready dashboard` (via metricsctl) | `metricsctl run-now` | No |
| MCP task execution | Varies | Via task mappings | `mcp_server.py` | Minor — new mappings added |
| Container lifecycle | Yes | `setup`, `reset`, `destroy` | Direct devctl invocation | Yes — snapshot names + reset semantics |
| **Node update** | **Yes** | **`update --scope node`** | **New** | **New capability** |
| **Dependency update** | **Yes** | **`update --scope webui\|dashboard`** | **New** | **New capability** |
| **Drift inspection** | **No mutation** | **`check`** | **New** | **New capability** |

**Conclusion:** The redesign affects only container lifecycle commands (setup,
reset, snapshot management) and adds new capabilities. All existing automated
flows (metricsctl, poller, MCP, test commands) are unaffected because they enter
through `ensure-stack-ready`, which is unchanged.

---

## 12. Failure Modes

### 12.1 Update Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| `nvm install` fails (network, missing binary) | Container has old Node; no stacks rebuilt | `devctl reset` to last-known-good |
| `npm install` resolution conflict | Dependency cannot be resolved; no lockfile produced | Fix `package.json`, re-run `devctl update` |
| `npm install` succeeds but produces invalid build | Lockfile generated; regression gate catches it | Gate aborts; `devctl reset` reverts |
| Lockfile pull-back fails (disk, permissions) | Host lockfiles stale; container state correct | Retry manually or re-run `devctl update` |
| Regression gate fails | Container valid but functionally broken | Do not snapshot. Fix code, re-run update |
| Lock timeout | Operation never starts | Retry after lock holder finishes |
| SvelteKit/Vite major divergence after update | Assertion blocks snapshot creation | Fix package.json to restore alignment |
| Container not running | Update cannot proceed | `devctl setup` or `lxc start` |

### 12.2 Reset Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| `current` snapshot missing | Falls back to `base` | Expected behavior |
| Both snapshots missing | Hard fail | `devctl setup` (full bootstrap) |
| `--base` with no base | Hard fail | `devctl setup` |

### 12.3 Interaction Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| `ensure-stack-ready` called with stale lockfile | `npm ci` fails (manifest/lockfile mismatch) | Run `devctl update` to regenerate lockfile |
| metricsctl dashboard generation with stale lockfile | Preflight `ensure-stack-ready` fails | Same as above |
| Poller cycle with stale lockfile | `run_dashboard_generation` fails; manifest reports failure | Operator runs `devctl update`, re-runs poller |

---

## 13. Open Questions

### Q1: Should devctl update auto-commit regenerated lockfiles?

**Recommendation: No.** Lockfile regeneration is a workspace mutation that the
developer should review and commit explicitly. `devctl update` copies the
lockfile to the workspace; the developer then inspects the diff, runs any
additional validation, and commits.

### Q2: Should E2E tests be part of the regression gate?

**Recommendation: Not by default.** E2E tests (Playwright) involve browser
automation and are significantly slower. The default regression gate should
cover typecheck + unit tests. A `--full` flag could opt into E2E as part of
the gate.

### Q3: Should `devctl update` support `--no-regression`?

**Recommendation: No.** The regression gate is the only mechanism that ensures
snapshot correctness. Bypassing it creates the same problem as the current
`snapshot-create` without tests. If the operator needs speed, `--simulate`
provides a fast check without mutation.

### Q4: What happens to in-flight work when `devctl update` runs?

The update flow destroys and recreates `node_modules` inside the container.
Any running Vite dev server or process using those modules will crash. The
operator should stop running processes before update. `devctl update` should
warn if the container has active exec sessions.

### Q5: Should `devctl status` report snapshot age?

**Recommendation: Yes.** `status` should report both snapshot names and their
creation timestamps. This helps the operator decide whether an update is needed.

---

## 14. Glossary of Invariants

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| INV-01 | Lockfiles are regenerated only inside the container | `_regenerate_stack` uses `lxc exec ... npm install` |
| INV-02 | Lockfiles are copied back to host before hash computation | `_pull_lockfile` precedes `_assert_stack_no_drift` |
| INV-03 | Regression gate passes before any snapshot creation | `_run_regression_gate` precedes `_create_snapshot` in update flow |
| INV-04 | `base` snapshot is never modified by `update` | `update` only writes `current` |
| INV-05 | `setup` invalidates both snapshots | `cmd_setup` deletes `current`, creates only `base` |
| INV-06 | Node ABI change widens scope to all stacks | Auto-escalation in update step 4 |
| INV-07 | SvelteKit/Vite major consistency holds after update | `assert_web_stack_major_consistency` called post-lockfile regen |
| INV-08 | `npm ci` and `npm install` are never interchanged | `_install_stack` uses ci; `_regenerate_stack` uses install |
| INV-09 | `ensure-stack-ready` never regenerates lockfiles | Uses only `npm ci`; fails on stale lockfile |
| INV-10 | Global lock held for entire update duration | `acquire_repo_lock` at step 1; `release_repo_lock` at step 11 |
| INV-11 | `reset` restores `current` if available, else `base` | Snapshot selection logic in `cmd_reset` |
| INV-12 | `--simulate` never mutates container or host state | Early return after detection phase |
| INV-13 | All stacks verified drift-free before snapshot, even if only one was updated | `_assert_stack_no_drift` runs for both stacks at step 8 |
| INV-14 | Automated flows (metricsctl, poller, MCP) never trigger lockfile regeneration | They call `ensure-stack-ready`, not `update` |
