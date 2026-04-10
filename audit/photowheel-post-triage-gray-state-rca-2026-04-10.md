# PhotoWheel Post-Triage Gray State — Root Cause Analysis

**Date:** 2026-04-10
**Type:** Functional Defect — Diagnostic (read-only investigation)
**Status:** RCA complete; fix not yet implemented

---

## Executive Summary

After accepting or rejecting an item in the staging queue, all visible PhotoCard
thumbnails enter a permanently gray (skeleton) state. The UI appears to "flash"
every ~300ms and recovers only when the user scrolls. The root cause is NOT a
missing focus-advance step as initially hypothesised. It is a two-layer defect:

1. PhotoCard image-state reset is keyed on item prop reference identity, not
   on sha256 value. The store replaces the items array twice (optimistic +
   revalidation), creating new object references for all items on both passes.
   The second pass resets imageState to 'loading' but provides no mechanism
   to exit, because the img src is unchanged and no new onload event fires.

2. The skeletonPulse CSS animation (350ms cycle) creates the appearance of
   periodic retrying. No network retry loop exists.

---

## Symptom Description (authoritative)

After accepting or rejecting an item in the staging queue:

1. The audit trail shows the triage action is correctly applied.
2. The backend queue state is correct (item removed from pending).
3. The frontend enters a degraded state:
   - The active photo becomes gray.
   - All thumbnails become gray.
   - Every ~300ms the UI "flashes" as if retrying a load.
   - The UI recovers instantly when the user scrolls left or right.
4. The issue is 100% reproducible.
5. The issue does NOT occur when navigating normally (only after triage).

---

## Operator Hypothesis

After triage, the frontend keeps the same activeIndex and tries to re-fetch the
now-removed item. The PhotoWheel attempts to load a non-existent slot
repeatedly. The render-window and preload logic enter a retry loop. A missing
"advance focus to next valid item" step is the root cause.

### Verdict: Partially correct, but misidentifies the exact mechanism.

Correct elements:
- activeIndex stays at K after triage. This is expected and correct.

Incorrect elements:
- The frontend does NOT re-fetch the removed item. The removed item leaves
  items[] on the first optimistic write.
- There is no retry loop. The "retrying" appearance is a CSS shimmer animation.
- A missing "advance focus" step is not the root cause. Focus advancement is
  implicit and working correctly: items[K] becomes the successor item.

---

## Exact Causal Chain

### Step 1 — Optimistic removal (correct)

triageItem runs state.items.filter() synchronously and removes item_K. The
store emits a new items array object. Every element is a fresh array reference
even though only one item was removed. activeIndex stays at K. items[K] is now
item_{K+1}.

### Step 2 — First effect cascade

+page.svelte derives items and activeIndex from the store. Both change (items is
a new array). PhotoWheel receives new items prop. Each visible PhotoCard receives
a new item prop object from the new array.

### Step 3 — PhotoCard $effect fires for all visible slots

The effect body is:

    $effect(() => { item.sha256; imageState = 'loading'; })

In Svelte 5, this effect tracks the item prop signal. When item is replaced with
a new object reference (even carrying the same sha256 value), the effect re-runs.
imageState is reset to 'loading' for every visible slot simultaneously. The
skeleton renders. Images are hidden (opacity: 0).

### Step 4 — Center slot has a different sha256 — correct path

The center slot was showing item_K. Now it shows item_{K+1} (different sha256,
different URL). Svelte updates the src attribute. The browser starts loading
item_{K+1}'s thumbnail. If preloaded (distance <= PRELOAD_RADIUS = 3), it hits
the cache. onload fires. imageState = 'loaded'. Center slot recovers.

### Step 5 — Revalidation (the irrecoverable blow)

After the API call succeeds, triageItem calls getStagingPage(null, refreshLimit).
The response replaces the entire items array in the store:

    items: page.items ?? [],  // fresh array, new object references
    activeIndex: Math.min(revalidatedActiveIndex, Math.max(items.length - 1, 0))

The fresh page contains the same logical items in the same positions. The store
emits a second new items array. Every slot gets a new object reference again.

### Step 6 — Second effect cascade permanently stuck

PhotoCard $effect fires for all visible slots again. imageState = 'loading' for
all.

For the center slot: items[K] = item_{K+1} — same sha256 as already loaded
during Step 4. Svelte diffs the src attribute: value is identical. No DOM
update. No network request. No onload event. imageState is stuck at 'loading'
with no mechanism to exit. Same for all neighbor slots whose sha256 was already
set in Step 4.

### Step 7 — The "300ms flash" is the skeleton shimmer

--duration-slow: 350ms. The skeleton animation is:

    animation: skeletonPulse 350ms var(--easing-default) infinite;

A gradient band sweeps from offset 200% to -200% at 350ms per cycle. The
operator observes this continuous shimmer as "the UI flashing as if retrying a
load every ~300ms." No retry is happening.

### Step 8 — Scrolling recovers because it forces genuine sha256 changes

onSelect(K±1) calls setActiveIndex, changing activeIndex to K±1. All slot
indices shift. Each slot is assigned a genuinely different item with a different
sha256. Svelte updates src attributes. Browsers load new images (from cache or
network). onload fires. imageState = 'loaded' for all slots. Full recovery.

---

## State Transition Diagram

### BEFORE TRIAGE

    items:        [A, B, C*, D, E]   (* = active, index 2)
    activeIndex:  2
    focusedItem:  C
    slots:
      slotPos 4 -> itemIndex  0 -> A  imageState=loaded
      slotPos 5 -> itemIndex  1 -> B  imageState=loaded
      slotPos 6 -> itemIndex  2 -> C  imageState=loaded  (center, active)
      slotPos 7 -> itemIndex  3 -> D  imageState=loaded
      slotPos 8 -> itemIndex  4 -> E  imageState=loaded
    preloads: B, D, E (within PRELOAD_RADIUS = 3)
    interactionState: IDLE

### AFTER OPTIMISTIC REMOVAL (sync, same tick as triage action)

    items:        [A, B, D, E]
    activeIndex:  2                  (unchanged -- Math.min(2, 3) = 2)
    focusedItem:  D                  (items[2] = D now)
    loading:      true
    slots:
      slotPos 4 -> itemIndex  0 -> A  imageState=loading  (item ref changed -> effect fired)
      slotPos 5 -> itemIndex  1 -> B  imageState=loading  (item ref changed -> effect fired)
      slotPos 6 -> itemIndex  2 -> D  imageState=loading  (new sha256 -> new src -> browser loads)
      slotPos 7 -> itemIndex  3 -> E  imageState=loading  (item ref changed -> effect fired)
      slotPos 8 -> itemIndex  4 -> (not rendered, out of bounds)
    Note: A, B, E have same sha256 as before but new object references.
          D has genuinely new sha256 -> new src -> browser loads it.

### AFTER SERVER CONFIRMATION + REVALIDATION (~100-400ms later)

    items:        [A', B', D', E']   (fresh objects from getStagingPage, same sha256 values)
    activeIndex:  2                  (revalidatedActiveIndex = 2, unchanged)
    focusedItem:  D'                 (same logical item, new object reference)
    loading:      false
    slots:
      slotPos 4 -> itemIndex  0 -> A'  imageState=loading  (STUCK -- src unchanged, no onload)
      slotPos 5 -> itemIndex  1 -> B'  imageState=loading  (STUCK -- src unchanged, no onload)
      slotPos 6 -> itemIndex  2 -> D'  imageState=loading  (STUCK -- D loaded in Step 4,
                                                             src unchanged, no onload)
      slotPos 7 -> itemIndex  3 -> E'  imageState=loading  (STUCK -- src unchanged, no onload)
    skeletonPulse: RUNNING at 350ms cycle

### BEFORE USER SCROLLS (steady degraded state)

    items:        [A', B', D', E']
    activeIndex:  2
    imageState:   loading for all visible slots (stuck indefinitely)
    Visual:       all thumbnails gray, 350ms shimmer in every card

---

## Failure Mode Classification

| Mode                                                  | Present | Notes                                                      |
|-------------------------------------------------------|---------|------------------------------------------------------------|
| Missing state transition                              | No      | Optimistic removal correctly sets next item as active      |
| Stale activeIndex pointer                             | No      | activeIndex correctly points to next item after removal    |
| Race between optimistic removal and revalidation      | Partial | Revalidation triggers second effect cascade, not a race    |
| Render-window underflow                               | No      | RENDER_RADIUS=5 provides 11 slots                          |
| Preload retry loop                                    | No      | Preload effect runs twice (once per store write), not loop |
| Stale component UI state (spurious effect re-run)     | YES     | Root cause: imageState stuck after reference-identity reset|
| Infinite skeleton animation perceived as periodic retry | YES   | skeletonPulse 350ms matches "~300ms flash" report          |

---

## Conceptual Fix Design

### Fix 1 — Primary: photocard image-state should track sha256 value, not item reference identity

The signal that should trigger an imageState reset is "the sha256 value changed
to a new photo," not "the item object was replaced." The effect should compare
item.sha256 value explicitly. If the same sha256 arrives via a new object
reference (which happens on every store revalidation), imageState should be left
unchanged.

This makes the effect idempotent for repeated delivery of the same logical item,
rather than firing on every reference change.

### Fix 2 — Supporting: identity preservation during revalidation

When the revalidation data arrives, the store could merge it with the current
state by preserving object references for items whose sha256 has not changed.
Only introduce new references for genuinely new or modified items. This prevents
PhotoCard components from receiving reference changes for items they are already
correctly rendering.

This addresses the problem at the source but is architecturally more complex
than Fix 1 alone.

### Fix 3 — UX gap: entrance animation after triage

The activeIndex does not change numerically after triage (item_K is removed, K
now points to K+1). The Phase 2 WAAPI animation (keyed on activeIndex changing)
does not fire. A new item silently appears in the center slot with no motion
cue.

To signal queue advancement, an explicit "content-changed-at-this-slot"
notification must be delivered to PhotoWheel after triage completion. This
could be a new event channel, a dedicated trigger prop (e.g., sequenceId that
increments on triage), or an onTriageComplete callback. The wheel reacts to
this signal to play the appropriate directional entrance animation.

---

## Edge Cases Requiring Coverage

| Scenario                                     | Required behavior                                                     |
|----------------------------------------------|-----------------------------------------------------------------------|
| Normal triage (middle item)                  | Next item shown, loaded, animated                                     |
| Triage last item                             | Previous item shown, loaded, animated in reverse direction            |
| Triage last item of single-item queue        | EmptyState shown immediately, no image loading                        |
| Revalidation returns same items              | No visible change to already-loaded neighbor slots                    |
| Revalidation returns new items               | Genuinely new items get fresh imageState='loading', load normally     |
| Error during API call (snapshot restored)    | Restored items must not re-trigger 'loading' for already-loaded slots |
| Rapid double-triage                          | Per-component value comparison must be race-condition-free            |

---

## Non-Goals

The following must NOT be changed as part of the fix:

- Phase 1 invariants: absolute stage layout, slot positioning, CSS transforms,
  z-index hierarchy.
- Phase 2 WAAPI entrance animation: centerSlotEl.animate() call, timing curve
  (cubic-bezier(0.2, 0, 0, 1), 200ms), and directional logic.
- RENDER_RADIUS = 5 and PRELOAD_RADIUS = 3.
- activeIndex arithmetic: clampIndex, computeWheelStep, all navigation logic.
- The loading="lazy" attribute on non-center slot img elements.
- The optimistic removal formula: filter() + Math.min(activeIndex, length-1).
- The skeleton animation itself (it should stop showing when the fix lands).

---

## Acceptance Criteria

| # | Criterion                                                                                                          | Verification                                               |
|---|--------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------|
| 1 | After triage, center slot shows successor item without ever entering permanently gray state.                       | data-state=loaded on .thumb after triage                   |
| 2 | Neighbor slots already loaded and logically unchanged remain in imageState='loaded' throughout triage cycle.       | Assert data-state=loaded on non-center slots after triage  |
| 3 | Skeleton appears at most twice per triage cycle and resolves within one network round-trip.                        | Assert skeleton absent within 1s of triage completion      |
| 4 | Scrolling before and after triage produces the same rendered result.                                               | Triage -> verify state; scroll -> verify same state        |
| 5 | Triaging the last item in a multi-item queue shows the previous item correctly.                                    | Drain to 1 remaining item before last -> assert prev shown |
| 6 | Triaging the only item shows EmptyState with no skeleton visible.                                                  | Single-item queue -> triage -> assert EmptyState, no skel  |
| 7 | A directional entrance animation plays at the center slot after triage completes.                                  | centerSlotEl.getAnimations() non-empty post-triage         |
| 8 | Rapidly triaging two items in succession leaves no slot permanently stuck in loading state.                        | 2 triages within 50ms -> wait 2s -> no slot in 'loading'   |
