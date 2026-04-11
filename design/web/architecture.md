# Web Control Plane Architecture (Consolidated)

Status: Active


This document consolidates Phase 1, Phase 1.5, and stable planning architecture content.

---

## Source Document: architecture.md#source-document-webui-architecture-phase1md

# SvelteKit Web UI Architecture

Date: 2026-04-03
Owner: Systems Engineering
Last Updated: 2026-04-04

---

## 1. Overview

The photo-ingress Web UI is a SvelteKit single-page application (SPA) built with
`@sveltejs/adapter-static`. It is served as pre-built static assets by the FastAPI
backend. There is no server-side rendering (SSR) at runtime — the app is fully
client-side after the initial asset delivery.

**Phase 1 Chunk 5 Status:** Global design system, read-only pages, staging triage
interactions, and blocklist CRUD interactions are implemented. Dashboard, staging,
audit timeline, blocklist, and settings are live.

This document describes:
- Design token system and global styling
- Layout system
- Route and page structure
- Component hierarchy
- State management strategy
- API layer design
- Error handling and loading state patterns

This document is phase-wide. It describes the intended Phase 1 UI end state across
multiple roadmap chunks. Chunk boundaries still apply:

- Chunk 2 covers global tokens, reset styles, base components, and shared stores.
- Chunk 3 covers read-only page wiring.
- Chunk 4 adds staging triage interactions.
- Chunk 5 adds blocklist write controls and optimistic CRUD handling.

---

## 1.5 Global Styling and Design Tokens

### 1.5.1 Design Token System

All visual properties (colours, spacing, typography, shadows, animations) are defined
as CSS custom properties in `webui/src/styles/tokens.css`. This is the single source
of truth for the design system.

**Location:** `webui/src/styles/tokens.css`

**Categories of tokens:**
- Colour palette (background, neutral, status, action, surface, text, border)
- Spacing scale (space-1 through space-16)
- Typography (font families, sizes, weights, line heights)
- Border radius (radius-sm through radius-full)
- Shadows (shadow-sm through shadow-xl)
- Animation (durations and easing functions)

Components reference tokens exclusively. No raw colour hex, pixel values, or named
colours appear in component `<style>` blocks.

See `design/web/detailed-design/design-tokens.md` for the complete token catalogue.

### 1.5.2 Global Reset Stylesheet

**Location:** `webui/src/styles/reset.css`

The reset stylesheet normalizes browser defaults and establishes consistent baselines:
- Removes default margins and padding from all HTML elements
- Normalizes form elements (input, button, textarea, select)
- Applies focus ring styling using `--action-primary` token
- Establishes body background (`--surface-base`) and text colour (`--text-primary`)
- Provides consistent typography sizing and link styling

### 1.5.3 Root Layout Integration

**File:** `webui/src/routes/+layout.svelte`

```javascript
<script>
  import '../styles/reset.css';
  import '../styles/tokens.css';
</script>

<main>
  <slot />
</main>
```

**Import order:** Reset is imported before tokens globally available to all components.

### 1.5.4 Dark Mode Meta Tag

**File:** `webui/src/app.html`

```html
<meta name="color-scheme" content="dark" />
```

This signals native dark-mode support in the browser.

---

## 2. SvelteKit Mode and Adapter

| Setting         | Value |
|----------------|-------|
| Rendering mode  | SPA (CSR-only, `ssr = false` in root layout) |
| Build adapter   | `@sveltejs/adapter-static` with `fallback: '200.html'` |
| TypeScript      | Enabled |
| Base path       | `/` (served from API root) |
| API base URL    | `/api/v1` (same origin, no CORS issues) |

SSR is **deferred**, not rejected. The Phase 1 rationale for deferral:
- The SPA is served as static files from the same origin as the API; no pre-render benefit exists today.
- No SEO requirement exists for an operator tool.
- All data is fetched client-side from the REST API.
- A running Node.js server process on the LXC host is an unnecessary Phase 1 dependency.

SSR remains a viable future upgrade path. See `architecture.md#source-document-web-control-plane-architecture-phase2md` §7 for the conditions under which SSR adoption is warranted and the migration steps to `@sveltejs/adapter-node`.

---

## 3. Layout System

### 3.1 Visual Structure

Every page renders within a single root layout that provides:

```
┌──────────────────────────────────────────────────┐
│  HEADER BAND                                     │
│  Logo | Nav tabs: Dashboard / Staging / Audit /  │
│  Blocklist / Settings     |  Health indicator    │
├──────────────────────────────────────────────────┤
│                                                  │
│  PAGE CONTENT AREA                               │
│  (varies per route)                              │
│                                                  │
│                                                  │
├──────────────────────────────────────────────────┤
│  FOOTER BAND                                     │
│  Version | Last poll time | Registry status      │
└──────────────────────────────────────────────────┘
```

### 3.2 Root Layout File (`src/routes/+layout.svelte`)

The root layout renders:
1. `<AppHeader>` — top navigation band with logo, page tabs, and global health badge.
2. `{@render children()}` — page slot.
3. `<AppFooter>` — bottom status band with version, last poll time, and registry status.

The root layout's `+layout.js` sets `ssr = false` and does not fetch data. Health
state is owned by `health.svelte.js` (see §6.1). `+layout.svelte` calls
`health.connect()` and `health.disconnect()` through a Svelte effect lifecycle, and
`AppHeader` / `AppFooter` subscribe to that store directly.

### 3.3 No Nested Layouts

All pages share the single root layout. No sub-layouts are introduced in Phase 1. This
keeps the layout graph simple and avoids layout inheritance complexity.

---

## 4. Route and Page Structure

```
src/routes/
  +layout.svelte           — Root layout (header, footer, page slot); calls health.connect()/disconnect()
  +layout.js               — Load: version metadata only (no health API call)
  +page.svelte             — Dashboard (/): KPIs, audit timeline preview
  +page.js                 — Load: staging page, health, config, and audit preview
  +error.svelte            — Global error boundary

  staging/
    +page.svelte           — Staging Queue: Photo Wheel + triage controls + metadata panel
    +page.js               — Load: GET /api/v1/staging

  audit/
    +page.svelte           — Audit Timeline: filter row + load-more pagination
    +page.js               — Load: GET /api/v1/audit-log

  blocklist/
    +page.svelte           — Blocklist CRUD: create/edit form, list controls, confirm delete dialog
    +page.js               — Load: blocklist rules

  settings/
    +page.svelte           — Settings: effective config display (read-only)
    +page.js               — Load: GET /api/v1/config/effective
```

### 4.1 Page Responsibilities

| Route       | Responsibility |
|-------------|----------------|
| `/`         | Dashboard with health status, KPI cards, poll runtime card, and recent audit events (last 5). |
| `/staging`  | Photo Wheel triage view with keyboard and button-driven accept/reject/defer actions. |
| `/audit`    | Full audit log with filter by action and explicit load-more pagination (`id DESC`, follow-up uses `after=<last_id>`). |
| `/blocklist`| Blocklist CRUD view: create/edit form, enable/disable toggle, and confirm-before-delete behavior. |
| `/settings` | Read-only display of effective runtime config (`GET /api/v1/config/effective`). |

---

## 5. Component Hierarchy

### 5.1 Global Components (`src/lib/components/`)

```
components/
  layout/
    AppHeader.svelte         — Top band: logo, nav tabs, health badge
    AppFooter.svelte         — Bottom band: version, last poll, registry status
    PageTitle.svelte         — Consistent page heading with optional subtitle

  common/
    KpiCard.svelte           — Single metric box (label, value, status colour bar)
    StatusBadge.svelte       — Coloured dot + label (OK/warn/error/unknown)
    ActionButton.svelte      — Primary action button (accept/reject/defer variants)
    ConfirmDialog.svelte     — Modal confirmation overlay for destructive actions
    ErrorBanner.svelte       — Inline error display for failed API calls
    LoadingSkeleton.svelte   — Placeholder block while data loads
    EmptyState.svelte        — Zero-items messaging with optional action

  dashboard/
    KpiGrid.svelte           — Grid of KpiCard instances for dashboard KPIs
    PollRuntimeChart.svelte  — Sparkline/line chart for 7-day poll runtime
    HealthBar.svelte         — Horizontal coloured gradient bar with status dots
    AuditPreview.svelte      — Recent audit events list (last 5, abbreviated)

  staging/
    PhotoWheel.svelte        — Carousel: center focus, blurred/scaled neighbors
    PhotoCard.svelte         — Individual photo/file card (thumbnail, filename, metadata)
    ItemMetaPanel.svelte     — Detail panel: filename, SHA-256, timestamp, account

  audit/
    AuditTimeline.svelte     — Scrollable event list
    AuditEvent.svelte        — Single audit event row (icon, filename, action, time)

  blocklist/
    BlockRuleList.svelte     — List of block rules with toggle/edit/delete controls
    BlockRuleForm.svelte     — Create/edit form for pattern, rule_type, reason, enabled

  settings/
    ConfigTable.svelte       — Read-only key/value config display
```

### 5.2 Component Dependency Rules

- Components in `layout/` have no dependencies on page-specific components.
- Components in `common/` have no dependencies on `dashboard/`, `staging/`, `audit/`,
  or `blocklist/` components.
- Page-specific components depend only on `common/` components and `$lib/stores`.
- No component imports from `$lib/api` directly — all API interaction goes through
  `+page.js` load functions or store actions.

---

## 6. State Management

### 6.1 Store Inventory (`src/lib/stores/`)

| Store              | Contents | Update Strategy |
|--------------------|----------|-----------------|
| `health.svelte.js` | `{ polling_ok, auth_ok, registry_ok, disk_ok, last_updated_at, error }` with nested `ServiceStatus` values | Store owns polling lifecycle via `connect()` / `disconnect()` with 30s polling. Used by layout header/footer. |
| `kpis.svelte.js`   | `{ pending_count, accepted_today, rejected_today, live_photo_pairs, last_poll_duration_s, loading, error }` | Loaded from staging total + health details; currently read-only and non-mutating. |
| `stagingQueue.svelte.js` | `{ items, cursor, total, activeIndex, loading, error }` | Supports page load/append plus triage actions (`triageItem`), optimistic removal, and rollback on failure. |
| `auditLog.svelte.js` | `{ events, cursor, hasMore, filter, loading, error }` | Supports explicit append via `loadMore()` and filter reset via `setFilter(action)`. |
| `blocklist.svelte.js` | `{ rules, loading, error }` | `hydrate()` plus CRUD actions with optimistic updates and rollback on API errors. |
| `config.svelte.js` | `{ kpi_thresholds, ...effectiveConfig, loading, error }` | Read-only `load()` from `GET /api/v1/config/effective`. |

### 6.2 Store Design Pattern

Stores use Svelte 5's `$state` rune syntax (via `.svelte.js` files) or the classic
writable store pattern. Each store exposes:

- A readable state object (or derived stores for computed values).
- Action functions that call the API layer and update state.
- An error field for per-store error display.

Pages load primary data via `+page.js` load functions and pass it as props. Stores are
used for:
- Cross-component state (health indicator visible in header and footer simultaneously).
- Persistent cursor state across paginated views.

**Health store lifecycle (architectural note):** The `health.svelte.js` store is the
exception to the load-function pattern. Because health data must be available at all
times in both the header and footer regardless of which page is active, it uses a
managed polling lifecycle rather than a page load function. The polling interval and
error backoff are internal to the store. No component or layout file contains
`setInterval` or fetch calls related to health — all of that is encapsulated in the
store module.

### 6.3 Optimistic UI (Chunk 4)

Staging triage uses optimistic UI in `stagingQueue.svelte.js`:

- On `triageItem(action, itemId)`, the selected item is removed from local state before
  API completion.
- On success, optimistic state is retained.
- On failure, a pre-action snapshot is restored, `error` is set, and a toast is pushed.

This behavior is verified by server-side integration tests. Toast rendering assertions are
deferred until browser-level tests are introduced.

### 6.4 Optimistic UI (Chunk 5 Blocklist)

Blocklist CRUD uses optimistic state transitions in `blocklist.svelte.js`:

- `createRule(payload)` appends an optimistic temp row, then replaces it with API response.
- `updateRule(id, payload)` patches the row optimistically, then reconciles with API response.
- `deleteRule(id)` removes the row optimistically before API completion.
- On any API failure, a snapshot rollback restores pre-action state, `error` is set, and a toast is pushed.

`X-Idempotency-Key` values are generated per mutation in store actions (`crypto.randomUUID()` with time/random fallback).

---

## 7. API Layer

**See also:** [api.md (Phase 1 source section)](api.md#source-document-web-control-plane-api-phase1md) for detailed API endpoint specification, response schemas, and authentication reference.

The current backend exposes read models plus triage and blocklist mutation responses:

- `HealthResponse` with nested `ServiceStatus` objects.
- `StagingPage` with `items`, `cursor`, `has_more`, and `total`.
- `AuditPage` with `events`, `cursor`, and `has_more`.
- `EffectiveConfig` with redacted `api_token` and explicit `kpi_thresholds` keys.
- `BlockRuleList` with `rules` entries using the current backend `rule_type` constraints.
- `TriageResponse` with `action_correlation_id`, `item_id`, and target `state`.
- `BlockRule` and `BlockRuleDeleteResponse` for create/update/delete flows.

### 7.1 Location and Structure (`src/lib/api/`)

```
api/
  client.ts        — Base fetch wrapper (bearer header, JSON handling, ApiError)
  health.ts        — GET /api/v1/health
  staging.ts       — GET /api/v1/staging, GET /api/v1/items/{id}
  audit.ts         — GET /api/v1/audit-log
  blocklist.ts     — GET/POST/PATCH/DELETE /api/v1/blocklist
  config.ts        — GET /api/v1/config/effective
  triage.ts        — POST /api/v1/triage/{item_id}/accept|reject|defer
```

### 7.2 Base Client (`client.ts`)

The base client wraps `fetch` with the following behaviours:

- Adds `Authorization: Bearer {token}` header on every request. Token handling remains a
  UI integration concern and must stay aligned with the active backend auth contract.
- Adds `Content-Type: application/json` by default.
- On non-2xx responses, extracts JSON or text error details and throws a typed
  `ApiError` object with `{ status, message, details }`.
- On network failure, throws an `ApiError` with `status: 0` and a "network unavailable"
  message.

### 7.3 Loading States

Each resource module exposes typed async functions. Callers (page load functions and
store actions) handle loading states by:

- Setting a `loading: true` flag before the call.
- Setting `loading: false` and either populating data or populating an error after the
  call resolves or rejects.
- Rendering `<LoadingSkeleton>` while loading is true.
- Rendering `<ErrorBanner>` when an error is set.

### 7.4 Error Handling Strategy (Chunks 3 and 4)

| Error Source | Handling |
|-------------|---------|
| API non-2xx | `apiFetch` throws `ApiError`; route/page/store sets local error state and renders `ErrorBanner` where applicable. |
| Network failure (status 0) | `apiFetch` throws `ApiError('network unavailable', 0, ...)`; UI shows component-level error states. |
| Auth failure (401) | Surfaced as API error to the active view; no dedicated auth-recovery flow in Chunk 3. |
| Triage mutation failure (500/409/404) | `stagingQueue.triageItem()` restores prior queue snapshot and emits toast through `toast.svelte.js`. |
| Blocklist mutation failure (409/404/network) | `blocklist.svelte.js` restores prior snapshot and emits toast through `toast.svelte.js`. |

---

## 8. SvelteKit Configuration Points

### 8.1 `svelte.config.js`

- Adapter: `@sveltejs/adapter-static` with `fallback: '200.html'`.
- No SSR: `ssr: false` in root `+layout.js` via `export const ssr = false`.
- Paths: no base path prefix (served at `/`).

Runtime serving behavior is implemented in `api/app.py` via `SPAStaticFiles`:
- Serve matched static files from `webui/build`.
- For non-`/api/*` misses, serve `200.html` if present.
- If `200.html` is absent, serve `index.html` as fallback.

### 8.2 `vite.config.js`

- Dev proxy: `/api` → `http://localhost:8000/api` for local development.
- No special asset handling beyond defaults (Svelte/Vite handles CSS and image imports).
- Planned containerized dev workflow: run Vite in dedicated development container
  `dev-photo-ingress` (see `docs/deployment/dev-container-workflow.md`). Staging remains
  focused on release validation and smoke/live operator checks.

### 8.3 `app.html`

- Sets `<meta charset="utf-8">` and `<meta name="viewport">`.
- Sets `<meta name="color-scheme" content="dark">`.
- Includes `%sveltekit.head%` and `%sveltekit.body%`.

---

## 9. Responsiveness Strategy

The Web UI targets desktop operator use as the primary context. Responsive adaptation
is planned for usability on tablet devices.

| Breakpoint | Behaviour |
|-----------|----------|
| `>= 1024px` | Full layout: header tabs visible, sidebar visible (dashboard), Photo Wheel wide. |
| `768–1023px` | Header tabs collapse to icon-only. Filter sidebar collapses to a toggle drawer. Photo Wheel reduces neighbor count to 1. |
| `< 768px` | Header shows hamburger menu. Photo Wheel shows center item only, neighbors hidden. Triage controls stack vertically below card. |

Mobile layout is not a Phase 1 priority but the layout structure must not prevent it.
Responsive CSS is implemented with CSS custom properties from the design token system
and CSS grid/flexbox. No media-query breakpoint logic in Svelte components — layout
adapts via CSS alone.

---

## 10. Accessibility Baseline (Chunk 3)

- All interactive controls have `aria-label` attributes.
- Staging triage keyboard controls are active: `ArrowLeft`, `ArrowRight`, `A`, `R`, `D`.
- Color is never the sole indicator of status — icon + color is used throughout.
- Destructive-action confirmation dialog is implemented on the Blocklist page for delete actions.

## 11. Chunk 5 Test Strategy Drift Resolution

Chunk 5 validation uses pytest integration tests, not Playwright.

- API tests: `tests/integration/api/test_blocklist.py`
- UI-flow simulation tests: `tests/integration/ui/test_blocklist_crud.py`

Implemented confirm/cancel validation without DOM harness:

- Confirm path is represented by executing DELETE and verifying rule removal.
- Cancel path is represented by intentionally not executing DELETE and verifying rule remains.

This pattern matches current repository strategy and avoids introducing browser harness overhead mid-phase.

---

## Source Document: web-control-plane-architecture-phase1.5.md

# Web Control Plane — Phase 1.5 Architectural Design

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
existing Phase 2 roadmap (planning/web-control-plane-phase2-implementation-
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

The Phase 2 implementation roadmap (planning/web-control-plane-phase2-
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

---

## Source Document: web-control-plane-project-structure.md

# Project Structure — Web Control Plane Extension

Date: 2026-04-03 (reality alignment: 2026-04-06)
Owner: Systems Engineering

---

## 1. Context

This document describes the folder structure introduced by the Web Control Plane
extension and explains the rationale for each addition. The existing project structure
is preserved in full. All new directories are additive.

Reality alignment note (2026-04-06):
- This document is a design/rationale artifact in `design/web/`.
- Delivery sequencing remains in `planning/`.

---

## 2. Repository Root Layout (Extended)

```
nightfall-photo-ingress/
│
├── src/                            # Existing: core Python package
│   └── nightfall_photo_ingress/
│       ├── adapters/
│       ├── domain/
│       ├── migrations/
│       ├── runtime/
│       ├── cli.py
│       ├── config.py
│       └── ...
│
├── api/                            # NEW: FastAPI application
│   ├── app.py
│   ├── auth.py
│   ├── dependencies.py
│   ├── audit_hook.py
│   ├── rapiddoc.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── staging.py
│   │   ├── triage.py
│   │   ├── audit_log.py
│   │   ├── blocklist.py
│   │   └── config.py
│   ├── services/
│   │   ├── health_service.py
│   │   ├── staging_service.py
│   │   ├── triage_service.py
│   │   ├── audit_service.py
│   │   ├── blocklist_service.py
│   │   └── config_service.py
│   └── schemas/
│       ├── config.py
│       ├── staging.py
│       ├── triage.py
│       ├── audit.py
│       ├── blocklist.py
│       └── health.py
│
├── webui/                          # NEW: SvelteKit single-page application
│   ├── src/
│   │   ├── lib/
│   │   │   ├── api/                # REST API fetch wrappers
│   │   │   ├── components/         # Shared Svelte components
│   │   │   ├── stores/             # Svelte stores (global state)
│   │   │   └── tokens/             # Design tokens (CSS custom properties)
│   │   ├── routes/
│   │   │   ├── +layout.svelte      # Root layout (header + footer)
│   │   │   ├── +layout.js
│   │   │   ├── +page.svelte        # Dashboard (/)
│   │   │   ├── staging/
│   │   │   │   └── +page.svelte    # Staging Queue / Photo Wheel
│   │   │   ├── audit/
│   │   │   │   └── +page.svelte    # Audit Timeline
│   │   │   ├── blocklist/
│   │   │   │   └── +page.svelte    # Blocklist / Rules
│   │   │   └── settings/
│   │   │       └── +page.svelte    # Settings / Config view
│   │   └── app.html
│   ├── static/
│   │   ├── favicon.svg
│   │   └── rapiddoc/               # RapiDoc static asset
│   │       └── rapidoc-min.js
│   ├── package.json
│   ├── svelte.config.js
│   └── vite.config.js
│
├── design/                         # EXISTING + EXTENDED: architecture and UI specs
├── planning/                       # EXISTING + EXTENDED
├── install/
├── systemd/
├── tests/
│   ├── unit/                       # isolated Python tests; run outside staging environment
│   ├── integration/                # isolated cross-module tests; run outside staging environment
│   │   └── api/                    # isolated ASGI API contract tests for the web control plane
│   │   └── ui/                     # isolated UI integration tests for web control plane routes/behavior
│   ├── staging/                    # staging-environment-only tests with runtime/container deps
│   └── staging-flow/               # production-flow staging tests against the staging environment
├── conf/
└── pyproject.toml
```

---

## 3. Module Boundaries and Rationale

### 3.1 `api/` — FastAPI Application

The `api/` directory is a separate top-level Python package (or sub-package under
`nightfall_photo_ingress`) that contains only the HTTP boundary layer. It does not
contain domain logic.

**Layering rule:** `api/` imports from `src/nightfall_photo_ingress/` (domain and
registry). Domain modules never import from `api/`. This preserves the existing
architecture's clean inward dependency direction.

**Subdirectories:**

| Directory    | Purpose |
|-------------|---------|
| `routers/`  | FastAPI router modules, one per resource group. Handles path/query validation and auth dependency injection. |
| `services/` | Application-level service objects. Translates validated HTTP requests into domain operations. Contains no repository calls; delegates to existing domain services. |
| `schemas/`  | Pydantic models for request bodies and JSON responses. No domain objects cross the API boundary directly. |
| `app.py`    | Application factory function and FastAPI lifespan context (connect registry, bind startup/shutdown hooks). |
| `dependencies.py` | Request-based dependency providers that read `AppConfig` and the registry connection from `request.app.state`. |
| `auth.py`   | Bearer token validation dependency. Reads `Authorization: Bearer` header and compares against config value. |
| `audit_hook.py` | Decorator/context manager that ensures audit log write precedes state mutation commit. |
| `rapiddoc.py` | Static HTML route for `/api/docs` plus local RapiDoc asset serving. |

Request-throttling note:
- No in-process request-throttling module is part of the active Phase 1 API tree.
- Request throttling is deferred to mandatory proxy-level controls in Phase 2.

### 3.2 `webui/` — SvelteKit SPA

The `webui/` directory is a fully self-contained Node.js project (SvelteKit). It builds
to static assets (`webui/build/`) which are served by the FastAPI application at the
`/` URL prefix.

**Why a top-level directory, not nested under `api/`:** The SvelteKit project has its
own `package.json`, `node_modules`, and build toolchain. Keeping it at the root of
the repository makes the build pipeline explicit and avoids confusion between Python
dependencies and Node.js dependencies.

**Build output:** `webui/build/` (gitignored). The FastAPI application mounts this
directory as a static files mount at `/`. The SvelteKit build target is
`@sveltejs/adapter-static` with a single-file fallback for SPA client-side routing.

### 3.3 `design/` Extensions

New design documents are added alongside existing architecture documents. No existing
documents are modified. New files are:

- `architecture.md#source-document-webui-architecture-phase1md` — SvelteKit structure, stores, API layer, layout system.
- `detailed-design/design-tokens.md` — Dark-mode design token catalogue.
- `planning/implemented/web-design-source/webui-component-mapping-phase1.md` — Mockup analysis, component mapping, interaction logic.

### 3.4 `tests/` Layout and Environment Boundaries

The repository now distinguishes tests by execution environment:

| Test area | Purpose | Environment |
|-----------|---------|-------------|
| `tests/unit/` | Fast isolated unit tests | Any local dev environment |
| `tests/integration/` | Isolated integration tests without staging container dependency | Any local dev environment |
| `tests/integration/api/` | Isolated FastAPI/ASGI contract tests for the web control plane | Any local dev environment |
| `tests/staging/` | Tests that require the staging environment or runtime package dependencies present there | Staging environment only |
| `tests/staging-flow/` | Production-flow validation against the staging environment | Staging environment only |

The API contract tests are intentionally separated from `tests/staging/` and placed under
`tests/integration/api/` so they participate in the normal default pytest collection
(`tests/unit` + `tests/integration`) without depending on container-only prerequisites.

Current test harness note: isolated FastAPI API tests use in-process ASGI transport and a
SQLite connection opened with `check_same_thread=False` so the same test registry can be
shared safely across the request-handling path exercised by the test client.

### 3.5 Roadmap references

Execution sequencing and phase/chunk status are documented in:

- `planning/implemented/web-control-plane-phase1-implementation-roadmap.md`
- `planning/planned/phase-2-architecture-roadmap.md`
- `planning/implemented/web-control-plane-phase1-scope.md`

---

## 4. Deployment Topology Inside LXC Container

### 4.1 Service Layout

The `photo-ingress` LXC container will host three systemd services after the extension:

| Service unit                  | Process              | Listens on           |
|-------------------------------|----------------------|----------------------|
| `nightfall-photo-ingress.service`       | Python CLI poll      | — (background timer) |
| `nightfall-photo-ingress-trash.service` | Python CLI trash job | — (background timer) |
| `nightfall-photo-ingress-api.service`   | Uvicorn + FastAPI    | `127.0.0.1:8000` (Phase 1) |

The API service depends on the registry database being available. It does not depend on
the poll or trash services.

### 4.2 Static Asset Serving

The SvelteKit build output (`webui/build/`) is owned by the `nightfall-photo-ingress-api` service.
FastAPI serves the built static files at the root URL. No separate web server (Nginx,
Caddy) is required in Phase 1.

In Phase 2, a reverse proxy (Nginx or Caddy) may be placed in front for:
- TLS termination.
- Serving static assets with cache headers.
- LAN exposure hardening.

### 4.3 Build and Deploy Flow

```
Development machine:
  1. cd webui && npm run build        → produces webui/build/
  2. pip install -e .                 → installs photo-ingress-core + api

LXC container (deploy target):
  3. rsync webui/build/ → container:/opt/photo-ingress/webui/build/
  4. pip install -e .    → ensures api deps present
  5. systemctl restart nightfall-photo-ingress-api
```

For initial deployment and ongoing operator use, static assets are considered a
deployment artifact — they are not served from a separate Node.js process at runtime.

### 4.4 Registry Access

The FastAPI application opens the SQLite registry database in read-write mode using the
same database path configured in `photo-ingress.conf`. The existing registry module
provides the connection factory. A connection-per-request or connection-pool-of-one
model is used; SQLite WAL mode supports concurrent reads from the CLI and the API.

### 4.5 No Docker Compose

Docker Compose is not used. The LXC container already provides process isolation.
systemd unit files replace Docker Compose's service orchestration role for this project.

---

## 5. Development Workflow (Local)

When developing locally (outside LXC):

1. Run `uvicorn api.app:app --reload --port 8000` from the repo root.
2. Run `cd webui && npm run dev` to start the Vite dev server (default port 5173).
3. The Vite dev server proxies `/api/` requests to `localhost:8000` via `vite.config.js`
   proxy configuration.
4. The browser loads the SvelteKit SPA from Vite; API calls reach the Python server.

This two-process dev setup is standard for SvelteKit + backend combinations and requires
no additional tooling.

---

## 6. gitignore Additions

The following paths should be added to `.gitignore`:

```
webui/node_modules/
webui/.svelte-kit/
webui/build/
api/__pycache__/
```

---

## 7. Dependency Manifests

**Python side (`pyproject.toml` additions):**

```
fastapi
uvicorn[standard]
```

The `[standard]` extra adds `uvloop` and `httptools` for improved performance on Linux.

**Node.js side (`webui/package.json` devDependencies):**

```
@sveltejs/kit
@sveltejs/adapter-static
svelte
vite
@sveltejs/vite-plugin-svelte
```

No runtime Node.js process is required in production. `node_modules` and the build
toolchain are development-only.

---

## Source Document: web-control-plane-architecture-phase2.md

# Phase 2 Architecture

Date: 2026-04-03
Owner: Systems Engineering
Depends on: planning/implemented/web-control-plane-phase1-scope.md,
            planning/planned/phase-2-architecture-roadmap.md,
            design-decisions.md#source-document-web-control-plane-techstack-decisionmd

---

## 1. Purpose and Scope

This document defines the Phase 2 architecture for the photo-ingress Web Control Plane.
Phase 2 begins only after Phase 1 (Phases 0–4 in integration-plan.md) is stable and
validated in production use.

Phase 2 has two tiers:

- **Phase 2 Mandatory:** Items that must be completed before LAN exposure is permitted.
  These are prerequisites for any operator access outside localhost.
- **Phase 2 Optional:** Items that improve the system but do not gate LAN exposure.
  They may be adopted independently in any order based on operational need.

---

## 2. Phase 2 Mandatory vs Optional Summary

| Item | Tier | Rationale |
|------|------|-----------|
| Reverse proxy (Nginx or Caddy) | Mandatory | TLS, compression, access logs, rate limiting |
| TLS termination | Mandatory | Operator credentials must not transit LAN in cleartext |
| Proxy-level rate limiting | Mandatory | Required before any LAN exposure |
| API versioning policy | Mandatory | Required before any breaking API change |
| Build artifact versioning and rollback | Mandatory | Enables safe re-deployment |
| Retry/backoff for read-only API client | Mandatory | Reduces transient error noise |
| Filter Sidebar | Mandatory | File-type filtering deferred from Phase 1 |
| Audit Timeline: Pagination → Infinite Scroll | Mandatory | Phase 1 uses LoadMoreButton; Phase 2 adds auto-scroll |
| KPI Threshold Configuration via API | Mandatory | Phase 2 settings UI for operator-editable thresholds |
| SSR capability | Optional | Only if load time or auth complexity warrants it |
| SQLite → Postgres migration | Optional | Only under concurrency pressure |
| Background worker architecture | Optional | For sidecar/thumbnail processing |
| Task queue (lightweight or Redis) | Optional | Depends on background worker adoption |
| OIDC/OAuth authentication | Optional | For multi-operator environments |
| CDN / asset caching | Optional | For remote access or multi-site deployment |

---

## 3. Reverse Proxy

### 3.1 Decision: Caddy over Nginx

| Factor | Caddy | Nginx |
|--------|-------|-------|
| TLS with automatic cert | Built-in (ACME, internal CA) | Requires certbot or manual config |
| Configuration complexity | Single `Caddyfile`, minimal syntax | `nginx.conf` with multiple blocks |
| Dynamic reload | Built-in | Requires `nginx -s reload` |
| Brotli compression | Built-in | Requires `ngx_brotli` module (often not in distro packages) |
| Structured access logs | JSON logs natively | Requires log format config |
| Systemd socket activation | Supported | Supported |

**Decision:** Caddy is preferred for a single-server LXC deployment. Its automatic TLS
from a local CA (`tls internal`) is a significant operational simplification compared
to manual certificate management. If the operator's environment mandates Nginx for
policy or familiarity reasons, Nginx is an acceptable alternative with equivalent
capability.

### 3.2 Proxy Topology (Phase 2)

```
Internet / LAN operator browser
        │
        │  HTTPS (443)
        ▼
  Caddy (systemd service, :443)
        │
        ├── /           → Static file serve from versioned build directory
        │                 (Cache-Control: immutable for hashed assets)
        │
        ├── /api/       → Reverse proxy to Uvicorn (127.0.0.1:8000)
        │                 (X-Forwarded-For, X-Real-IP forwarded)
        │
        └── /api/docs   → Reverse proxy to Uvicorn (no auth bypass needed;
                          Caddy passes bearer token through)
```

Static assets are served by Caddy directly from the versioned build directory. This
removes static file I/O from the Uvicorn process entirely, improving API response
latency.

### 3.3 Uvicorn Binding Change for Phase 2

In Phase 1, Uvicorn binds to `127.0.0.1:8000` (localhost only).
In Phase 2, this is unchanged. Uvicorn continues to bind to localhost. Caddy is the
only process that accepts external connections. This provides defence-in-depth: even
if Caddy is misconfigured, Uvicorn is not directly reachable from the LAN.

### 3.4 Security Headers at Proxy Level

In Phase 2, security headers are enforced at the Caddy configuration layer.
Caddy adds these on all responses:

| Header | Value |
|--------|-------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` |

Current implementation note:
- The current FastAPI application does not yet ship a dedicated security-header
  middleware layer for the control plane.
- Phase 2 therefore introduces the durable header policy at the proxy, rather than
  migrating an already-live app-level header stack.

### 3.5 Rate Limiting at Proxy Level

In Phase 2, Caddy's rate limiting module (`caddy-ratelimit` or equivalent) becomes the
first durable request-throttling layer for the control plane. This provides:

- Rate limiting before requests reach the Python process (lower CPU cost for abusive
  traffic).
- Shared limits for static and API endpoints from a single configuration point.
- Log visibility for rate-limited requests in the access log.

Current implementation note:
- The current control-plane app does not ship a verified in-process rate-limiting
  dependency today.
- Phase 2 should not assume a removal migration here; it should introduce proxy-level
  limiting directly and avoid overlapping policies unless an explicit short-lived
  localhost safeguard is intentionally added.

### 3.6 Phase 2 Mandatory Reverse Proxy Checklist

Before LAN exposure is enabled:

1. Caddy (or Nginx) running as a systemd service in the LXC container.
2. TLS: certificate issued from local CA or self-signed, with operator trust imported.
3. HTTPS-only: HTTP redirects to HTTPS.
4. Static asset serving from versioned build directory (see §4).
5. Security headers applied.
6. Access logs in structured JSON format, written to a log file or journald.
7. Rate limiting active for `/api/` path.
8. Uvicorn remains on `127.0.0.1` only.
9. No overlapping legacy app-level rate limiter remains active unless explicitly retained
  as a temporary localhost-only safeguard.
10. CORS allowlist updated to match the LAN hostname (e.g., `https://photo-ingress.lan`).

---

## 4. Build Artifact Versioning and Rollback

### 4.1 Strategy

In Phase 1, `webui/build/` is overwritten on each deployment. In Phase 2, builds are
versioned using a timestamp or release tag, enabling atomic rollback.

**Directory layout on the LXC host:**

```
/opt/photo-ingress/
  webui/
    releases/
      2026-04-03T1200/     ← named by deployment timestamp or tag
        index.html
        _app/
        200.html
      2026-04-10T0900/     ← newer release
        ...
    current → releases/2026-04-10T0900/   ← symlink; Caddy serves from this path
```

### 4.2 Deployment Procedure

1. Build `webui/build/` locally.
2. Upload `webui/build/` to a new timestamped release directory on the host.
3. Verify the new build directory is complete.
4. Update the `current` symlink atomically.
5. Caddy picks up the new directory on the next request (no restart required if
   symlink resolution is fresh per request — or a Caddy reload is issued).
6. Keep the previous two releases for rollback.

### 4.3 Rollback

To roll back:
1. Re-point the `current` symlink to the previous release directory.
2. No Uvicorn restart required (API is separate from UI assets).
3. No user sessions are lost (the SPA is stateless).

### 4.4 API Release Correlation

Each static build embeds the API version string it was built against (as a
build-time environment variable baked into the SPA). On startup, the SPA can verify
that the API version it expects matches the running API. Version mismatch renders a
banner prompting a page refresh rather than failing silently.

---

## 5. API Versioning Policy

### 5.1 Current State (Phase 1)

All endpoints are under `/api/v1/`. No formal versioning policy exists yet.

### 5.2 Phase 2 Policy

**Version prefix:** All routes carry a major version prefix (`/api/v1/`, `/api/v2/`,
etc.). Minor changes that are backwards compatible do not require a new prefix.

**Breaking vs non-breaking change classification:**

| Change type | Classification |
|-------------|---------------|
| Adding a new field to a response body | Non-breaking |
| Adding a new optional query parameter | Non-breaking |
| Adding a new endpoint | Non-breaking |
| Removing a field from a response body | Breaking |
| Changing a field name or type | Breaking |
| Removing an endpoint | Breaking |
| Changing required headers or auth scheme | Breaking |
| Changing pagination cursor format | Breaking |

**Deprecation timeline:**
- Breaking changes require a new version prefix (e.g., `/api/v2/`).
- The prior version is supported for a minimum of 60 days after the new version
  is available, unless a security issue requires immediate removal.
- Deprecated endpoints return a `Deprecation: true` response header and a
  `Sunset: {date}` header indicating removal date.
- The SPA is updated to use the new version before the old version is sunset.

**Intra-version stability guarantee:**
- Within a single major version, the response shape is stable.
- Additive changes (new optional fields) are permitted without a version bump.
- The OpenAPI schema for each version is snapshotted at release and kept in
  `docs/api/` for reference.

### 5.3 v2 Trigger Conditions

A v2 is warranted when:
- A response shape change requiring a breaking transition is needed (field rename,
  restructure, cursor format migration).
- The authentication scheme migrates from static bearer token to OIDC/OAuth.
- The pagination strategy changes incompatibly.

---

## 6. API Client Retry and Backoff (Phase 2 Mandatory)

### 6.1 Scope of Retry

Retry is applied only to read-only (GET) requests. Mutating requests (POST, PATCH,
DELETE) remain fail-fast with idempotency-key replay as the only retry mechanism.

### 6.2 Retry Policy

| Condition | Retry behaviour |
|-----------|----------------|
| Network failure (status 0) | Retry up to 3 times with exponential backoff |
| HTTP 503 (Service Unavailable) | Retry up to 3 times with exponential backoff |
| HTTP 429 (Rate Limit) | Retry after the `Retry-After` header value |
| HTTP 5xx (other) | No silent retry; show error banner |
| HTTP 4xx | No retry; show error banner |

**Backoff schedule:** initial 500ms, doubling with ±10% jitter. Maximum wait: 8
seconds. If all retries fail, the `ApiError` is surfaced as in Phase 1.

### 6.3 Health Polling Resilience

The `health.svelte.js` store polling interval survives transient failures silently using
the retry policy above. A visible error indicator in the header badge appears only when
three consecutive polls fail after retries.

### 6.4 Mutating Endpoint Retry Pattern

For mutating endpoints, the operator triggers the retry manually via a "Retry" button
on the error banner. The same idempotency key is reused on a manual retry (safe because
the server replays the prior result on a duplicate key). No automatic retry is performed
on mutations.

---

## 7. SSR as Optional Future Mode

### 7.1 Current State (Phase 1)

The SPA uses `@sveltejs/adapter-static`. SSR is disabled. This is an operator-only
tool served from localhost.

### 7.2 Conditions for SSR Adoption (Phase 2 Optional)

SSR is worth revisiting if one of the following becomes true:

1. **Multi-user access:** More than one simultaneous operator session is needed.
   SSR enables server-side auth guard and session isolation without exposing auth state
   to the client.
2. **Load time requirement:** On degraded LAN conditions, a pre-rendered HTML first
   paint is measurably better (threshold: FCP > 3s on nominal LAN connection).
3. **Auth complexity:** The OIDC/OAuth migration (see §10) requires per-request
   server-side cookie validation more naturally handled in a SvelteKit server context.

### 7.3 Upgrade Path

If SSR is adopted:

1. Switch from `@sveltejs/adapter-static` to `@sveltejs/adapter-node`.
2. The SvelteKit Node.js server process runs as a second systemd service
   (`nightfall-photo-ingress-ui.service`) on `127.0.0.1:3000` (or similar port).
3. Caddy proxies `/` → `127.0.0.1:3000` instead of serving static files directly.
4. API calls in `+page.server.js` load functions use server-side fetch with the
   bearer token in server environment variable (never exposed to client).
5. The Caddy static asset path is removed; Caddy proxies all requests.

### 7.4 Compatibility

The FastAPI API layer is unaffected by the frontend adapter change. The REST API
contract does not change. The SPA upgrade from adapter-static to adapter-node
is a frontend-only migration.

---

## 8. SQLite → Postgres Migration Path (Phase 2 Optional)

### 8.1 Current State

Phase 1 uses SQLite in WAL mode. The registry and all new tables
(`ui_action_idempotency`, `blocked_rules`) are in a single SQLite database.

### 8.2 Migration Trigger Conditions

Migration to Postgres is warranted only if:

- Sustained concurrent write contention produces measurable latency (threshold:
  p95 write latency > 100ms on triage actions under normal operational load).
- Multiple operator sessions require isolation for long-running read transactions.
- The background worker (§9) produces write throughput that starves the CLI poll cycle.

### 8.3 Migration Strategy

If migration is triggered:

1. Introduce a database abstraction layer in the existing domain modules (repository
   pattern). This is a prerequisite for safe migration without changing business logic.
2. Export the SQLite database schema to a Postgres-compatible schema.
3. Migrate existing data with a one-time export/import script.
4. Run the new Postgres instance as a containerised service inside the existing LXC
   container (Postgres in LXC is well-supported and avoids introducing a new container).
5. Update the connection factory in `config.py` to accept a `database_url` configuration
   key; existing SQLite path remains the default.
6. Run the two databases in parallel under a feature flag until validation is complete.
7. Switch to Postgres; keep SQLite as read-only archive for 30 days, then decommission.

### 8.4 Impact on API Layer

The FastAPI application service layer is unaffected if the repository pattern is
correctly implemented. No router, schema, or service logic changes during DB migration.

---

## 9. Background Worker Architecture (Phase 2 Optional)

### 9.1 Scope

The background worker covers:
- Sidecar/XMP metadata fetch jobs.
- On-demand thumbnail generation and disk cache.

Both were deferred from the integration-plan Phase 5 scope.

### 9.2 Architecture

The background worker runs as a third systemd service
(`nightfall-photo-ingress-worker.service`) inside the same LXC container.

**Job queue:** In the lightweight Phase 2 model, the job queue is a SQLite table
(`sidecar_jobs`, `thumbnail_jobs`) polled at a configurable interval by the worker
process. This requires no new process or dependency beyond SQLite.

The worker is a Python process that:
1. Queries the `sidecar_jobs` table for items with `state = 'queued'`.
2. Claims a batch (updates `state = 'running'`).
3. Executes the job.
4. Updates `state = 'done'` or `state = 'failed'` with error captured.
5. Sleeps for the configured poll interval.

This is a pull-model queue using SQLite as a durable message store. It is simple,
observable, and requires no additional infrastructure.

### 9.3 Worker / API Interaction

- The API enqueues jobs by inserting rows into `sidecar_jobs` table.
- The worker reads and updates those rows.
- SQLite WAL mode accommodates the concurrent access.
- The API exposes job status via `GET /api/v1/items/{item_id}` (sidecar state field).

### 9.4 Upgrade to Redis (Phase 2+ Optional)

If the SQLite-backed queue becomes a bottleneck (high job throughput or many parallel
workers), Redis can replace it. The queue abstraction in the worker service must be
designed as an interface with two implementations (SQLite and Redis) so the switch does
not require changes to the job logic. This is deferred to a phase 2+ iteration.

---

## 10. Enhanced Authentication: OIDC/OAuth (Phase 2 Optional)

### 10.1 Current State

Phase 1 uses a single static bearer token. This is adequate for a solo operator on a
trusted LAN.

### 10.2 Migration Trigger Conditions

- More than one human operator requires individual identity tracking in audit events
  (currently `actor` is always the single configured token name).
- The operator's organisation requires MFA.
- The deployment is exposed beyond the local LAN (e.g., VPN-accessible server).

### 10.3 Proposed Auth Architecture

**Provider:** An existing Authentik, Keycloak, or similar OIDC provider already present
in the operator's infrastructure. No new auth service is introduced specifically for
photo-ingress.

**Integration method:** Caddy handles the OIDC redirect flow via the `caddy-auth-portal`
module or a forward-auth sidecar. The FastAPI backend validates the JWT issued after
successful OIDC login. No session state is stored in the API backend.

**Audit integration:** The `actor` field in audit events transitions from a static token
name to the authenticated user identity (sub claim from JWT). This is a non-breaking
change to the audit_log table (the column already exists).

**Fallback:** Static bearer token auth is preserved as a fallback for automated tooling
(e.g., maintenance scripts that call the API directly). OIDC is the interactive operator
path.

### 10.4 Impact on Phase 1 API Layer

The FastAPI `auth.py` dependency is updated to accept both OIDC JWTs and the static
bearer token. No router, schema, or service logic changes. This is a drop-in replacement
of the auth dependency.

---

## 11. Proxy-Level Rate Limiting

### 11.1 Phase 1 vs Phase 2

The original Phase 1 intent included an in-process FastAPI rate limiter, but the
current control-plane baseline does not rely on a shipped app-level rate-limiting
dependency. That leaves the following open concern set for LAN exposure:
- Requests currently reach Python before any dedicated control-plane throttling policy
  is applied.
- There is no shared request-throttling state across future multi-process topologies.
- Rate-limit observability is absent until a front-door limiter is added.

### 11.2 Phase 2 Approach

Caddy's rate limiting module intercepts requests before they reach Python. Benefits:
- Rate limit state survives Uvicorn restarts (Caddy is a separate process).
- Requests are rejected with no Python overhead.
- Rate limit logs appear in Caddy's structured access log alongside all other requests.

### 11.3 Rate Limit Policy (Phase 2)

| Path pattern | Limit | Window |
|-------------|-------|--------|
| `POST /api/` | 30 req/min | Per IP |
| `PATCH /api/` | 30 req/min | Per IP |
| `DELETE /api/` | 20 req/min | Per IP |
| `GET /api/` | 120 req/min | Per IP |
| All paths (global) | 300 req/min | Per IP |

These become the primary control-plane rate limits. No document should assume there is
an already-live FastAPI limiter to remove unless that implementation is added in a
separate, explicitly documented localhost-only hardening step.

---

## 12. CDN and Asset Caching (Phase 2 Optional)

### 12.1 Applicability

CDN integration is only relevant if:
- The UI is accessed over WAN (not just LAN).
- Static asset load time is a measured operator pain point.
- The deployment is multi-site.

For the standard single-LAN-server LXC deployment, Caddy's local caching headers
on static assets are sufficient.

### 12.2 Caching Strategy for Static Assets

Caddy serves the SvelteKit static build. SvelteKit's Vite build outputs files with
content-hash filenames (e.g., `_app/immutable/entry-abc123.js`). Caddy sets:

```
Cache-Control: public, max-age=31536000, immutable
```

for all files under `_app/immutable/` (never change for a given filename).

For `index.html` and `200.html`:

```
Cache-Control: no-cache
```

This ensures the SPA shell is always fresh while hashed assets are cached aggressively
by the browser.

### 12.3 CDN Integration (Optional, Phase 2+)

If a CDN is warranted, the versioned build directory content is uploaded to the CDN
origin bucket. The CDN is configured to respect `Cache-Control` headers. The Caddy
reverse proxy continues to handle API requests; only static assets are served from CDN.
This requires a configuration step to update the SvelteKit build's `paths.assets` base
to the CDN origin URL.

---

## 13. Filter Sidebar Introduction (Phase 2 Mandatory)

### 13.1 Context

The Phase 1 Dashboard uses a full-width main content area. The Dashboard mockup shows a
Filter Sidebar (file-type checkboxes: All Files, Images, Videos, Documents), but this
was deferred in the Phase 1 re-evaluation (C9) because it is browsing ergonomics, not
core operator workflow.

### 13.2 Requirements

- The sidebar provides per-type filtering scoped to staging queue items and dashboard
  KPI counts.
- Selecting `Images` shows only image-type items in the staging queue count and the
  audit preview; `All Files` is the default unfiltered state.
- Filter state is ephemeral (session only; not persisted to the URL or server).
- The sidebar is only present on the Dashboard page in Phase 2. The Staging Queue
  page has its own inline filter in a later iteration.

### 13.3 API Changes

No new endpoint path is required. Phase 2 extends `GET /api/v1/staging` with an
optional `type` query parameter for dashboard-scoped filtering.

`GET /api/v1/config/effective` returns an `allowed_types` list so the sidebar options are
dynamic (driven by what the system is configured to process), not hardcoded in the UI.

### 13.4 Frontend Architecture

```
Dashboard Page
  FilterSidebar (new Phase 2 component)
    props: options[] (from config store), selected: string, onChange: (type) => void
  |
  └─ Emits selected type to page-level svelte $state
        └─ All Dashboard API calls gain type= query parameter when filter active
```

The sidebar introduces a `filterType` state variable at page level. This is passed
as a prop to all child components that query the API for counts or items.

### 13.5 Layout Changes

The Phase 1 full-width main content grid gains a sidebar column:

```
┌──────────┬──────────────────────────────────────────────┐
│ Filters  │ KPI grid + Audit timeline                      │
└──────────┴──────────────────────────────────────────────┘
```

Responsive behaviour is as originally specified in planning/implemented/web-design-source/webui-component-mapping-phase1.md §6.2 and §6.3
(slide-out drawer on tablet, modal sheet on mobile).

### 13.6 Phase 1 Compatibility

- Phase 1 API endpoints are unchanged (the `type` query parameter is already defined).
- Phase 1 SPA has no `FilterSidebar` component; adding it in Phase 2 is purely additive.
- The Phase 2 Dashboard layout CSS adds a grid column; no Phase 1 component changes.

---

## 14. Audit Timeline: Pagination → Infinite Scroll (Phase 2 Mandatory)

### 14.1 Context

Phase 1 uses an explicit `LoadMoreButton` for the Audit Timeline. The button appends the
next cursor page to the list when clicked. This is correct Phase 1 behaviour (C10).

### 14.2 Phase 2 Change

Phase 2 replaces the explicit `LoadMoreButton` with an IntersectionObserver-based
automated scroll trigger. When the operator scrolls to within 200px of the bottom of
the list, the next cursor page is fetched and appended automatically.

### 14.3 Migration Approach

The backend API is unchanged. `GET /api/v1/audit-log?after=...&limit=...` continues
to operate identically. The migration is frontend-only:

1. Replace `<LoadMoreButton>` in `AuditTimeline` with a sentinel `<div>` observed by
   `IntersectionObserver`.
2. The observer fires the next-page fetch when the sentinel enters the viewport.
3. A loading skeleton row is shown while the next page loads.
4. If no more pages are available, the sentinel is removed from the DOM.
5. Filter changes reset cursor state and clear the appended list, triggering a fresh
   first-page load (same behaviour as Phase 1).

### 14.4 Phase 1 Compatibility

`LoadMoreButton` remains in `src/lib/components/common/` and is retained for explicit
pagination flows. No Phase 1 component is removed during this migration.

### 14.5 Rollback

Restoring the `LoadMoreButton` variant requires a single component swap in
`AuditTimeline.svelte`. The API contract is unchanged.

---

## 15. KPI Threshold Configuration via API (Phase 2 Mandatory)

### 15.1 Context

In Phase 1, KPI thresholds (the warning/error boundaries for each metric's status bar
colour) are served from `GET /api/v1/config/effective` as the `kpi_thresholds` field. They are
read from `photo-ingress.conf` on the server. The operator edits the config file
directly to change thresholds (Phase 1 behaviour).

Phase 2 adds an in-UI settings page allowing the operator to view and edit KPI
thresholds without SSH access to the server.

### 15.2 New API Endpoint (Phase 2)

```
PATCH /api/v1/config/thresholds
```

Request body: JSON object mapping metric keys to `{ warning: number, error: number }`.

Validation rules:
- `warning < error` for all metrics.
- All values must be non-negative integers (or floats for percentage-based metrics).
- Unknown metric keys are rejected (`422 Unprocessable Entity`).

The endpoint updates the running configuration and persists changes to a
`config_overrides` SQLite table (so file-based config remains the baseline; overrides
take precedence at runtime). A `GET /api/v1/config/effective` call after a successful PATCH
reflects the updated values immediately.

### 15.3 Frontend: Settings Page

The Settings page (`/settings`, already a Phase 1 route) gains a
"KPI Thresholds" section with an editable form:

- One row per metric (label, warning input, error input, unit indicator).
- Inline validation (warning must be less than error).
- "Save" button calls `PATCH /api/v1/config/thresholds`; success toasts confirmation.
- "Reset to defaults" restores config-file values (calls DELETE on the overrides row).

### 15.4 Phase 1 Compatibility

`GET /api/v1/config/effective` already returns `kpi_thresholds` in Phase 1 (read-only). Phase 2
adds the PATCH endpoint. The GET response shape is unchanged (additive `kpi_thresholds`
field was already present). No breaking change.

### 15.5 Rollback

If the PATCH endpoint is problematic: delete the `config_overrides` table row for
thresholds; the system falls back to config-file values on next API start.

---

## 16. Phase 2 Deployment Topology

### 13.1 Service Inventory (Phase 2 Mandatory)

```
LXC Container: photo-ingress
┌────────────────────────────────────────────────────────┐
│                                                        │
│  caddy.service               :443 (LAN-facing)         │
│    ↓ /              → webui/current/ (static files)    │
│    ↓ /api/          → 127.0.0.1:8000 (Uvicorn)         │
│                                                        │
│  nightfall-photo-ingress-api.service   127.0.0.1:8000  │
│    ↓ FastAPI + Uvicorn                                 │
│    ↓ Imports domain modules from nightfall_photo_ingress│
│    ↓ SQLite registry (WAL mode)                        │
│                                                        │
│  nightfall-photo-ingress.timer        (no socket)      │
│  nightfall-photo-ingress-trash.path   (no socket)      │
│    ↓ CLI processes, read/write SQLite registry         │
│                                                        │
│  webui/                                                │
│    releases/                                           │
│      {timestamp}/  ← built artifacts                   │
│    current → releases/{latest}/  ← symlink             │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 13.2 Service Inventory (Phase 2 Optional — Background Worker)

```
│  nightfall-photo-ingress-worker.service   (no socket)  │
│    ↓ Poll sidecar_jobs / thumbnail_jobs tables          │
│    ↓ Executes fetch/generation jobs                    │
│    ↓ SQLite registry (WAL mode, shared)                │
```

### 13.3 Phase 2 Deployment Flow

```
Build machine:
  1. cd webui && npm run build
  2. Tag the build: RELEASE=$(date -u +%Y-%m-%dT%H%M)
  3. Compress: tar -czf photo-ingress-ui-${RELEASE}.tar.gz build/

LXC Container (deploy):
  4. Upload tarball
  5. Expand into: /opt/photo-ingress/webui/releases/${RELEASE}/
  6. Symlink: ln -sfn releases/${RELEASE} current
  7. Perform Caddy config reload (if Caddyfile changed)
  8. Run any pending DB migrations: python -m nightfall_photo_ingress.migrations
  9. Restart nightfall-photo-ingress-api.service if Python code changed
```

Rollback:
```
  10. ln -sfn releases/${PREVIOUS_RELEASE} current
      (no Uvicorn restart, no data change)
```

---

## 17. Phase 2 Component Dependency Graph

The following graph shows build-time and runtime dependencies between components.
Arrows point from dependent to dependency.

```
Phase 2 Deployment Dependencies
────────────────────────────────

[Operator Browser]
      │
      │ HTTPS
      ▼
[Caddy]
  │           │
  │ /          │ /api/
  ▼           ▼
[webui/current/]   [Uvicorn / FastAPI]
(static files)          │
                        │ Python import
                        ▼
              [nightfall_photo_ingress]
               (domain, registry, config)
                        │
                        ▼
                   [SQLite DB]
                   (WAL mode)
                        ▲
                        │ read/write
              [nightfall-photo-ingress]
              [nightfall-photo-ingress-trash]
              [nightfall-photo-ingress-worker] (optional)
```

**Build-time dependencies:**

```
[SvelteKit build]
  depends on → [API OpenAPI schema] (for type generation, optional)
  depends on → [Design tokens] (tokens.css)
  depends on → [node_modules] (Vite, SvelteKit, TypeScript)
  produces  → [webui/build/]  → deployed to [webui/releases/{tag}/]
```

---

## 18. Phase 1 → Phase 2 Compatibility Guarantees

Phase 2 must not break any Phase 1 operator workflow. The following constraints apply:

| Constraint | How maintained |
|-----------|----------------|
| `/api/v1/` endpoints unchanged | No endpoint is removed or renamed in Phase 2 |
| Auth token still works | Static bearer token remains valid in Phase 2; OIDC is additive |
| CLI ingest unaffected | CLI has no dependency on Caddy, Uvicorn, or the web UI |
| SQLite schema stable | Phase 2 migrations are additive only |
| Feature-flag rollback | UI/API can be stopped without affecting CLI ingest timers |
| RapiDoc docs still accessible | `/api/docs` continues to be proxied through Caddy |
| `LoadMoreButton` still usable | `AuditTimeline` infinite scroll is additive; component not removed |
| Filter Sidebar additive | Phase 2 adds sidebar column; no Phase 1 component removed |
| KPI Thresholds GET unchanged | `kpi_thresholds` field in config response was already present in Phase 1 |

Phase 2 is complete when all mandatory items in §2 are operational and the LAN exposure
checklist in §3.6 is signed off.
