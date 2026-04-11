# Web Control Plane — Phase 1.5 Architectural Design

Status: Implemented


Date: 2026-04-07
Owner: Systems Engineering
Depends on: Phase 1 complete (all Chunks 0-6 validated)
Blocks: Phase 2 Chunk P2-2 and beyond

---

## 1. Purpose and Motivation

Phase 1 delivered the structural skeleton of the Staging Queue: keyboard navigation,
idempotent triage mutations, audit-first durability, and the PhotoWheel/TriageControls
component architecture. However, Phase 1 was scoped to wiring correctness and did not
address the visual fidelity or interaction fluency required for an operator who processes
hundreds of items per session.

The UI mock (design/ui-mocks/Astronaut photo review interface.png) establishes the
operator-grade target: a cinematic 3D carousel rendering real photo thumbnails with
perspective depth and depth-of-field blur, inline Accept/Reject controls overlaid on the
active card region, and large CTA buttons for touch or fatigue-friendly triage. The
current implementation falls short of this target in three critical dimensions:

1. **No image rendering.** PhotoCard renders a text placeholder (`<div class="thumb">IMG</div>`).
   There is no `<img>` element, no thumbnail URL, no backend image serving endpoint.

2. **No continuous navigation.** The PhotoWheel responds only to discrete keyboard events
   (ArrowLeft, ArrowRight) and click. There is no scroll-wheel, trackpad-swipe,
   touch-swipe, or momentum physics. An operator with a mouse wheel or trackpad cannot
   browse the queue fluidly.

3. **No thumbnail pipeline.** The backend has no facility to generate, store, or serve
   thumbnails. Pending files exist on disk under `pending_path` but are not exposed
   via any HTTP endpoint.

Phase 1.5 corrects these three gaps as a cohesive architectural unit. The work is
sequenced before Phase 2 because (a) the PhotoWheel interaction model influences the
Filter Sidebar and audit integration planned for Phase 2, and (b) thumbnail serving
introduces a new API surface that must be established before the API versioning policy
of Phase 2 Chunk P2-5 is finalized.

### What Phase 1.5 is not

- Phase 1.5 does not redesign the Phase 1 component architecture (the PhotoWheel,
  PhotoCard, TriageControls, ItemMetaPanel composition is preserved).
- Phase 1.5 does not introduce breaking changes to existing API endpoints.
- Phase 1.5 does not address Dashboard features (KPI wiring, Filter Sidebar, Audit
  infinite scroll) — those remain Phase 2 scope.

---

## 2. Revised Phase Structure

### Before (two phases)

```
Phase 1  →  Phase 2 (mandatory)  →  Phase 2 (optional)  →  LAN exposure
```

### After (three phases)

```
Phase 1  →  Phase 1.5  →  Phase 2 (mandatory)  →  Phase 2 (optional)  →  LAN exposure
```

Phase 1.5 is a hard gate for Phase 2 Chunk P2-2 (Filter Sidebar) and beyond. Phase 2
Chunk P2-1 (API Client Retry/Backoff) is already complete and is unaffected. The
existing Phase 2 roadmap (design/web/roadmaps/web-control-plane-phase2-implementation-
roadmap.md) requires a dependency annotation update but no structural rework.

### Phase 1.5 scope summary

| Area | Deliverable |
|------|-------------|
| Thumbnail Backend | Generation, storage, cache, purge, and HTTP serving of thumbnails |
| PhotoCard Image Rendering | Replace placeholder with `<img>` tag backed by thumbnail API |
| PhotoWheel Interaction Model | Scroll-wheel, trackpad-swipe, touch-swipe, momentum physics |
| PhotoWheel Preloading | Viewport-aware thumbnail prefetch for adjacent cards |

### 2.1 Canonical token system declaration (P1.5-0)

Phase 1.5 declares one authoritative token source for the web control plane:

- Canonical token file: `webui/src/lib/tokens/tokens.css`
- Legacy compatibility file: `webui/src/styles/tokens.css`

#### Token layering contract

- Primitive tokens are raw palette/scale variables (color palette, spacing scale,
  typography scale, radius scale, shadow scale, motion constants).
- Semantic tokens are component/domain aliases that map to primitive tokens and are
  consumed by UI components.
- Component styles must consume semantic tokens where available; direct primitive-token
  use is restricted to token-definition layers and exceptional fallback cases.

#### Migration contract

- During Phase 1.5 implementation, all active component references to
  `webui/src/styles/tokens.css` must be re-pointed to
  `webui/src/lib/tokens/tokens.css`.
- `webui/src/styles/tokens.css` is retained only as a read-only compatibility shim
  until migration completion criteria are met.
- After migration completion, the compatibility shim is removed.

#### PhotoWheel motion-token source of truth

PhotoWheel motion and transition tokens are canonical-token derived and must be defined
only in `webui/src/lib/tokens/tokens.css`, including:

- `--duration-slow`
- `--easing-default`
- `--wheel-blur-center`
- `--wheel-blur-near`
- `--wheel-blur-far`
- Any new Phase 1.5 momentum/animation token

#### Phase 1.5 token dependency set

The following tokens are required by Phase 1.5 chunks and are consumed from the
canonical token file:

- `--duration-slow`
- `--easing-default`
- `--wheel-blur-center`
- `--wheel-blur-near`
- `--wheel-blur-far`
- `--color-bg-700` (or equivalent skeleton pulse background token)
- `--color-content-300` (or equivalent placeholder icon token)
- Any new motion token introduced by the momentum chunk

### Gating criteria

Phase 1.5 is complete when:
1. PhotoCard renders a real thumbnail image for every pending item.
2. Scroll-wheel and touch-swipe navigate the PhotoWheel with momentum decay.
3. Thumbnail generation runs without blocking the ingest pipeline.
4. All existing Phase 1 integration tests continue to pass (zero regressions).

---

## 3. Operator-Flow and Interaction Model Design

### 3.1 Operator workflow

The Staging Queue is the operator's primary triage surface. A typical session:

1. Operator opens the Staging Queue page.
2. The SPA loads the first page of pending items and hydrates the PhotoWheel.
3. The operator visually scans the active card's thumbnail, filename, and metadata.
4. The operator decides: Accept (A key or green button), Reject (R key or red button),
   or Skip/Defer (D key or scroll to next).
5. The PhotoWheel advances to the next item. Repeat until the queue is empty or the
   operator stops.

Operator speed depends on two factors: (a) how quickly they can see the image to make a
decision, and (b) how quickly they can navigate between items. Phase 1 addressed (b)
partially via keyboard shortcuts but not via the natural mouse/trackpad interaction that
operators actually use. Phase 1 did not address (a) at all.

### 3.2 Interaction channels

Phase 1.5 targets four interaction channels for PhotoWheel navigation:

| Channel | Input | Behavior |
|---------|-------|----------|
| Keyboard | ArrowLeft / ArrowRight | Discrete step (already implemented in Phase 1) |
| Keyboard | A / R / D | Triage action (already implemented in Phase 1) |
| Scroll wheel | wheel event (deltaY) | Discrete step per detent; debounced to prevent overshoot |
| Trackpad swipe | wheel event (continuous deltaY) | Accumulated delta with threshold; momentum decay after release |
| Touch swipe | touchstart/touchmove/touchend | Velocity-tracked swipe; fling threshold triggers momentum |

All channels converge on the same state transition: `activeIndex` advances or retreats
by one or more positions. The PhotoWheel is the sole owner of navigation state via the
`onSelect` callback to the parent page's `stagingQueue.setActiveIndex()`.

### 3.3 Control placement (mock fidelity)

The UI mock places two classes of triage controls:

1. **Inline controls**: Compact Accept/Reject buttons positioned to the right of the
   active card, vertically centered. These are for fast keyboard-and-mouse operators
   who triage without moving their hand to the large CTA area.

2. **CTA controls**: Two large full-width buttons below the PhotoWheel. Accept (teal
   border, hand icon) on the left, Reject (red border, hand icon) on the right. These
   are for touch-first or fatigue-conscious triage.

The Phase 1 implementation already has both control placements wired (inline via
absolute positioning in `.wheel-inline-controls`, CTA below the wheel). Phase 1.5 does
not change the control placement — only the visual quality of the content inside the
PhotoWheel.

---

## 4. PhotoWheel Interaction Model

### 4.1 Current state (Phase 1)

The PhotoWheel renders all items in a flex row with CSS `translateZ`, `scale`, and
`filter: blur()` transforms driven by distance from `activeIndex`. Navigation is
keyboard-only (ArrowLeft/ArrowRight) or click-to-select. All items are rendered in the
DOM simultaneously regardless of queue size.

### 4.2 Target state (Phase 1.5)

#### 4.2.1 Scroll-wheel navigation

The PhotoWheel listens for `wheel` events on the `.wheel` container element. Each wheel
event is classified:

- **Discrete (high-resolution scroll):** `event.deltaMode === WheelEvent.DOM_DELTA_LINE`
  or a single large `deltaY` step typical of a mouse wheel detent. Each detent advances
  `activeIndex` by 1 in the direction of scroll.

- **Continuous (trackpad gesture):** Small, frequent `deltaY` values. The component
  accumulates delta into a running total. When the accumulated delta crosses a
  configurable threshold (design target: 60px equivalent), `activeIndex` advances by 1
  and the accumulator resets.

A scroll-lock mechanism prevents the page from scrolling while the PhotoWheel has pointer
focus. Implementation: `event.preventDefault()` on the wheel handler when the event
target is within the `.wheel` container. The scroll lock disengages when the active card
is at either end of the queue (first or last item) and the scroll direction would go
beyond bounds, allowing natural page scroll to resume.

#### 4.2.2 Touch-swipe navigation

Touch handling follows a three-phase model:

1. **touchstart**: Record the starting X/Y coordinates and timestamp.
2. **touchmove**: Track the current X position; compute instantaneous velocity. If the
   horizontal displacement exceeds a dead zone (design target: 10px), suppress vertical
   scroll via `event.preventDefault()` and enter swipe-tracking mode.
3. **touchend**: If the accumulated horizontal displacement exceeds the swipe threshold
   (design target: 40px) or the release velocity exceeds the fling threshold (design
   target: 0.3px/ms), trigger an `activeIndex` change. Otherwise, snap back.

The swipe axis is horizontal to match the PhotoWheel's horizontal card layout.

#### 4.2.3 Momentum and easing

When the operator releases a trackpad-swipe or touch-fling with high velocity, the
PhotoWheel enters a momentum phase:

- The velocity at release is captured.
- A `requestAnimationFrame` loop decays the velocity by a friction coefficient per
  frame (design target: 0.92 per frame at 60fps).
- Each time the decaying accumulated displacement crosses the step threshold, the
  PhotoWheel advances one position.
- The loop terminates when velocity drops below a minimum threshold (design target:
  0.05px/ms) or `activeIndex` reaches a queue boundary.
- Any new user input (key, click, wheel, touch) immediately cancels momentum.

The visual transition between positions uses the existing CSS transition tokens:
`var(--duration-slow)` with `var(--easing-default)`. Momentum-driven steps use the same
transition, creating a smooth deceleration feel.

#### 4.2.4 ActiveIndex state machine

```
                  ┌─────────────────────────────────┐
                  │         IDLE                     │
                  │  (activeIndex stable, no input)  │
                  └──────┬──────────────────┬────────┘
                         │                  │
              keyboard/click            wheel/touch
                 arrow/select            gesture start
                         │                  │
                         ▼                  ▼
                ┌──────────────┐   ┌────────────────┐
                │  STEP        │   │  TRACKING       │
                │  (immediate) │   │  (accumulating) │
                └──────┬───────┘   └──────┬──────────┘
                       │                  │
                       │          threshold crossed
                       │          or fling detected
                       │                  │
                       ▼                  ▼
                ┌──────────────┐   ┌────────────────┐
                │  TRANSITIONING│  │  MOMENTUM       │
                │  (CSS anim)  │   │  (rAF decay)   │
                └──────┬───────┘   └──────┬──────────┘
                       │                  │
                    anim end         velocity < min
                       │              or boundary
                       │                  │
                       └──────┬───────────┘
                              ▼
                       ┌─────────────┐
                       │    IDLE     │
                       └─────────────┘
```

Any user input received during TRANSITIONING or MOMENTUM immediately cancels the
current motion and re-enters STEP or TRACKING from the current `activeIndex`.

#### 4.2.5 DOM windowing

Phase 1 renders all items in the DOM. For queues exceeding approximately 50 items, this
creates unnecessary layout cost. Phase 1.5 introduces a render window:

- Only items within a window of `activeIndex +/- RENDER_RADIUS` are rendered in the
  DOM (design target: `RENDER_RADIUS = 5`, yielding 11 DOM nodes maximum).
- Items outside the window are represented by spacer elements of the correct width to
  maintain scroll position and flex layout.
- When `activeIndex` changes, entering items are mounted and exiting items are
  unmounted. The CSS transition on `.slot` handles entry/exit animation naturally.

The RENDER_RADIUS value is a design-time constant, not a runtime configuration item.

#### 4.2.6 Thumbnail preloading

Adjacent thumbnails are preloaded to eliminate visible loading when the operator
navigates:

- When `activeIndex` settles (IDLE state), the component triggers a preload for items
  at `activeIndex +/- PRELOAD_RADIUS` (design target: `PRELOAD_RADIUS = 3`).
- Preloading uses `new Image()` with the thumbnail URL set on `.src`. The browser cache
  handles deduplication.
- Preload requests are low priority and do not block rendering. If the operator
  navigates before a preload completes, the in-flight request is abandoned (browser
  handles cancellation via garbage collection of the Image object).

---

## 5. Thumbnail Backend Design

### 5.0 Integration contract designation (P1.5-1)

Sections 5.1 through 5.7 and the related frontend loading-state definition in section
6.4 are the authoritative Phase 1.5 thumbnail integration contract consumed by:

- Backend implementation chunk P1.5-2
- Frontend image rendering chunk P1.5-4
- Frontend preloading chunk P1.5-6

This contract is signed off for P1.5-1 with the following fixed constraints:

- API route and response contract: `GET /api/v1/thumbnails/{sha256}` with 200/404/500
  semantics and explicit content/cache headers as defined below.
- Frontend loading behavior: skeleton -> loaded -> error states as defined in section 6.4.
- Preload behavior: `new Image()`-based prefetch with tolerated concurrent requests and
  abandoned client connections.
- Backend guarantees: latency targets, atomic writes, zero-byte marker behavior, and
  cache purge expectations.
- Registry boundary: no registry schema changes for thumbnail state.

### 5.1 Design principles

1. **Independent subsystem.** Thumbnail generation and serving is a self-contained
   pipeline that does not modify the ingest path, the registry state machine, or the
   file lifecycle (pending/accepted/rejected/purged). It reads from `pending_path` and
   writes to a dedicated thumbnail cache directory.

2. **Additive API surface.** The thumbnail endpoint is a new route added alongside the
   existing `/api/v1/staging` and `/api/v1/items/{item_id}` endpoints. No existing
   endpoints are modified.

3. **Lazy generation with cache.** Thumbnails are generated on first request and cached
   on disk. Subsequent requests for the same SHA-256 are served from cache.

4. **No registry schema changes.** Thumbnail state is not stored in the registry
   database. Cache presence/absence on disk is the sole state signal. This avoids
   coupling thumbnail lifecycle to the file status state machine.

### 5.2 Thumbnail storage layout

```
<thumbnail_cache_path>/
  <sha256_prefix_2>/<sha256_prefix_4>/<sha256>.webp
```

Example for SHA-256 `e007gae...`:

```
<thumbnail_cache_path>/e0/e007/e007gae....webp
```

The two-level prefix directory structure prevents any single directory from accumulating
an excessive number of files. With a uniform SHA-256 distribution, each level-1 directory
(256 possibilities) contains at most ~16 level-2 directories, and each level-2 directory
contains individual thumbnails.

The `thumbnail_cache_path` is a new configuration field in `CoreConfig`, defaulting to
`<data_root>/cache/thumbnails`. This path is independent of the 5-zone storage layout
(staging, pending, accepted, rejected, trash).

### 5.3 Thumbnail generation

#### 5.3.1 Format and dimensions

- **Format:** WebP (lossy). WebP provides significantly better compression than JPEG at
  equivalent visual quality, reducing disk cache size and network transfer.
- **Quality:** 80 (WebP quality parameter).
- **Maximum dimension:** 480px on the longest edge, preserving aspect ratio. This is
  sufficient for the PhotoWheel card display at 220px CSS width plus 2x retina.
- **EXIF orientation:** Applied during generation. The thumbnail is stored in display
  orientation — no client-side rotation needed.
- **ICC profile:** Stripped. Thumbnails are converted to sRGB during generation.
- **Metadata stripping:** All EXIF, IPTC, and XMP metadata is stripped from the
  thumbnail. Only pixel data is retained.

#### 5.3.2 Generation strategy

Thumbnail generation is **synchronous on first request** (lazy). When the thumbnail API
endpoint receives a request for a SHA-256 that has no cached thumbnail:

1. Look up the file's `current_path` in the registry (must be in `pending` status).
2. Validate that the physical file exists at `current_path`.
3. Generate the thumbnail using Pillow (PIL). Read the source image, apply EXIF
   orientation, resize with Lanczos resampling, convert to sRGB, encode as WebP.
4. Write the thumbnail atomically: write to a temporary file in the same directory,
   then `os.rename()` to the final path. This prevents serving a partially-written file.
5. Return the generated thumbnail.

If the source file is not an image (e.g., a video or document), the endpoint returns a
404 with a JSON error body. The frontend falls back to a file-type icon placeholder.

#### 5.3.3 Supported source formats

Pillow-decodable image formats: JPEG, PNG, WebP, HEIF/HEIC (via pillow-heif), TIFF,
BMP, GIF (first frame only).

Video thumbnails (MP4, MOV) are out of scope for Phase 1.5. Video files return 404 from
the thumbnail endpoint. The frontend handles this by showing a video-type placeholder
icon. Video thumbnail generation may be added in a future phase using ffmpeg.

#### 5.3.4 Error handling

| Condition | Behavior |
|-----------|----------|
| SHA-256 not in registry | 404 Not Found |
| File status is not `pending` | 404 Not Found (thumbnails serve only pending items) |
| Physical file missing | 404 Not Found; log warning |
| File is not a decodable image | 404 Not Found; cache a zero-byte marker file to avoid repeated decode attempts |
| Pillow decode error (corrupt image) | 404 Not Found; cache a zero-byte marker file |
| Disk write failure | 500 Internal Server Error; do not cache; next request retries |

The zero-byte marker file convention: when a source file cannot produce a thumbnail, a
zero-byte file is written to the cache path. Subsequent requests detect the zero-byte
file and return 404 immediately without attempting decode. The marker is purged when the
source file is purged (see section 5.5).

### 5.4 Thumbnail API endpoint

#### Route

```
GET /api/v1/thumbnails/{sha256}
```

#### Parameters

| Parameter | Location | Type | Required | Description |
|-----------|----------|------|----------|-------------|
| sha256 | path | string | yes | SHA-256 hex digest of the source file |

#### Success response

- **Status:** 200 OK
- **Content-Type:** `image/webp`
- **Cache-Control:** `private, max-age=86400, immutable`
- **ETag:** `"thumb-{sha256}"` (the SHA-256 is content-addressed; the thumbnail for a
  given SHA-256 never changes)
- **Body:** WebP image bytes

The `immutable` cache directive tells the browser that the resource at this URL will
never change for the same SHA-256, eliminating conditional revalidation requests.

#### Error responses

- **404 Not Found:** File not in registry, not in pending status, not a decodable image,
  or physical file missing. Body: `{"detail": "<reason>"}`.
- **500 Internal Server Error:** Generation or I/O failure. Body:
  `{"detail": "Thumbnail generation failed"}`.

#### Authentication

Same `verify_api_token` dependency as existing endpoints.

#### Rate considerations

Thumbnail requests are read-only and idempotent. They participate in the existing
apiFetch retry logic added in Phase 2 Chunk P2-1 (retry on 503, backoff on 429).

### 5.5 Thumbnail cache purge

Thumbnail cache entries must be cleaned up when their source file leaves the `pending`
state. Two purge vectors:

1. **Accept/Reject purge hook.** When `accept_sha256()` or `reject_sha256()` transitions
   a file out of `pending` status, a post-commit hook removes the corresponding
   thumbnail cache file (including any zero-byte marker). This is a best-effort
   deletion — the file lifecycle does not depend on successful cache cleanup.

2. **Periodic cache sweep.** A CLI command (`metricsctl thumbnail-gc`) scans the
   thumbnail cache directory and removes entries whose SHA-256 no longer has `pending`
   status in the registry. This handles cache entries orphaned by missed hooks or
   crashes. The sweep is designed to be run via cron or systemd timer, not as an
   always-on process.

The purge strategy is deliberately simple. Thumbnail cache is a derivative artifact; any
cache entry can be regenerated from the source file. The only cost of a missed purge is
disk space occupied by stale thumbnails.

### 5.6 Thumbnail performance budget

| Metric | Target |
|--------|--------|
| Generation latency (JPEG 12MP source → 480px WebP) | < 200ms |
| Cache hit serving latency | < 5ms (file read + send) |
| Thumbnail file size (typical photo) | 15-40 KB |
| Cache disk overhead per 1000 pending items | ~25 MB |

These targets assume a local SSD for the thumbnail cache. The latency budget for first-
request generation is acceptable because the browser will display the PhotoCard metadata
immediately and progressively render the thumbnail when it arrives. The `<img>` element
uses `loading="lazy"` for items outside the visible render window.

### 5.7 Relationship to registry and file lifecycle

```
                     ┌─────────────────────────────┐
                     │         Registry             │
                     │  files.status = 'pending'    │
                     │  files.current_path = ...    │
                     └────────────┬────────────────┘
                                  │ read-only lookup
                                  ▼
┌────────────────┐      ┌─────────────────────┐      ┌────────────────────┐
│  pending_path  │──────│  Thumbnail Generator │──────│  thumbnail_cache   │
│  (source)      │ read │  (Pillow)            │ write│  (WebP on disk)    │
└────────────────┘      └─────────────────────┘      └────────┬───────────┘
                                                              │ read
                                                              ▼
                                                    ┌──────────────────┐
                                                    │  GET /thumbnails │
                                                    │  (HTTP response) │
                                                    └──────────────────┘
```

The thumbnail subsystem has a read-only relationship with the registry and pending
storage. It never writes to the registry. It never moves, renames, or deletes source
files. The only mutable state it owns is the thumbnail cache directory.

---

## 6. PhotoCard Image Integration

### 6.1 Current state

PhotoCard.svelte renders:

```svelte
<div class="thumb">IMG</div>
```

This is a placeholder that exists solely for layout sizing. The card displays filename,
SHA-256 prefix, account, and timestamp metadata as text.

### 6.2 Target state

PhotoCard.svelte renders:

```svelte
<div class="thumb">
  <img
    src="/api/v1/thumbnails/{item.sha256}"
    alt={item.filename}
    loading="lazy"
    decoding="async"
    onerror={handleImageError}
  />
</div>
```

On image load error (404 for non-image files, network error), the component falls back
to a file-type icon rendered via an inline SVG or a CSS-styled placeholder element. The
fallback is determined by the file extension: image-type extensions show a broken-image
icon; video extensions show a video icon; other extensions show a document icon.

### 6.3 Sizing and aspect ratio

The `.thumb` container maintains a fixed aspect ratio of 4:3 (matching the typical
landscape photo) via `aspect-ratio: 4 / 3`. The `<img>` element uses
`object-fit: cover` to fill the container without distortion, cropping edges as needed.
This matches the UI mock, which shows tightly cropped photo thumbnails filling the card
area.

The card's `min-width: 220px` is preserved. The thumbnail area expands to fill the card
width, and the 4:3 aspect ratio determines the height (~165px at 220px width).

### 6.4 Loading states

| State | Visual |
|-------|--------|
| Loading (img not yet loaded) | Pulsing skeleton rectangle matching `.thumb` dimensions |
| Loaded | Full thumbnail image |
| Error (non-image file) | File-type icon centered in `.thumb` area |
| Error (generation failed) | Broken-image icon centered in `.thumb` area |

The skeleton pulse uses a CSS animation on the `.thumb` background, matching the existing
design token `--duration-slow` for animation timing.

---

## 7. Updated Acceptance Criteria

### 7.1 Thumbnail backend

- [ ] `GET /api/v1/thumbnails/{sha256}` returns 200 with `image/webp` content for a
      pending item that is a JPEG, PNG, or WebP source file.
- [ ] Repeated requests for the same SHA-256 are served from disk cache (no re-generation).
- [ ] Requests for a non-existent SHA-256 return 404.
- [ ] Requests for a non-pending item (accepted/rejected/purged) return 404.
- [ ] Requests for a non-image file return 404 and create a zero-byte marker.
- [ ] Subsequent requests for a non-image SHA-256 return 404 without attempting decode.
- [ ] Thumbnails are written atomically (temp file + rename).
- [ ] Thumbnail cache files are removed when the source file is accepted or rejected.
- [ ] `metricsctl thumbnail-gc` removes orphaned cache entries.
- [ ] EXIF orientation is applied; metadata is stripped.
- [ ] Authentication is required (same `verify_api_token` as other endpoints).

### 7.2 PhotoCard image rendering

- [ ] PhotoCard renders a real `<img>` element with `src` pointing to the thumbnail API.
- [ ] Images load progressively (skeleton → thumbnail).
- [ ] Non-image files show an appropriate file-type icon fallback.
- [ ] The card maintains consistent dimensions across loading, loaded, and error states
      (no layout shift).

### 7.3 PhotoWheel interaction

- [ ] Mouse scroll wheel navigates the PhotoWheel (one step per detent).
- [ ] Trackpad two-finger swipe navigates with accumulated delta threshold.
- [ ] Touch swipe navigates with velocity-based fling detection.
- [ ] Momentum decay animates through multiple items when release velocity is high.
- [ ] Any new input cancels in-flight momentum.
- [ ] Scroll lock prevents page scroll while the PhotoWheel is active.
- [ ] Scroll lock disengages at queue boundaries.
- [ ] DOM windowing limits rendered items to `activeIndex +/- RENDER_RADIUS`.
- [ ] Adjacent thumbnails are preloaded within `PRELOAD_RADIUS`.
- [ ] All existing keyboard shortcuts (Arrow, A, R, D) continue to work.

### 7.4 Regression

- [ ] All existing Phase 1 integration tests pass without modification.
- [ ] Triage mutations (accept/reject with idempotency keys) are unaffected.
- [ ] Audit trail entries are unaffected.
- [ ] Health endpoint and polling are unaffected.

---

## 8. Impact Analysis on Phase 2

### 8.1 Phase 2 chunks unaffected

| Chunk | Impact |
|-------|--------|
| P2-1 API Client Retry/Backoff | Already complete. The new thumbnail endpoint benefits from the existing retry logic in `apiFetch` — GET requests to `/api/v1/thumbnails/` will retry on 503/429 automatically. No changes needed. |
| P2-3 Audit Timeline Infinite Scroll | No dependency on thumbnails or PhotoWheel changes. Unaffected. |
| P2-4 KPI Threshold Configuration | No dependency. Unaffected. |
| P2-5 API Versioning Policy | The new `/api/v1/thumbnails/` endpoint must be included in the v1 schema snapshot. This is an additive inclusion, not a conflict. |
| P2-6 Build Artifact Versioning | No dependency. Unaffected. |
| P2-7 Caddy LAN Gate | Thumbnail requests must be proxied. The Caddy configuration adds a route for `/api/v1/thumbnails/*` with the same authentication and rate-limiting rules as other API endpoints. This is a minor additive change. |

### 8.2 Phase 2 chunks with dependency

| Chunk | Impact |
|-------|--------|
| P2-2 Filter Sidebar | The Filter Sidebar filters items on the Dashboard, not the Staging Queue. However, the Filter Sidebar design may later extend to filter the Staging Queue by file type. The thumbnail fallback (file-type icons for non-images) established in Phase 1.5 provides the visual vocabulary for such filtering. No blocking dependency, but the Phase 1.5 file-type classification informs Filter Sidebar categories. |

### 8.3 Phase 2 roadmap update required

The Phase 2 implementation roadmap (design/web/roadmaps/web-control-plane-phase2-
implementation-roadmap.md) must add Phase 1.5 as a dependency gate:

```
Phase 1  →  Phase 1.5  →  P2-2 through P2-7
                        ↗
              P2-1 (already complete, no gate)
```

This is a documentation update only. No Phase 2 code or design changes are required.

---

## 9. Design Constants Reference

All design constants introduced in this document, collected for implementation reference:

| Constant | Value | Location |
|----------|-------|----------|
| Scroll-wheel detent threshold | 1 step per detent | PhotoWheel |
| Trackpad accumulated delta threshold | 60px | PhotoWheel |
| Touch swipe dead zone | 10px | PhotoWheel |
| Touch swipe commit threshold | 40px | PhotoWheel |
| Touch fling velocity threshold | 0.3px/ms | PhotoWheel |
| Momentum friction coefficient | 0.92 per frame @60fps | PhotoWheel |
| Momentum minimum velocity | 0.05px/ms | PhotoWheel |
| RENDER_RADIUS | 5 (11 DOM nodes) | PhotoWheel |
| PRELOAD_RADIUS | 3 | PhotoWheel |
| Thumbnail max dimension | 480px longest edge | Thumbnail generator |
| Thumbnail format | WebP lossy, quality 80 | Thumbnail generator |
| Thumbnail cache prefix depth | 2 levels (2-char / 4-char) | Thumbnail storage |
| Cache-Control | private, max-age=86400, immutable | Thumbnail API |
| Generation latency budget | < 200ms | Thumbnail generator |
| Cache hit latency budget | < 5ms | Thumbnail API |

---

## 10. Open Questions

1. **HEIF/HEIC support.** The `pillow-heif` package is required for HEIC decoding.
   This adds a native dependency. Confirm whether the dev container and production
   deployment can accommodate this, or whether HEIC should be deferred.

2. **Video thumbnail generation.** Phase 1.5 explicitly excludes video thumbnails.
   Confirm that returning a placeholder icon for video files is acceptable for the
   initial release.

3. **Thumbnail cache location.** The design proposes `<data_root>/cache/thumbnails`.
   Confirm this is appropriate for the deployment topology, or whether a tmpfs /
   separate filesystem is preferred for cache isolation.

4. **Live photo pair rendering.** When a live photo pair exists (JPEG + MOV), the
   PhotoCard shows the JPEG thumbnail. Should there be a visual indicator that a
   video companion exists? This is a UX question that does not affect the backend
   design.
