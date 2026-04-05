---
name: "Metrics Dashboard Runtime Output Migration (Single PR)"
about: "Controlled checklist for moving dashboard static output to runtime path under metrics/output"
title: "[Metrics] Migrate dashboard static output to runtime path (single controlled PR)"
labels: ["metrics", "infra", "migration"]
assignees: []
---

## Summary

Migrate dashboard static output from repo-root `dashboard/` to a runtime path under `metrics/output/`, while keeping dashboard source/build inputs in git and preserving publish behavior to the `metrics` branch.

This issue is a **single controlled PR checklist**. Do not split into multiple PRs unless blockers are found and approved.

## Objectives

- [ ] Main branch no longer tracks generated dashboard static output.
- [ ] Dashboard build writes static output to runtime path under `metrics/output/`.
- [ ] Publish step copies from runtime static output path into publication worktree `dashboard/`.
- [ ] Existing payload schema and metric semantics remain unchanged.
- [ ] Drift-check/build-stamp logic continues to work with new output location.

## Non-Goals

- [ ] No change to metric semantics.
- [ ] No synthetic metrics.
- [ ] No dashboard UI redesign.
- [ ] No publication branch structure redesign (still publishes `dashboard/` for Pages).

## Preconditions

- [ ] Branch is up to date with `main`.
- [ ] Latest metrics runner and publish hardening commits are present.
- [ ] Local env uses project `.venv`.
- [ ] CI green before opening PR.

## Implementation Checklist

### 1) Output Path Migration

- [ ] Define new canonical static output path (example: `metrics/output/dashboard/static/`).
- [ ] Update Svelte static adapter output path to runtime location.
- [ ] Update dashboard build script to copy/build into runtime static path.
- [ ] Keep all dashboard source/build inputs tracked in git:
  - `metrics/dashboard/src/**`
  - `metrics/dashboard/package.json`
  - `metrics/dashboard/package-lock.json`
  - `metrics/dashboard/svelte.config.js`
  - `metrics/dashboard/vite.config.js`

### 2) Publish Pipeline Wiring

- [ ] Update publish sync source from repo-root static output to runtime static output path.
- [ ] Keep destination unchanged: publication worktree `dashboard/`.
- [ ] Keep atomic flow: Build/Locate -> Validate -> Copy -> Commit -> Push.
- [ ] Remove/disable fallback paths that can publish stale statics.

### 3) Drift-Check and Build-Stamp

- [ ] Move or mirror `.build-stamp` to runtime static output location.
- [ ] Update fingerprint checks to read/write stamp at runtime location.
- [ ] Ensure unchanged source does not trigger rebuild.
- [ ] Ensure hash filename churn in dist does not count as drift.

### 4) Git Tracking and Ignore Policy

- [ ] Confirm generated static output paths are ignored.
- [ ] Ensure no generated dashboard static files are tracked on `main`.
- [ ] Keep only sentinel ignore files tracked where needed (for empty dir behavior).

### 5) Docs and Operator Guidance

- [ ] Update metrics runtime docs for new source-of-truth static path.
- [ ] Update publish pipeline docs to reference runtime static source.
- [ ] Add operator troubleshooting note for build-stamp location and drift diagnostics.

## Test Plan Checklist

### Unit Tests

- [ ] Update/add tests for new static output path usage.
- [ ] Update/add tests for publish copying from runtime static path.
- [ ] Update/add tests for build-stamp read/write at new location.
- [ ] Keep existing no-op behavior tests for unchanged commit.

### Integration/Smoke Tests

- [ ] Run `metrics-runner run` twice on unchanged commit -> second run is clean skip.
- [ ] Run publish twice on unchanged source -> second publish uses reuse mode and no churn.
- [ ] Validate payload fields and schema unchanged.
- [ ] Validate complexity mix and breakdown consistency remains correct.

### Determinism Checks

- [ ] Rebuild with unchanged source -> no publish-triggering drift.
- [ ] Confirm dist hash changes do not create functional drift alerts.

## Acceptance Criteria

- [ ] `main` branch does not track generated dashboard statics.
- [ ] Publish output is correct in publication branch `dashboard/`.
- [ ] No regressions in metrics payload schema.
- [ ] No regressions in unchanged-commit state machine behavior.
- [ ] Tests added/updated and green.
- [ ] Dry-run and one real publish verification results attached to PR description.

## PR Requirements (Single Controlled PR)

- [ ] One PR only for this migration (unless approved exception).
- [ ] PR description includes:
  - [ ] Before/after path map
  - [ ] Risk assessment
  - [ ] Rollback procedure
  - [ ] Verification command outputs
- [ ] Required reviewers tagged.
- [ ] Merge method agreed (squash/rebase/merge commit).

## Rollback Plan

- [ ] Revert PR commit(s) restoring previous static source path.
- [ ] Re-run one full metrics cycle and publish.
- [ ] Confirm publication branch dashboard content and payload integrity.

## Post-Merge Validation

- [ ] Run one scheduled or manual poller cycle.
- [ ] Run one publish and verify status payload.
- [ ] Confirm no static churn appears on `main` from normal operation.
- [ ] Confirm dashboards are still served correctly from publication branch.

## Notes / Decisions

- Decision log:
  - 
- Open risks:
  - 
- Follow-ups (if any):
  - 
