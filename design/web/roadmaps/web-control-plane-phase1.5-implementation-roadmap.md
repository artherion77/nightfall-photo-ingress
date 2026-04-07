# Web Control Plane — Phase 1.5 Implementation Roadmap

Status: In Progress — Chunks P1.5-0 and P1.5-1 complete; P1.5-2 not started
Date: 2026-04-07
Owner: Systems Engineering
Depends on: Phase 1 complete (all Chunks 0-6 implemented and validated)
Blocks: Phase 2 Chunk P2-2 and beyond

Authoritative Phase 1.5 design:
- `design/web/web-control-plane-architecture-phase1.5.md`

Phase 1 completion record:
- `design/web/roadmaps/web-control-plane-phase1-implementation-roadmap.md`

Phase 2 roadmap (dependency update required after Phase 1.5 sign-off):
- `design/web/roadmaps/web-control-plane-phase2-implementation-roadmap.md`

---

## 1. Phase 1.5 Goal Summary

Phase 1.5 closes three operator-facing gaps left by Phase 1: (a) no image rendering
in the PhotoWheel, (b) no continuous scroll/touch/momentum navigation, and (c) no
thumbnail pipeline. These are delivered as a cohesive unit because the thumbnail API
surface, the PhotoCard image element, the interaction model, and the preloading
strategy are interdependent.

Phase 1.5 is a hard gate for Phase 2 Chunk P2-2 (Filter Sidebar) and all subsequent
Phase 2 chunks except P2-1 (already complete).

### Phase 1.5 scope at a glance

| Area | Deliverable |
|------|-------------|
| Token System Consolidation | Declare canonical token file; define migration contract |
| Thumbnail Backend Integration Contract | API route, error semantics, caching guarantees, purge hooks |
| Thumbnail Backend Implementation | Generation, storage, cache, and HTTP serving |
| PhotoCard Image Rendering | Replace placeholder with `<img>` backed by thumbnail API; skeleton/loaded/error states |
| PhotoWheel Scroll + Touch Model | Scroll-wheel, trackpad, touch-swipe, fling detection |
| PhotoWheel Momentum + State Machine | rAF momentum decay, cancel-on-input, ActiveIndex state machine |
| DOM Windowing + Preloading | RENDER_RADIUS viewport culling; PRELOAD_RADIUS prefetch |
| Regression + Quality Gate | Zero Phase 1 regressions; new interaction + image tests |

### Explicit exclusions

- Dashboard page changes (Phase 2).
- Filter Sidebar (Phase 2 P2-2).
- KPI Threshold editing (Phase 2 P2-4).
- Audit Timeline infinite scroll (Phase 2 P2-3).
- Video thumbnail generation (future phase).
- SSR, Postgres, OIDC, CDN (Phase 2 optional).

---

## 2. Chunk Dependency Graph

```
P1.5-0: Token System Declaration
   │
   └──► P1.5-1: Thumbnail Backend Integration Contract  (document-only; no code)
           │
           ├──► P1.5-2: Thumbnail Backend Implementation  (backend code)
           │       │
           │       └──► P1.5-4: PhotoCard Image Rendering  (frontend; depends on live thumbnail API)
           │               │
           │               └──► P1.5-6: DOM Windowing + Preloading  (frontend; depends on image rendering)
           │                       │
           │                       └──► P1.5-7: Regression + Quality Gate  (validation pass)
           │
           └──► P1.5-3: PhotoWheel Scroll + Touch Handlers  (frontend; no thumbnail dependency)
                   │
                   └──► P1.5-5: Momentum Engine + ActiveIndex State Machine  (frontend; depends on input handlers)
                           │
                           └──► P1.5-6  (merge; windowing integrates with momentum-driven navigation)
```

**Parallel tracks:**
- P1.5-2 (thumbnail backend) and P1.5-3 (scroll/touch handlers) are independent and
  may execute in parallel after P1.5-1 is signed off.
- P1.5-4 and P1.5-5 may execute in parallel on their respective tracks.
- P1.5-6 merges both tracks; it cannot start until P1.5-4 and P1.5-5 are both complete.
- P1.5-7 is the final gate.

**Recommended sequence:** P1.5-0 → P1.5-1 → (P1.5-2 ∥ P1.5-3) → (P1.5-4 ∥ P1.5-5) → P1.5-6 → P1.5-7.

---

## 3. Chunk P1.5-0 — Token System Declaration

Status: Implemented (2026-04-07)

### Purpose

Declare which of the two existing token files is the canonical design token source for
the web control plane.  Define the primitive→semantic layering contract.  Establish the
migration expectation for references to the non-canonical file.  This chunk is a design
decision and documentation update only — no code changes.

### Dependencies

- Phase 1 complete (Chunk 2 delivered the original `webui/src/styles/tokens.css`).

### Deliverables

1. Amend `design/web/web-control-plane-architecture-phase1.5.md` (or a companion
   design-tokens update document) with:
   - Declaration of `webui/src/lib/tokens/tokens.css` as the canonical token source.
   - Definition of primitive tokens (palette, scale) vs. semantic tokens
     (component-level aliases) and their intended consumption boundaries.
   - Migration path: all Phase 1 component references to `webui/src/styles/tokens.css`
     must be re-pointed to the canonical file during chunk execution. The legacy file
     is retained as a read-only compatibility shim until all references are migrated,
     then deleted.
   - Explicit statement: PhotoWheel motion tokens (`--duration-slow`,
     `--easing-default`, `--wheel-blur-center`, `--wheel-blur-near`,
     `--wheel-blur-far`, and any new momentum/animation tokens) are defined in the
     canonical token file and must not be duplicated elsewhere.
2. List of tokens that Phase 1.5 chunks depend on (consumed from the canonical file):
   - `--duration-slow`
   - `--easing-default`
   - `--wheel-blur-center`, `--wheel-blur-near`, `--wheel-blur-far`
   - `--color-bg-700` or equivalent skeleton-pulse background
   - `--color-content-300` or equivalent placeholder-icon fill
   - Any new motion token introduced by P1.5-5 (momentum friction, step timing)

### Acceptance Criteria

- [x] A single canonical token file is named in the design documentation.
- [x] Primitive vs. semantic layering is defined with consumption boundaries.
- [x] Migration path from the non-canonical file is documented with completion criteria.
- [x] PhotoWheel motion tokens are explicitly scoped to the canonical file.
- [x] No code changes are included in this chunk.

### Stop-Gate

Cannot proceed to P1.5-1 unless the canonical token file is declared and the
primitive→semantic layering contract is written down.  All subsequent chunks
reference this declaration for token sourcing.

---

### Chunk P1.5-0 complete (2026-04-07) — token declaration, layering contract,
migration expectation, and motion-token source-of-truth documented.

---

## 4. Chunk P1.5-1 — Thumbnail Backend Integration Contract

Status: Implemented (2026-04-07)

### Purpose

Define the integration contract that the frontend (P1.5-4, P1.5-6) and the backend
(P1.5-2) both code against.  This chunk produces a specification document only — no
backend or frontend code.  The contract freezes the API shape, error semantics, caching
guarantees, and performance budget so that backend and frontend tracks can proceed in
parallel with no ambiguity.

### Dependencies

- P1.5-0 (token system declaration signed off).

### Deliverables

1. Integration contract document (section in Phase 1.5 design or standalone spec)
   defining the following:

   **API surface:**
   - `GET /api/v1/thumbnails/{sha256}` — route, path parameter, auth requirement.
   - Success: 200, `Content-Type: image/webp`, `Cache-Control: private, max-age=86400, immutable`, `ETag: "thumb-{sha256}"`.
   - Errors: 404 (not found, not pending, not decodable, physical file missing); 500 (generation or I/O failure).

   **Error-handling contract (frontend expectations):**
   - 404 triggers file-type icon fallback in PhotoCard; no retry.
   - 500 triggers broken-image icon fallback; eligible for `apiFetch` retry (P2-1 retry policy applies).
   - Network failure (status 0): retry per P2-1 policy; show skeleton until resolved or retries exhausted.

   **Preload strategy contract:**
   - Frontend uses `new Image()` with thumbnail URL for prefetch.
   - Backend must tolerate concurrent requests for the same SHA-256 without corruption (atomic write guarantee).
   - Backend must tolerate abandoned connections (browser GC of Image object) without resource leaks.

   **Loading-state transitions (frontend contract):**

   | State | Trigger | Visual |
   |-------|---------|--------|
   | Skeleton | `<img>` element mounted, src set, load not yet fired | Pulsing rectangle (`--duration-slow`) |
   | Loaded | `<img>` `onload` fires | Full thumbnail, `object-fit: cover` |
   | Error (non-image) | `<img>` `onerror` fires, HTTP 404 | File-type icon (image/video/document by extension) |
   | Error (generation failed) | `<img>` `onerror` fires, HTTP 500 after retries | Broken-image icon |

   **Backend guarantees:**
   - Generation latency (JPEG 12MP → 480px WebP): < 200ms.
   - Cache-hit serving latency: < 5ms.
   - Thumbnail file size, typical: 15–40 KB.
   - Atomic write: temp file + `os.rename()`.
   - Zero-byte marker convention for non-decodable sources.
   - Cache purge on accept/reject (best-effort hook); periodic GC via `metricsctl thumbnail-gc`.

   **No registry schema changes.** Thumbnail state lives on the filesystem only.

### Acceptance Criteria

- [x] Integration contract document exists and covers all items listed above.
- [x] API route, status codes, headers, and content type are specified without ambiguity.
- [x] Frontend loading-state transition table is specified.
- [x] Backend latency budget and atomic-write guarantee are stated.
- [x] Preload concurrency and abandoned-connection tolerance are stated.
- [x] No code changes are included in this chunk.

### Stop-Gate

Cannot proceed to P1.5-2 (backend implementation) or P1.5-4 (frontend image
rendering) unless the integration contract is signed off.  Both tracks code against
this contract.

---

### Chunk P1.5-1 complete (2026-04-07) — integration contract designated and
signed off in architecture documentation.

---

## 5. Chunk P1.5-2 — Thumbnail Backend Implementation

Status: Not Started

### Purpose

Implement the thumbnail generation, caching, purge, and HTTP-serving backend as
defined by the P1.5-1 integration contract.  This chunk adds a single new API endpoint
and a filesystem-only cache subsystem.  No existing endpoints are modified.

### Dependencies

- P1.5-1 (integration contract signed off).
- Phase 1 Chunk 1 patterns (auth dependency, router registration, service-layer structure).

### Deliverables

**Backend files (new):**
```
api/routers/thumbnails.py       — GET /api/v1/thumbnails/{sha256}; verify_api_token dependency
api/services/thumbnail_service.py — generate(), get_or_generate(), purge_cache_entry()
```

**Backend files (extended):**
```
api/app.py                      — Register thumbnails router
api/dependencies.py             — Expose thumbnail_cache_path from config
src/nightfall_photo_ingress/config.py — Add thumbnail_cache_path to CoreConfig
                                        (default: <data_root>/cache/thumbnails)
```

**Purge hooks (extended):**
```
api/services/triage_service.py  — Post-commit hook: call thumbnail purge on accept/reject
```

**CLI (extended):**
```
metricsctl                      — Add thumbnail-gc subcommand (scan cache, remove entries
                                  whose SHA-256 is not pending in registry)
```

**Tests (new):**
```
tests/integration/api/test_thumbnails.py
  — 200 for pending JPEG/PNG/WebP source
  — cache hit on second request (no re-generation; assert via mtime or mock)
  — 404 for non-existent SHA-256
  — 404 for non-pending item
  — 404 for non-image file; zero-byte marker created
  — 404 on subsequent request for marked non-image (no decode attempt)
  — atomic write (concurrent request does not serve partial file)
  — auth required (missing token → 401)
  — EXIF orientation applied (test with rotated JPEG fixture)
  — accept/reject triggers cache purge
```

### Acceptance Criteria

- [ ] `GET /api/v1/thumbnails/{sha256}` returns 200 with `image/webp` for a pending
      JPEG, PNG, or WebP source.
- [ ] Repeated requests are served from disk cache without re-generation.
- [ ] 404 for non-existent SHA-256, non-pending status, or non-decodable source.
- [ ] Zero-byte marker prevents repeated decode attempts for non-image files.
- [ ] Thumbnails are written atomically (temp file + rename).
- [ ] EXIF orientation is applied; all metadata is stripped.
- [ ] `Cache-Control: private, max-age=86400, immutable` and `ETag` headers are set.
- [ ] Authentication required (same `verify_api_token` as other endpoints).
- [ ] Accept/reject transitions trigger best-effort cache-entry removal.
- [ ] `metricsctl thumbnail-gc` removes orphaned cache entries.
- [ ] All new `test_thumbnails.py` tests pass.
- [ ] All existing Phase 1 integration tests pass (zero regressions).

### Stop-Gate

Cannot proceed to P1.5-4 (PhotoCard image rendering) unless this chunk is complete
and `GET /api/v1/thumbnails/{sha256}` returns correct responses for test fixtures.

---

### ⛔ STOP — P1.5-2 complete. Return control to user for review before continuing.

---

## 6. Chunk P1.5-3 — PhotoWheel Scroll + Touch Handlers

Status: Not Started

### Purpose

Add scroll-wheel and touch-swipe input handling to the PhotoWheel component.  This
chunk wires raw browser events to discrete `activeIndex` changes.  It does not add
momentum, DOM windowing, or image rendering — those are subsequent chunks.

### Dependencies

- P1.5-1 (integration contract signed off; interaction design constants finalized).
- Phase 1 Chunk 4 (PhotoWheel keyboard navigation and `activeIndex` state exist).

### Deliverables

**Frontend files (extended):**
```
webui/src/lib/components/staging/PhotoWheel.svelte
  — wheel event listener on .wheel container
  — Discrete-scroll classification (DOM_DELTA_LINE or large deltaY): one step per detent
  — Continuous-scroll classification (small deltaY): accumulated delta with 60px threshold
  — Scroll-lock: event.preventDefault() when PhotoWheel has pointer focus
  — Scroll-lock release: at queue boundaries when scroll direction is beyond bounds
  — touchstart / touchmove / touchend handlers
  — Swipe dead zone: 10px horizontal displacement before entering swipe-tracking mode
  — Swipe commit threshold: 40px displacement or 0.3px/ms release velocity
  — Vertical scroll suppressed during active horizontal swipe tracking
```

**Design constants consumed from canonical token file (P1.5-0):**
- `--duration-slow` (CSS transition on `.slot` during step)
- `--easing-default` (CSS transition easing)

**Tests (new):**
```
tests/integration/ui/test_photowheel_scroll.py
  — Discrete wheel event advances activeIndex by 1
  — Continuous small-delta events accumulate; crossing threshold advances by 1
  — Scroll-lock: page does not scroll while PhotoWheel is focused
  — Scroll-lock disengages at first/last item boundary
  — Touch swipe exceeding threshold advances activeIndex
  — Touch swipe below dead zone does not change activeIndex
  — Existing keyboard shortcuts (Arrow, A, R, D) remain functional
```

Note: scroll/touch input simulation requires a browser-level driver (Playwright or
equivalent).  If Playwright is not available at execution time, the test strategy falls
back to structured code review with manual verification checklist, consistent with the
Phase 1 test strategy for client-side interaction logic.

### Acceptance Criteria

- [ ] Mouse scroll wheel navigates the PhotoWheel (one step per detent).
- [ ] Trackpad two-finger swipe navigates with accumulated delta threshold (60px).
- [ ] Touch swipe navigates with 40px commit threshold.
- [ ] Touch swipe below 10px dead zone does not trigger navigation.
- [ ] Scroll-lock prevents page scroll while PhotoWheel is focused.
- [ ] Scroll-lock disengages at queue boundaries (first/last item).
- [ ] All existing keyboard shortcuts continue to function.
- [ ] All existing Phase 1 integration tests pass (zero regressions).

### Stop-Gate

Cannot proceed to P1.5-5 (momentum engine) unless discrete scroll and touch input
handlers are wired and confirmed to produce correct `activeIndex` changes.

---

### ⛔ STOP — P1.5-3 complete. Return control to user for review before continuing.

---

## 7. Chunk P1.5-4 — PhotoCard Image Rendering

Status: Not Started

### Purpose

Replace the PhotoCard text placeholder with a real `<img>` element backed by the
thumbnail API.  Implement skeleton→loaded→error visual state transitions as defined
in the P1.5-1 integration contract.

### Dependencies

- P1.5-2 (thumbnail backend live and returning correct responses).
- P1.5-1 (integration contract: loading-state transition table).
- P1.5-0 (canonical token file: skeleton-pulse and placeholder-icon tokens).

### Deliverables

**Frontend files (extended):**
```
webui/src/lib/components/staging/PhotoCard.svelte
  — Replace <div class="thumb">IMG</div> with:
    <div class="thumb">
      <img src="/api/v1/thumbnails/{item.sha256}"
           alt={item.filename}
           loading="lazy"
           decoding="async"
           onerror={handleImageError} />
    </div>
  — Skeleton state: pulsing rectangle while image loads (CSS animation on .thumb background)
  — Loaded state: full thumbnail, object-fit: cover
  — Error state (non-image): file-type icon (image/video/document by extension)
  — Error state (generation failure): broken-image icon
  — .thumb container: aspect-ratio: 4/3; min-width: 220px preserved
  — No layout shift across loading/loaded/error states (fixed dimensions)
```

**Tests (new):**
```
tests/integration/ui/test_photocard_image.py
  — PhotoCard img src points to /api/v1/thumbnails/{sha256}
  — Successful thumbnail load renders visible image
  — 404 response triggers file-type icon fallback
  — Card dimensions remain stable across all three states (no layout shift)
  — loading="lazy" and decoding="async" attributes present
```

### Acceptance Criteria

- [ ] PhotoCard renders a real `<img>` element with `src` pointing to the thumbnail API.
- [ ] Skeleton (pulsing rectangle) is visible while the image is loading.
- [ ] Loaded state shows the full thumbnail with `object-fit: cover`.
- [ ] Non-image files (404) show an appropriate file-type icon fallback.
- [ ] Generation failure (500 after retries) shows a broken-image icon.
- [ ] Card dimensions are stable across skeleton, loaded, and error states (zero layout shift).
- [ ] `loading="lazy"` and `decoding="async"` attributes are present on the `<img>`.
- [ ] All new `test_photocard_image.py` tests pass.
- [ ] All existing Phase 1 integration tests pass (zero regressions).

### Stop-Gate

Cannot proceed to P1.5-6 (DOM windowing + preloading) unless PhotoCard correctly
renders thumbnails in all three states (skeleton, loaded, error) and the layout is
shift-free.

---

### ⛔ STOP — P1.5-4 complete. Return control to user for review before continuing.

---

## 8. Chunk P1.5-5 — Momentum Engine + ActiveIndex State Machine

Status: Not Started

### Purpose

Add momentum physics (rAF velocity decay) and formalize the ActiveIndex state machine.
This chunk builds on the scroll/touch handlers from P1.5-3 and introduces the
IDLE → TRACKING → MOMENTUM → IDLE lifecycle with cancel-on-input semantics.

### Dependencies

- P1.5-3 (scroll and touch handlers wired and producing discrete activeIndex changes).

### Deliverables

**Frontend files (extended):**
```
webui/src/lib/components/staging/PhotoWheel.svelte
  — ActiveIndex state machine: IDLE, STEP, TRACKING, TRANSITIONING, MOMENTUM
  — TRACKING → MOMENTUM transition when release velocity exceeds fling threshold (0.3px/ms for touch;
    continuous trackpad release with residual accumulated velocity)
  — Momentum loop: requestAnimationFrame decay with friction 0.92/frame @60fps
  — Momentum step: each time decaying displacement crosses step threshold, advance activeIndex by 1
  — Momentum termination: velocity < 0.05px/ms or activeIndex at queue boundary
  — Cancel-on-input: any key, click, wheel, or touch event during TRANSITIONING or MOMENTUM
    immediately cancels current motion; re-enter STEP or TRACKING from current activeIndex
  — CSS transitions during momentum steps use canonical tokens (--duration-slow, --easing-default)
```

**Design constants (from Phase 1.5 architecture §9):**
- Momentum friction coefficient: 0.92 per frame @60fps
- Momentum minimum velocity: 0.05px/ms
- Touch fling velocity threshold: 0.3px/ms

**Tests (new):**
```
tests/integration/ui/test_photowheel_momentum.py
  — High-velocity touch fling triggers momentum; multiple items are traversed
  — Momentum terminates when velocity decays below threshold
  — Momentum terminates at queue boundary (first or last item)
  — New input during momentum cancels motion immediately
  — State machine returns to IDLE after momentum terminates
  — Keyboard input during MOMENTUM cancels and enters STEP
```

Note: momentum testing requires a browser-level driver for rAF simulation.  Same
Playwright fallback strategy as P1.5-3.

### Acceptance Criteria

- [ ] High-velocity touch fling produces momentum traversal of multiple items.
- [ ] Momentum decays per rAF loop with friction coefficient 0.92/frame.
- [ ] Momentum terminates at velocity < 0.05px/ms.
- [ ] Momentum terminates at queue boundaries (first/last item).
- [ ] Any new input during TRANSITIONING or MOMENTUM cancels motion immediately.
- [ ] ActiveIndex state machine transitions are correct for all input channels.
- [ ] CSS transitions during momentum steps use canonical tokens.
- [ ] All existing Phase 1 integration tests pass (zero regressions).

### Stop-Gate

Cannot proceed to P1.5-6 (DOM windowing + preloading) unless momentum engine is
functional and cancel-on-input semantics are verified.

---

### ⛔ STOP — P1.5-5 complete. Return control to user for review before continuing.

---

## 9. Chunk P1.5-6 — DOM Windowing + Preloading

Status: Not Started

### Purpose

Introduce DOM windowing (RENDER_RADIUS) to limit rendered PhotoCard elements and
thumbnail preloading (PRELOAD_RADIUS) to eliminate visible loading during navigation.
This chunk merges the image-rendering track (P1.5-4) and the momentum track (P1.5-5)
into a unified interaction model.

### Dependencies

- P1.5-4 (PhotoCard image rendering complete — `<img>` elements exist to preload).
- P1.5-5 (momentum engine complete — navigation can traverse many items rapidly,
  requiring efficient DOM management).

### Deliverables

**Frontend files (extended):**
```
webui/src/lib/components/staging/PhotoWheel.svelte
  — RENDER_RADIUS = 5: only items at activeIndex ± 5 are rendered as PhotoCard elements
    (11 DOM nodes maximum)
  — Items outside RENDER_RADIUS: spacer elements of correct width to maintain flex layout
  — When activeIndex changes: entering items mount, exiting items unmount
  — CSS transition on .slot handles entry/exit animation

  — PRELOAD_RADIUS = 3: when activeIndex settles (state machine enters IDLE),
    trigger preload for items at activeIndex ± 3
  — Preload mechanism: new Image() with thumbnail URL set on .src
  — Preload is low-priority; does not block rendering
  — Navigating before preload completes: in-flight Image() objects are abandoned
    (browser GC handles cancellation)
```

**Design constants (from Phase 1.5 architecture §9):**
- RENDER_RADIUS: 5 (design-time constant, not runtime configuration)
- PRELOAD_RADIUS: 3 (design-time constant, not runtime configuration)

**Tests (new):**
```
tests/integration/ui/test_photowheel_windowing.py
  — Queue of 50+ items: only 11 DOM nodes rendered at any time
  — Navigating from item 25 to item 26: item at index 20 unmounted, item at index 31 mounted
  — Spacer elements maintain correct total width (no layout jump)
  — Preload fires for items at activeIndex ± 3 on IDLE settle
  — Rapid navigation (momentum) does not trigger preload until IDLE
```

### Acceptance Criteria

- [ ] DOM contains at most `2 * RENDER_RADIUS + 1` PhotoCard elements at any time.
- [ ] Items outside the render window are represented by correctly-sized spacer elements.
- [ ] No layout shift or visual jump occurs when items enter or exit the render window.
- [ ] Thumbnail preloading fires for `activeIndex ± PRELOAD_RADIUS` when state is IDLE.
- [ ] Preloading does not fire during MOMENTUM or TRACKING states.
- [ ] Abandoned preload requests do not cause errors or resource leaks.
- [ ] All interaction channels (keyboard, scroll, touch, momentum) function correctly
      with windowed rendering.
- [ ] All new `test_photowheel_windowing.py` tests pass.
- [ ] All existing Phase 1 integration tests pass (zero regressions).

### Stop-Gate

Cannot proceed to P1.5-7 (quality gate) unless DOM windowing and preloading are
verified across all interaction channels and queue sizes.

---

### ⛔ STOP — P1.5-6 complete. Return control to user for review before continuing.

---

## 10. Chunk P1.5-7 — Regression + Quality Gate

Status: Not Started

### Purpose

Full regression pass and quality verification.  No new functionality is added.  This
chunk validates that all Phase 1.5 deliverables meet their acceptance criteria and
that all Phase 1 behavior is preserved without modification.

### Dependencies

- All prior Phase 1.5 chunks (P1.5-0 through P1.5-6) complete.

### Deliverables

1. Full integration suite execution: all Phase 1 tests + all Phase 1.5 tests.
2. Manual verification checklist for interaction channels not coverable by pytest:
   - Scroll-wheel navigation (discrete + continuous)
   - Touch-swipe navigation
   - Momentum traversal and cancel-on-input
   - Skeleton → loaded → error state transitions in PhotoCard
   - DOM windowing with large queue (50+ items)
   - Preload behavior (network tab inspection)
3. API surface audit: confirm only `GET /api/v1/thumbnails/{sha256}` was added;
   no existing endpoints were modified.
4. Token migration audit: confirm all component `<style>` blocks reference only the
   canonical token file; the non-canonical file contains no references that are not
   also in the canonical file.
5. Documentation update:
   - This roadmap: update chunk statuses to "Implemented".
   - Phase 2 roadmap: add Phase 1.5 as dependency gate for P2-2 through P2-7.
   - Roadmaps README: add this roadmap to the index.

### Acceptance Criteria

- [ ] All Phase 1 integration tests pass without modification.
- [ ] All Phase 1.5 integration tests pass.
- [ ] Triage mutations (accept/reject/defer with idempotency keys) are unaffected.
- [ ] Audit trail entries are unaffected.
- [ ] Health endpoint and polling are unaffected.
- [ ] No existing API endpoint responses have changed shape or status codes.
- [ ] Only one new API endpoint exists: `GET /api/v1/thumbnails/{sha256}`.
- [ ] All PhotoWheel interaction channels produce correct activeIndex changes.
- [ ] PhotoCard renders correctly in skeleton, loaded, and error states.
- [ ] DOM windowing limits rendered nodes to `2 * RENDER_RADIUS + 1`.
- [ ] Thumbnail preloading fires on IDLE settle within PRELOAD_RADIUS.
- [ ] Canonical token file is the sole token source for all components.
- [ ] Phase 2 roadmap dependency annotation is updated.

### Stop-Gate

Phase 1.5 is declared complete only when all acceptance criteria above are met.
Phase 2 Chunks P2-2 through P2-7 cannot proceed until this gate is passed.

---

### Phase 1.5 complete — proceed to Phase 2 execution.

---

## 11. Phase 1.5 Gating Criteria for Phase 2 Eligibility

Phase 2 Chunk P2-2 (Filter Sidebar) and all subsequent Phase 2 chunks are blocked
until every item below is satisfied:

1. `GET /api/v1/thumbnails/{sha256}` is live, authenticated, and returning correct
   WebP responses for pending image files.
2. PhotoCard renders real thumbnail images with skeleton→loaded→error state transitions.
3. PhotoWheel supports scroll-wheel, trackpad-swipe, touch-swipe, and momentum
   navigation across all tested interaction channels.
4. DOM windowing limits rendered items to `activeIndex ± RENDER_RADIUS`.
5. Thumbnail preloading fires within `PRELOAD_RADIUS` on IDLE settle.
6. Canonical token file is declared and all components reference it exclusively.
7. All Phase 1 integration tests pass without modification (zero regressions).
8. All Phase 1.5 integration tests pass.
9. Phase 2 roadmap dependency annotation updated to reflect Phase 1.5 gate.
10. This roadmap's chunk statuses are all marked "Implemented".

Phase 2 Chunk P2-1 (API Client Retry/Backoff) is already complete and is unaffected
by this gate.  The thumbnail endpoint benefits from P2-1 retry logic automatically
(GET requests to `/api/v1/thumbnails/` retry on 503/429 per existing policy).

---

## 12. Design Constants Reference

All design-time constants consumed or introduced by Phase 1.5 chunks, collected for
implementation reference.  Authoritative source: `design/web/web-control-plane-
architecture-phase1.5.md` §9.

| Constant | Value | Consuming Chunk |
|----------|-------|-----------------|
| Scroll-wheel detent threshold | 1 step per detent | P1.5-3 |
| Trackpad accumulated delta threshold | 60px | P1.5-3 |
| Touch swipe dead zone | 10px | P1.5-3 |
| Touch swipe commit threshold | 40px | P1.5-3 |
| Touch fling velocity threshold | 0.3px/ms | P1.5-3, P1.5-5 |
| Momentum friction coefficient | 0.92 per frame @60fps | P1.5-5 |
| Momentum minimum velocity | 0.05px/ms | P1.5-5 |
| RENDER_RADIUS | 5 (11 DOM nodes) | P1.5-6 |
| PRELOAD_RADIUS | 3 | P1.5-6 |
| Thumbnail max dimension | 480px longest edge | P1.5-2 |
| Thumbnail format | WebP lossy, quality 80 | P1.5-2 |
| Thumbnail cache prefix depth | 2 levels (2-char / 4-char) | P1.5-2 |
| Cache-Control header | private, max-age=86400, immutable | P1.5-2 |
| Generation latency budget | < 200ms | P1.5-2 |
| Cache-hit latency budget | < 5ms | P1.5-2 |
| PhotoCard aspect ratio | 4:3 | P1.5-4 |
| PhotoCard min-width | 220px | P1.5-4 |

---

## 13. Drift Log

### 13.1 Initial roadmap creation (2026-04-07)

- Generated from `design/web/web-control-plane-architecture-phase1.5.md` (659 lines, Draft status).
- Chunked into 8 implementation units (P1.5-0 through P1.5-7).
- Two parallel tracks identified: backend thumbnail (P1.5-2 → P1.5-4) and frontend
  interaction (P1.5-3 → P1.5-5), merging at P1.5-6.
- Token system consolidation scoped as a document-only prerequisite chunk (P1.5-0).
- Thumbnail backend integration contract scoped as a document-only gate (P1.5-1)
  enabling parallel execution of backend and frontend tracks.

### 13.2 Chunk P1.5-0 sign-off (2026-04-07)

- Updated `design/web/web-control-plane-architecture-phase1.5.md` with canonical
  token declaration naming `webui/src/lib/tokens/tokens.css` as authoritative.
- Added primitive→semantic layering contract and migration contract for
  `webui/src/styles/tokens.css` compatibility-shim retirement.
- Added explicit PhotoWheel motion-token source-of-truth statement and Phase 1.5
  token dependency list.
- Marked chunk P1.5-0 as implemented and acceptance criteria complete.

### 13.3 Chunk P1.5-1 sign-off (2026-04-07)

- Designated `design/web/web-control-plane-architecture-phase1.5.md` section 5 as the
  authoritative thumbnail integration contract for chunks P1.5-2, P1.5-4, and P1.5-6.
- Confirmed the contract includes required API surface, error semantics, preload
  contract, loading-state transitions, backend guarantees, and no-schema-change
  constraint.
- Marked chunk P1.5-1 as implemented and acceptance criteria complete.
