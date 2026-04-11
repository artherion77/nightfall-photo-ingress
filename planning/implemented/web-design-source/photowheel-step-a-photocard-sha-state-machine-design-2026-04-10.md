# PhotoWheel Defect Fix - Step A

Status: Implemented


## Scope
This document defines the design for Step A only: PhotoCard state transitions must depend on sha256 value changes, not object reference identity changes.

## Problem Statement
The current card behavior resets image state when a new item object reference is delivered, even when the sha256 value is unchanged. During optimistic removal and revalidation, unchanged media objects are re-delivered as new references. This creates false loading resets and can strand the UI in loading when the image source string does not change and no load event is emitted.

## Step A Design Goal
Guarantee that PhotoCard transitions to loading only when the media identity changes (sha256 delta), while remaining idempotent for repeated delivery of the same sha256.

## PhotoCard State Machine

### States
1. loading
- Skeleton visible.
- Image hidden.

2. loaded
- Image visible.
- Skeleton hidden.

3. error
- Error placeholder visible.
- Image hidden.

### Inputs
1. current sha256 value for the card.
2. previous sha256 value retained by the card.
3. image load success event.
4. image load error event.
5. component lifecycle boundaries (mount and unmount).

### Transition Rules
1. Any state to loading
- Trigger only when current sha256 is present and current sha256 differs from previous sha256.

2. loading to loaded
- Trigger only by load success event that corresponds to the current sha256 transition epoch.

3. loading to error
- Trigger only by load error event that corresponds to the current sha256 transition epoch.

4. loaded to loading
- Allowed only for a genuine sha256 change.

5. error to loading
- Allowed only for a genuine sha256 change.

### Forbidden Transitions
1. loaded to loading when current sha256 equals previous sha256.
2. error to loading when current sha256 equals previous sha256.
3. Any transition caused solely by object reference replacement.
4. Any transition caused by unrelated prop changes.

## Previous sha256 Tracking
1. Maintain a per-card previous sha256 checkpoint.
2. Update this checkpoint only when a new sha256 transition is accepted.
3. Do not rewrite checkpoint when identical sha256 is replayed from store revalidation.

## Idempotency Contract
1. Re-delivery of same sha256 is a no-op for image state.
2. Repeated identical payloads must not re-show skeleton.
3. Revalidation with same sha256 must preserve loaded or error terminal state.

## Race Condition Control (Rapid Triage)
1. Associate each accepted sha256 change with a monotonically increasing local transition epoch.
2. Accept load or error events only if event epoch equals current epoch and event sha256 equals current sha256.
3. Ignore late events from superseded epochs.
4. This prevents stale asynchronous events from overwriting newer state.

## Effect Logic (Textual)

### Observed Values
1. The sha256 value only.

### Required Comparisons
1. If sha256 is missing: no image transition for media identity.
2. If sha256 equals previous sha256: no state transition.
3. If sha256 differs from previous sha256: begin new transition epoch and move to loading.

### Required Transitions
1. On sha delta: set loading.
2. On matching load success: set loaded.
3. On matching load error: set error.

### Transitions That Must Not Occur
1. loading reset on object-only change.
2. loading reset on identical src value after revalidation.
3. State updates from stale load or error events.

## Compatibility Analysis

### Lazy Loading
1. Compatible.
2. Delayed image loading for non-center slots remains valid.
3. Cards remain in loading only until legitimate event completion.

### WAAPI Entrance Animation
1. Orthogonal.
2. Step A does not alter wheel movement or animation trigger logic.
3. Existing animation behavior remains unchanged.

### Preload Window
1. Compatible with preload strategy.
2. Preloaded unchanged neighbors remain loaded across revalidation.
3. No false preload-driven state resets.

### skeletonPulse Animation
1. Visual primitive remains unchanged.
2. Its continuous display is reduced because false loading re-entry is removed.
3. Any remaining pulse indicates genuine first-load or active failure.

## Edge Case Handling

1. Same sha256 delivered twice
- No state change.
- No skeleton reappearance.

2. New sha256 delivered
- Immediate transition to loading.
- Deterministic transition to loaded or error.

3. Empty queue
- Card is absent or unbound; no synthetic loading transition.

4. Rapid triage before revalidation settles
- Multiple sha changes are resolved by epoch gating.
- Final visible state corresponds to latest sha change only.

5. Snapshot rollback after triage error
- If rollback sha differs from current: loading then loaded or error for rollback sha.
- If rollback sha equals current: no reset.

## Step A Acceptance Criteria
1. Unchanged sha256 after revalidation does not transition loaded to loading.
2. Genuine sha256 change always transitions to loading exactly once per accepted transition epoch.
3. No slot remains permanently in loading when src remains unchanged across revalidation.
4. Same-sha replay is idempotent for both loaded and error states.
5. Rapid double triage cannot be overwritten by stale load or error events.
6. Lazy loading semantics remain unchanged for non-center cards.
7. Error state appears only for current sha256 load failures.
8. Visual behavior after triage no longer depends on user scroll to recover from false loading.
