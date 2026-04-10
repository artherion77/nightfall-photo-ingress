# PhotoWheel Fidelity Improvement Plan

Status: Complete (Chunks 0-5 Complete)
Date: 2026-04-09
Authority: design/web/photowheel-visual-design-decisions.md (Decisions E–K)
Predecessors: Phase 1 (Stage Model Migration — COMPLETE), Phase 2 (Motion / VIS-5 — COMPLETE)
Reference Mock: design/ui-mocks/Astronaut photo review interface.png

---

## Scope

This plan closes the visual and interaction fidelity gap between the
current staging implementation and the approved mockup. It covers
Decisions E through K from the authoritative design document.

## Out of Scope

- Bulk actions, multi-select
- Backend changes, auth changes
- Animation rework (Phase 2 WAAPI is preserved)
- Thumbnail loading logic, preload logic
- New features unrelated to review flow
- Viewports smaller than iPad 10th gen landscape (1180 × 820)

## Phase 1 and Phase 2 Preservation

All chunks in this plan must preserve:

- **Phase 1 structural invariants**: center-slot centering (D.3), tier
  transforms (B.2), render-window (RENDER_RADIUS=5), input handling
  (keyboard, wheel, touch, momentum). Unit tests: 36/36.
- **Phase 2 motion invariants**: WAAPI content-entrance animation on
  activeIndex change (200ms, cubic-bezier), VIS-5 motion diversity.
  E2E centering tolerance ±4px.
- **Existing test suites**: centering-perceptual, visual-invariants,
  thumbnail-behavior specs must continue to pass unchanged unless a
  chunk explicitly documents a required test update.

Chunks that modify the slot geometry (e.g. card width) must revalidate
the centering E2E spec and update tolerance if needed.

---

## Chunk 0 — Full-Viewport Layout and Scroll Containment

Priority: P0 (Interaction Correctness)
Invariants: SCR-1, SCR-2, SCR-3, SCR-4, VP-1, VP-2, VP-3

### Goal

Eliminate the vertical scrollbar on the staging page and prevent
scroll chaining from the PhotoWheel to the page.

### Scope

1. Convert the staging page layout to a full-viewport grid that
   distributes vertical space: header (auto) → title (auto) →
   wheel (1fr) → CTA (auto) → footer (auto).
2. Set `height: 100vh` or equivalent viewport constraint on the
   staging page container. Remove `min-height: 100vh` in favor
   of exact `100vh` on `.app-shell`.
3. Add `overscroll-behavior: contain` to the `.wheel` element.
4. Add `touch-action: none` to the `.wheel` element to prevent
   browser-initiated scroll during touch interaction.
5. Replace the wheel's `min-height: 360px` with flex/grid sizing
   that fills available vertical space.
6. Ensure `main` padding is included in the layout budget.

### Non-Goals

- Changing card geometry or visual treatment.
- Responsive behavior below 1180px.
- Modifying the app header or footer.

### Acceptance Criteria

- SCR-1: No vertical scrollbar at 1180 × 820.
- SCR-2: Mouse-wheel inside the wheel does not scroll page.
- SCR-3: `.wheel` has `overscroll-behavior: contain`.
- SCR-4: Touch on wheel does not scroll page.
- VP-1: No vertical scrollbar at minimum viewport.
- VP-2: Wheel fills vertical space between title and CTA.
- VP-3: Below-minimum viewport clips, does not overflow.
- All existing E2E suites pass.

### Files Affected

| File | Change |
|------|--------|
| `webui/src/routes/staging/+page.svelte` | Layout grid, height constraint |
| `webui/src/lib/components/staging/PhotoWheel.svelte` | `overscroll-behavior`, `touch-action`, remove `min-height` |
| `webui/src/routes/+layout.svelte` | Ensure `.app-shell` is exactly `100vh` |

---

## Chunk 1 — Active Photo Visual Dominance

Priority: P1 (Visual Fidelity)
Invariants: DOM-1, DOM-2, DOM-3, DOM-4

### Goal

Make the active card the dominant visual element, matching the mockup's
proportions where the center photo commands a significant portion of the
viewport.

### Scope

1. Change the base slot width from a fixed 220px to a viewport-relative
   value (e.g. `clamp(280px, 38vw, 480px)`) via the `--slot-width`
   custom property.
2. Recalculate `--slot-offset` to accommodate the wider base.
3. Verify that Tier 1 (0.78×) and Tier 2 (0.60×) scale factors produce
   proportional non-active cards.
4. Adjust `perspective` value on `.wheel` if needed to maintain depth
   illusion at larger card size.
5. Adjust `--space-8` padding-block on `.stage` if the taller card
   causes vertical clipping.

### Non-Goals

- Changing tier scale factors, rotation angles, or overlap offsets.
- Changing the number of rendered slots or RENDER_RADIUS.
- Responsive slot count reduction.

### Acceptance Criteria

- DOM-1: Active card width ≥ 35% of 1180px (≥ 413px) at minimum VP.
- DOM-2: Active card width ≤ 50% of viewport at all sizes.
- DOM-3: Active card area > any CTA button area.
- DOM-4: Thumbnail aspect ratio 4:3 (±1px).
- Centering E2E spec passes (re-run; update tolerance if justified and
  documented).
- Visual-invariants E2E spec passes (VIS-1 through VIS-7).

### Files Affected

| File | Change |
|------|--------|
| `webui/src/lib/components/staging/PhotoWheel.svelte` | `--slot-width`, stage padding, perspective |
| `webui/src/lib/components/staging/PhotoCard.svelte` | Verify `aspect-ratio` holds at new width |

---

## Chunk 2 — CTA Button Redesign

Priority: P1 (Visual Fidelity)
Invariants: ACT-1, ACT-2, ACT-3, ACT-4, ACT-5, ACT-6

### Goal

Redesign the CTA Accept/Reject buttons to match the mockup: large
outlined containers with hand icons, replacing the current small filled
buttons.

### Scope

1. Create a new `TriageCTA.svelte` component (or update the
   `TriageControls` `mode="cta"` branch) that renders:
   - Outlined border (teal / red) with transparent background.
   - Hand icon (✋ SVG or emoji) to the left of label text.
   - Label text at `--text-xl` size.
   - Minimum height 64px.
   - Two-column grid layout.
2. Add `:hover` and `:active` states using the existing glow tokens
   (`--shadow-accept-glow`, `--shadow-reject-glow`).
3. Preserve idempotency-key generation on click.
4. Preserve the `disabled` prop behavior.

### Non-Goals

- Changing inline controls (mode="inline").
- Adding new triage actions (defer remains keyboard-only).
- Animation on button press.

### Acceptance Criteria

- ACT-1: Accept CTA has teal outlined border, no solid fill.
- ACT-2: Reject CTA has red outlined border, no solid fill.
- ACT-3: Both CTAs display a hand icon.
- ACT-4: CTA height ≥ 64px.
- ACT-5: Two-column grid spanning content width.
- ACT-6: Only active card affected by triage action.

### Files Affected

| File | Change |
|------|--------|
| `webui/src/lib/components/staging/TriageControls.svelte` | CTA mode rendering |
| `webui/src/lib/components/common/ActionButton.svelte` | May need variant or new component |
| `webui/src/routes/staging/+page.svelte` | CTA placement in grid |

---

## Chunk 3 — Drag and Drop

Priority: P0 (Interaction Correctness)
Invariants: DND-1, DND-2, DND-3, DND-4, DND-5, DND-6, DND-7

### Goal

Implement functional drag-and-drop from the active card onto the CTA
Accept/Reject buttons.

### Scope

1. Add `draggable="true"` to the center-slot `.slot.is-active` div.
   Set `ondragstart` to populate `dataTransfer` with the item's `sha256`.
2. Non-active slots: ensure `draggable` is absent or `false`.
3. Add `ondragover` + `ondrop` handlers to both CTA buttons:
   - `ondragover`: call `event.preventDefault()` to allow drop; add
     active glow class.
   - `ondragleave`: remove glow class.
   - `ondrop`: extract `sha256`, fire the corresponding triage action
     with an idempotency key.
4. During drag (tracked via a `dragging` state flag):
   - Reduce active card opacity to 0.5.
   - Suppress `handleKeydown`, `handleWheel`, and `handleTouchStart`
     to prevent navigation.
5. On `dragend`: restore active card opacity, clear `dragging` flag,
   re-enable navigation.

### Non-Goals

- Touch-based drag (HTML5 drag API does not support touch natively;
  touch users use buttons or keyboard).
- Custom drag ghost image.
- Drag reordering within the wheel.

### Acceptance Criteria

- DND-1: Active card has `draggable="true"`.
- DND-2: Non-active cards are not draggable.
- DND-3: Drop on Accept CTA triggers accept.
- DND-4: Drop on Reject CTA triggers reject.
- DND-5: Drop outside any target: no side effect.
- DND-6: CTA glow during dragover.
- DND-7: Wheel navigation suspended during drag.

### Files Affected

| File | Change |
|------|--------|
| `webui/src/lib/components/staging/PhotoWheel.svelte` | `draggable`, `ondragstart`, `ondragend`, navigation suppression |
| `webui/src/lib/components/staging/TriageControls.svelte` | `ondragover`, `ondragleave`, `ondrop`, glow classes |
| `webui/src/routes/staging/+page.svelte` | Wire drag state between wheel and controls if needed |

---

## Chunk 4 — Operator-First Metadata

Priority: P2 (Information Architecture)
Invariants: META-1, META-2, META-3, META-4, META-5

### Goal

Move operator-relevant metadata (account, capture time) into the active
card and de-emphasize technical fields (SHA, size, OneDrive ID).

### Scope

1. Modify `PhotoCard.svelte` to show primary metadata (account, capture
   time, filename) below the thumbnail within the card container. Only
   render this metadata block when `active={true}`.
2. Truncate SHA-256 display to ≤ 16 characters everywhere.
3. Format `first_seen_at` as `Captured at HH:MM` (existing
   `formatTimestamp` function already does this).
4. Hide OneDrive ID from default view.
5. Format `size_bytes` as human-readable (e.g. `4.2 MB`) when displayed.

### Non-Goals

- Changing metadata for non-active cards (they show only thumbnail +
  filename, as today).
- Making metadata editable.
- Real-time metadata refresh.

### Acceptance Criteria

- META-1: Account and capture time visible on active card without
  interaction.
- META-2: Primary metadata text ≥ `--text-base` (15px).
- META-3: SHA-256 truncated to ≤ 16 characters.
- META-4: OneDrive ID not visible in default view.
- META-5: Primary metadata visually attached to active card.

### Files Affected

| File | Change |
|------|--------|
| `webui/src/lib/components/staging/PhotoCard.svelte` | Conditional metadata block for active state |

---

## Chunk 5 — Remove Standalone Details Panel; Add Disclosure Sheet

Priority: P2 (Information Architecture)
Invariants: DET-1, DET-2, DET-3, DET-4

### Goal

Remove the `ItemMetaPanel` from the default staging page layout.
Provide secondary metadata via an overlay sheet.

### Scope

1. Remove `<ItemMetaPanel item={selected} />` from
   `staging/+page.svelte`.
2. Add a small "details" icon (ⓘ or similar) on the active card
   that opens a right-side sheet/drawer.
3. Create a `DetailSheet.svelte` component:
   - Slide-in from right, overlays page content.
   - Contains: full SHA-256 (copyable), size, OneDrive ID, any
     future diagnostic fields.
   - Dismissible via close button, Escape, click-outside.
4. The sheet uses `position: fixed` with `z-index: var(--z-overlay)`.
   It does not push or reflow the main layout.

### Non-Goals

- Bottom-sheet mobile pattern.
- Persistent sidebar.
- Modal dialog.
- Sheet animation (slide-in is a nice-to-have but not required).

### Acceptance Criteria

- DET-1: No standalone details panel in default staging view.
- DET-2: Disclosure affordance (icon/link) on active card.
- DET-3: Detail sheet does not cause page reflow or scroll.
- DET-4: Detail sheet dismissible via close, Escape, click-outside.
- VP-1: No vertical scrollbar (removing the panel reduces height).

### Files Affected

| File | Change |
|------|--------|
| `webui/src/routes/staging/+page.svelte` | Remove `ItemMetaPanel` |
| `webui/src/lib/components/staging/PhotoCard.svelte` | Add details icon trigger |
| `webui/src/lib/components/staging/DetailSheet.svelte` | New component |

---

## Execution Order

| Order | Chunk | Priority | Rationale |
|-------|-------|----------|-----------|
| 1 | Chunk 0 — Full-Viewport Layout | P0 | Establishes the layout container that all subsequent chunks depend on. Without this, card sizing and CTA placement cannot be validated. |
| 2 | Chunk 1 — Active Photo Dominance | P1 | Requires the viewport layout from Chunk 0 to validate sizing invariants. Must precede CTA redesign because DOM-3 (card area > button area) depends on knowing the card size. |
| 3 | Chunk 2 — CTA Button Redesign | P1 | Requires layout (Chunk 0) and card sizing (Chunk 1). Provides the drop targets needed by Chunk 3. |
| 4 | Chunk 3 — Drag and Drop | P0 | Requires CTA buttons (Chunk 2) as drop targets. Interaction correctness is P0 but implementation depends on Chunks 0–2. |
| 5 | Chunk 4 — Operator-First Metadata | P2 | Independent of Chunks 2–3, but must follow Chunk 1 (card sizing affects metadata layout). |
| 6 | Chunk 5 — Details Panel Removal | P2 | Depends on Chunk 4 (primary metadata on card). Removing the panel before metadata is on the card would lose information. |

---

## Validation Strategy

After each chunk:

1. Run all three E2E suites:
   - `tests/e2e/test_photowheel_centering_playwright.py`
   - `tests/e2e/test_photowheel_visual_invariants_playwright.py`
   - `tests/e2e/test_photowheel_thumbnail_behavior_playwright.py`
2. Run unit tests: `pytest tests/ -q --ignore=tests/e2e`
3. Rebuild and deploy to staging: `./dev/bin/govctl staging.install`
4. Manual visual inspection against mockup at 1180 × 820 viewport.

If a chunk requires test spec updates (e.g. centering tolerance change
due to wider cards), the update must be documented in the chunk's
commit message and justified against the relevant invariant.

---

## Execution Log

### 2026-04-09 — Chunk 0 Completed

Summary:
- Implemented full-viewport containment on the staging page via local
   grid sizing in `staging/+page.svelte` and wheel-shell shrink rules.
- Added `.wheel { overscroll-behavior: contain; height: 100%; }` and
   converted stage sizing from fixed minimum to parent-fill behavior.
- Preserved root layout stability by keeping `.app-shell` on
   `min-height: 100vh` and constraining overflow to the staging route,
   which avoided mobile click/touch regressions.

Acceptance validation:
- SCR-1, VP-1, VP-3: validated through layout constraints and E2E
   navigation checks with no new page-scroll regressions.
- SCR-2, SCR-4: validated by wheel/touch interaction behavior in the
   visual invariants suite after final layout adjustment.
- SCR-3: validated in code (`overscroll-behavior: contain` on `.wheel`).
- VP-2: validated by 1fr wheel track + full-height wheel/stage sizing.

Test evidence:
- Unit tests: `738 passed, 1 deselected` (known unrelated deselection:
   `test_tmpfs_devices_added_in_create`).
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - FAIL (pre-existing): `test_photowheel_thumbnail_behavior_playwright.py`
      (`C2 C3 C5` desktop fallback assertion expects `error`, receives
      `loaded`; tracked separately in issue #22).

### 2026-04-09 — Chunk 1 Completed

Summary:
- Updated wheel geometry to viewport-relative dominant sizing using
   `--slot-width: clamp(280px, 38vw, min(480px, 50vw))`.
- Recalculated slot spacing for larger cards with
   `--slot-offset: calc(var(--slot-width) * 0.86 + var(--slot-gap))`
   while preserving existing tier transforms and render radius.
- Tuned depth context (`perspective: 860px`) for improved visual
   continuity at the larger active-card width.
- Reduced stage vertical padding to avoid clipping at minimum viewport.
- Updated `PhotoCard` to width-following layout (`width: 100%`) so card
   box and thumbnail remain aligned to slot geometry at all widths.

Acceptance validation:
- DOM-1: satisfied. At 1180px viewport width, preferred active width is
   `38vw = 448.4px` (>= 413px threshold).
- DOM-2: satisfied. Upper bound is constrained by `min(480px, 50vw)`,
   guaranteeing active width <= 50% viewport.
- DOM-3: satisfied by geometry. Active card area at minimum viewport is
   significantly larger than a single CTA button area.
- DOM-4: satisfied. Thumbnail keeps `aspect-ratio: 4 / 3` unchanged.
- Centering/VIS validation: passed without tolerance changes.

Test evidence:
- Staging deploy: `govctl staging.install` run_finished `passed: 5`.
- Unit tests: `738 passed, 1 deselected`.
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - PASS: `test_photowheel_thumbnail_behavior_playwright.py`

### 2026-04-09 — Chunk 5 Completed

Summary:
- Removed default in-flow details panel from staging page layout.
- Added active-card details disclosure affordance (`ⓘ`) in
   `PhotoCard.svelte`.
- Added `DetailSheet.svelte` fixed overlay (right-side drawer) for
   secondary metadata: full SHA-256 (copyable input), size, account,
   and OneDrive ID.
- Wired details open/close flow through `PhotoWheel` and
   `staging/+page.svelte`.
- Implemented close via explicit close button, Escape key, and
   click-outside on backdrop.

Acceptance validation:
- DET-1: No standalone details panel remains in default staging view.
- DET-2: Active card includes explicit details disclosure trigger.
- DET-3: Detail sheet uses fixed overlay (`z-index: --z-overlay`) and
   does not reflow page layout.
- DET-4: Detail sheet dismisses via close, Escape, and click-outside.
- VP-1: Staging page remains clipped/contained with no dependency on
   in-flow metadata panel height.

Compatibility note:
- Thumbnail behavior E2E helper's `hasButton` signal was narrowed to
   fallback-surface buttons only, so new details disclosure button does
   not trigger false failures in thumbnail retry assertions.

Test evidence:
- Staging deploy: `govctl staging.install` run_finished `passed: 5`.
- Unit tests: `738 passed, 1 deselected`.
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - PASS: `test_photowheel_thumbnail_behavior_playwright.py`

### 2026-04-09 — Chunk 4 Completed

Summary:
- Refactored `PhotoCard.svelte` metadata rendering to operator-first
   presentation on active card only.
- Non-active cards now display thumbnail + filename only.
- Active card now displays account and capture time as primary metadata,
   with technical fields de-emphasized.
- Added human-readable size formatting helper and active-only size line.
- Preserved truncated SHA display (`16` chars + ellipsis) where shown.
- Added non-visual `data-sha256` attribute on card root to support
   robust E2E identification without requiring visible SHA text.

Acceptance validation:
- META-1: Account and capture time visible on active card.
- META-2: Primary metadata uses `--text-base` styling.
- META-3: SHA display remains truncated to `<= 16` chars.
- META-4: OneDrive ID not shown in default card view.
- META-5: Primary metadata is directly attached to active card content.

Compatibility note:
- Thumbnail behavior E2E helper previously relied on visible SHA text on
   non-active cards. After Chunk 4 metadata de-emphasis, helper was
   updated to use `data-sha256` fallback matching for non-active slots.

Test evidence:
- Staging deploy: `govctl staging.install` run_finished `passed: 5`.
- Unit tests: `738 passed, 1 deselected`.
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - PASS: `test_photowheel_thumbnail_behavior_playwright.py`

### 2026-04-09 — Chunk 3 Completed

Summary:
- Added active-card drag support in `PhotoWheel.svelte` with
   `draggable="true"`, drag payload (`application/x-nightfall-sha256` +
   `text/plain`), and drag lifecycle hooks (`ondragstart`, `ondragend`).
- Added drag-state gating in wheel input handlers to suspend keyboard,
   wheel, and touch-start navigation while dragging.
- Added visual dragging feedback on active slot (`opacity: 0.5`).
- Added CTA drop-target handling in `TriageControls.svelte`:
   `ondragover`, `ondragleave`, `ondrop`, and glow classes for accept/
   reject targets.
- Wired drag state from wheel to CTA controls in `staging/+page.svelte`
   via `onDragStateChange` -> `dragActive` prop.

Acceptance validation:
- DND-1: Active card is draggable (`draggable="true"`).
- DND-2: Non-active cards remain non-draggable.
- DND-3: Drop on Accept CTA dispatches accept action.
- DND-4: Drop on Reject CTA dispatches reject action.
- DND-5: Drops without expected drag payload produce no side effect.
- DND-6: CTA glow is shown during drag-over (`is-drag-over` classes).
- DND-7: Wheel navigation input is suppressed during drag lifecycle.

Test evidence:
- Staging deploy: `govctl staging.install` run_finished `passed: 5`.
- Unit tests: `738 passed, 1 deselected`.
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - PASS: `test_photowheel_thumbnail_behavior_playwright.py`

### 2026-04-09 — Chunk 2 Completed

Summary:
- Redesigned CTA-mode controls in `TriageControls.svelte` from small
   filled buttons to large outlined action surfaces.
- Added left-side hand icon glyph for both Accept and Reject CTAs.
- Kept inline controls unchanged (`mode="inline"`) and preserved all
   idempotency-key action wiring.
- Preserved disabled behavior via native button `disabled` attribute and
   disabled styling.

Acceptance validation:
- ACT-1: Accept CTA uses teal outline (`border-accept`) with
   transparent background.
- ACT-2: Reject CTA uses red outline (`border-reject`) with
   transparent background.
- ACT-3: Both CTA buttons include hand icon (`&#9995;`).
- ACT-4: CTA `min-height: 64px` enforced in component CSS.
- ACT-5: CTA container remains two-column grid (`1fr 1fr`) across
   content width.
- ACT-6: Triage action targeting unchanged; CTA handlers continue to
   operate on the current active card via existing staging queue wiring.

Test evidence:
- Staging deploy: `govctl staging.install` run_finished `passed: 5`.
- Unit tests: `738 passed, 1 deselected`.
- E2E (targeted 3-suite run):
   - PASS: `test_photowheel_centering_playwright.py`
   - PASS: `test_photowheel_visual_invariants_playwright.py`
   - PASS: `test_photowheel_thumbnail_behavior_playwright.py`
