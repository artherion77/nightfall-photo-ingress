# E2E Test Specification - PhotoWheel Post-Triage Gray-State Fix

## Scope
This specification defines the e2e coverage plan for validating Step A and Step B together, without relying on nondeterministic staging data.

## Test Suite Objectives
1. Validate sha-based PhotoCard state transitions.
2. Validate identity-preserving store revalidation behavior.
3. Cover RCA acceptance criteria AC1 through AC8.
4. Prevent regressions in triage, queue boundary, and animation behaviors.

## Test Module Integration Target
Planned module name in existing suite:
- tests/e2e/test_photowheel_post_triage_gray_state_playwright.py

The implementation module is planned; this document is test design only.

## Selector and Assertion Contract

### Selector Strategy
1. Stable selectors for:
- PhotoWheel root.
- Each visible slot.
- Center slot.
- Triage accept and reject actions.
- Empty-state container.

2. Per-card state observability:
- data-state=loading for skeleton phase.
- data-state=loaded for image-visible phase.
- data-state=error for failure phase.

3. Slot observability:
- Slot position attribute to distinguish center and neighbors.

### State Detection Rules
1. Skeleton state
- data-state equals loading.

2. Loaded state
- data-state equals loaded.
- image element is visible.

3. Error state
- data-state equals error.

### Animation Detection Rules
1. Query center-slot animation list immediately after triage transition settlement window.
2. Assert presence of expected entrance animation activity.
3. Assert by animation presence and timing window, not pixel-diff.

## Deterministic Data Strategy

1. Queue seeding
- Seed deterministic queue fixtures with stable sha identities and order.

2. Scenario profiles
- Baseline identical revalidation.
- Reduced payload profile.
- Expanded payload profile.
- Reordered payload profile.
- Rollback-on-error profile.

3. Isolation
- Reset seeded queue before each test or test group.
- Prevent coupling to live ingestion pipeline.

4. Flake prevention
- Use explicit readiness and completion markers.
- Avoid hard sleeps as primary synchronization.
- Use bounded waits with actionable diagnostics.

## Test Cases

### TC-01 Same-Sha Revalidation Is Idempotent
Purpose
- Confirm unchanged sha revalidation does not force loaded cards back to loading.

Preconditions
- Seed queue with at least five items.
- Ensure visible slots reach loaded state.

Steps
1. Perform one triage action at center slot.
2. Allow revalidation profile that returns same surviving identities.
3. Observe center and visible neighbors after revalidation settles.

Expected Outcome
- No visible card remains in loading beyond bounded settle window.
- Unchanged neighbors stay loaded.

### TC-02 Genuine Sha Change Enters Loading Then Loaded
Purpose
- Confirm new media identity transitions correctly.

Preconditions
- Seed queue with distinct sha values.

Steps
1. Triage center item.
2. Observe successor in center.

Expected Outcome
- Center transitions loading to loaded exactly once for that transition epoch.

### TC-03 No Persistent Gray Without User Scroll
Purpose
- Validate defect elimination directly.

Preconditions
- Seed queue with at least four items.

Steps
1. Triage once.
2. Do not scroll.
3. Wait for post-triage settle window.

Expected Outcome
- No visible slot is stuck at loading.

### TC-04 Rapid Double Triage Race Safety
Purpose
- Ensure stale asynchronous events cannot overwrite final state.

Preconditions
- Seed queue with at least six items.

Steps
1. Trigger two triage actions in rapid succession.
2. Wait for final revalidation settle.

Expected Outcome
- Final center corresponds to second triage outcome.
- No visible slot remains stuck in loading.

### TC-05 Snapshot Rollback After Error
Purpose
- Validate rollback recovery path under failed triage.

Preconditions
- Rollback-on-error profile enabled for first triage request.

Steps
1. Trigger triage that fails server-side.
2. Observe rollback state after error handling settles.

Expected Outcome
- Restored items converge to loaded for unchanged identities.
- No persistent loading state remains.

### TC-06 Identical Revalidation Payload Preserves Stability
Purpose
- Validate Step B identity-preserving behavior for unchanged payload.

Preconditions
- Baseline identical revalidation profile.

Steps
1. Trigger explicit revalidation cycle with no logical content change.
2. Observe all visible cards.

Expected Outcome
- No loaded-to-loading regression for unchanged cards.
- Visual churn is minimal and bounded.

### TC-07 Fewer-Items Revalidation
Purpose
- Validate shrink behavior and index clamp correctness.

Preconditions
- Reduced payload profile available.

Steps
1. Triage near queue tail.
2. Revalidate with reduced server payload.

Expected Outcome
- activeIndex remains valid via clamp behavior.
- Correct center item is shown and loaded.

### TC-08 More-Items Revalidation
Purpose
- Validate expansion behavior with mixed reuse and insertion.

Preconditions
- Expanded payload profile available.

Steps
1. Triage once.
2. Revalidate with additional items injected.

Expected Outcome
- Existing unchanged items remain stable.
- New items load normally when entering visible window.

### TC-09 Reordered Revalidation Payload
Purpose
- Validate server-order authority with identity stability.

Preconditions
- Reordered payload profile available.

Steps
1. Trigger revalidation with same identities in different order.
2. Observe visible slot mapping and card states.

Expected Outcome
- Slot order follows server order.
- No persistent loading for unchanged identities.

### TC-10 Last-Item Triage in Multi-Item Queue
Purpose
- Validate boundary behavior at queue tail.

Preconditions
- Seed queue where active item is final index and total count is at least two.

Steps
1. Triage active last item.
2. Observe resulting center item.

Expected Outcome
- Previous item becomes center and reaches loaded state.

### TC-11 Single-Item Queue to Empty State
Purpose
- Validate empty queue transition correctness.

Preconditions
- Seed queue with exactly one item.

Steps
1. Triage single item.
2. Observe post-triage view.

Expected Outcome
- Empty state appears.
- No persistent skeleton remains visible.

### TC-12 Post-Triage Entrance Animation Trigger
Purpose
- Validate animation trigger requirement after triage completion.

Preconditions
- Seed queue with at least three items.

Steps
1. Triage center item.
2. Inspect center-slot animation activity in immediate post-triage window.

Expected Outcome
- At least one expected entrance animation instance is observed.

## Coverage Matrix
1. AC1 covered by TC-02 and TC-03.
2. AC2 covered by TC-01 and TC-06.
3. AC3 covered by TC-03.
4. AC4 covered by TC-03 plus optional post-scroll parity check.
5. AC5 covered by TC-10.
6. AC6 covered by TC-11.
7. AC7 covered by TC-12.
8. AC8 covered by TC-04.
9. Step B identity-preservation behavior covered by TC-06 through TC-09.

## Exit Criteria
1. All test cases pass under deterministic fixture profiles.
2. No persistent loading state occurs after triage without user scroll.
3. Queue boundary and animation requirements remain stable across repeated runs.