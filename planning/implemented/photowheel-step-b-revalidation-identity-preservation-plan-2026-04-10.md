# PhotoWheel Defect Fix - Step B

## Scope
This document defines the Step B design only: identity-preserving revalidation for stagingQueue so unchanged media items retain object identity across server refresh.

## Problem Statement
The store currently replaces the full items array on revalidation, creating new object references for all items. This amplifies reactive churn and previously contributed to false image loading resets. Step B reduces this churn by preserving identities where content identity is unchanged.

## Step B Design Goal
Preserve object identity for unchanged media items during revalidation while keeping server order authoritative and preserving all Phase-1.5 invariants.

## Conceptual Merge Algorithm

### Inputs
1. current items snapshot from client state.
2. server items snapshot from revalidation response.

### Identity Key Strategy
1. Primary stable key: sha256.
2. If needed for collision safety: composite key of sha256 plus stable backend identifier.

### Matching Strategy (No O(N^2))
1. Build a map from current items keyed by identity key.
2. Walk server items exactly once.
3. For each server item:
- If matching identity exists and no identity-level change is detected, reuse existing object reference.
- If identity is new or changed, create a new object reference.

### Output Construction
1. Build merged output in exact server order.
2. Drop identities not present in server response.
3. Recompute activeIndex with existing clamp invariant against merged length.

### Complexity
1. Map build O(N).
2. Merge pass O(M).
3. Total O(N + M), memory O(N).

## Stale Reference Prevention
1. Never reuse references for identities absent from server response.
2. Never reuse references when identity key changed.
3. Apply merge atomically per revalidation generation to avoid mixed snapshots.

## Interaction Analysis

### Optimistic Removal
1. Unchanged behavior.
2. Optimistic removal remains immediate and local.
3. Revalidation then stabilizes surviving identities via merge.

### activeIndex
1. Existing clamp policy remains unchanged.
2. If queue shrinks, activeIndex clamps to valid range.
3. If queue grows, activeIndex remains valid.

### Render Window
1. Slot math remains unchanged.
2. Fewer false object changes reduce unnecessary visible slot recalculation.

### Preload Window
1. Preload radius logic remains unchanged.
2. Unchanged identities avoid redundant preload-triggered effects.

### Interaction with Step A
1. Step A enforces sha-based state transitions at card level.
2. Step B reduces frequency of unnecessary prop churn from store.
3. Combined effect is both correctness and stability under revalidation.

## Failure Mode Analysis

1. Server returns fewer items
- Missing identities are dropped.
- Reused identities remain stable.
- activeIndex clamps to new last index.

2. Server returns more items
- Existing matching identities reused.
- Additional items inserted as new references in server order.

3. Server returns reordered items
- Identity references reused where keys match.
- Positions update to server order without forced identity recreation.

4. Server returns identical items
- Full identity reuse expected.
- Minimal reactive churn expected.

## Migration Plan

1. Introduce merge strategy behind existing store surface.
- No consumer API change.
- Keep optimistic and revalidation orchestration intact.

2. Validate invariants before rollout.
- Preserve Phase-1.5 geometry, index semantics, render and preload radii, and action semantics.

3. Instrument rollout diagnostics.
- Track reused versus replaced identities during revalidation.
- Verify high reuse rate for identical payloads.

4. Staged enablement.
- Enable in controlled environment.
- Compare against baseline behavior and e2e outcomes.

5. Safe fallback
- If merge preconditions fail, fall back to full replacement path for that cycle while logging reason.

## Step B Acceptance Criteria
1. Identical revalidation payload preserves identity for all unchanged items.
2. Partially changed payload preserves identities for unchanged items and replaces only changed or new items.
3. Reordered payload keeps server order while preserving matching identities.
4. Fewer-items payload drops absent identities and clamps activeIndex correctly.
5. More-items payload adds new identities without perturbing unchanged ones.
6. No stale references survive when identities disappear from server payload.
7. Combined with Step A, no persistent post-triage gray-state remains.
8. No regressions in existing Phase-1.5 interaction invariants.