# Visual Invariants Click Flake Investigation (2026-04-09)

## Summary

The intermittent failure in the combined E2E run was test-side nondeterminism, not a product regression from thumbnail-loading fixes.

## Scope Investigated

- Failing assertion location:
  - `webui/tests/e2e/photowheel.visual-invariants.spec.ts`
  - test: `wheel and click navigation preserve the animated visual contract`
  - assertion: `expect(clickChanged).toBeTruthy()`
- Runtime behavior of click navigation in:
  - `webui/src/lib/components/staging/PhotoWheel.svelte`

## Findings

1. The original flaky assertion path depended on a click transition in the visual-invariants spec.
2. In `PhotoWheel.svelte`, only the active center slot has a click handler; adjacent slot clicks are not a supported navigation contract.
3. A deeper combined-run source of nondeterminism remained even after replacing click with keyboard: residual `MOMENTUM`/`TRANSITIONING` state from the immediately preceding wheel step could still alter active selection during subsequent assertion snapshots.
4. This produced failures where a navigation step was detected, but before/after signature snapshots matched due to state continuing to settle.
5. The failure mode is therefore a sequencing issue in the test harness, not evidence of thumbnail-loading regressions.

## Decision

Adjusted the test to validate supported deterministic inputs and explicit state settling:

- renamed the test from wheel+click to wheel+keyboard
- replaced click step with keyboard step for the second transition assertion
- added `waitForWheelIdle()` helper that waits for `data-interaction-state="IDLE"`
- used idle waits before and after the keyboard verification step

No product code change was made.

## Validation Evidence

- Thumbnail behavior wrapper test: pass
- Visual invariants wrapper test: pass in isolated run
- Combined 3-suite run: pass after settling fix (no visual-invariants failure observed)

## Risk Assessment

- Low risk: change is test-only and aligns assertions to supported deterministic behavior.
- Residual note: if click-to-select for non-active slots is desired in future UX, it should be implemented explicitly in product code and covered by dedicated interaction tests.
