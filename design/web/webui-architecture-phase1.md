# SvelteKit Web UI Architecture

Status: Implemented (Chunks 2, 3, and 4)
Date: 2026-04-03
Owner: Systems Engineering
Last Updated: 2026-04-04

---

## 1. Overview

The photo-ingress Web UI is a SvelteKit single-page application (SPA) built with
`@sveltejs/adapter-static`. It is served as pre-built static assets by the FastAPI
backend. There is no server-side rendering (SSR) at runtime — the app is fully
client-side after the initial asset delivery.

**Phase 1 Chunk 4 Status:** Global design system, read-only pages, and staging triage
interaction wiring are implemented. Dashboard, staging, audit timeline, blocklist, and
settings are live; staging now includes accept/reject/defer actions.

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
- Chunk 5 adds blocklist write controls.

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

See `design/web/webui-design-tokens-phase1.md` for the complete token catalogue.

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

SSR remains a viable future upgrade path. See `design/web/web-control-plane-architecture-phase2.md` §7 for the conditions under which SSR adoption is warranted and the migration steps to `@sveltejs/adapter-node`.

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
    +page.svelte           — Blocklist: read-only list in Chunk 3; write controls added in Chunk 5
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
| `/blocklist`| List of blocked rules. Chunk 3 is read-only; toggle, add, edit, and delete controls arrive in Chunk 5. |
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
    BlockRuleList.svelte     — List of block rules; write controls added in Chunk 5

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
| `blocklist.svelte.js` | `{ rules, loading, error }` | Read-only `loadRules()` in Chunk 3; CRUD actions deferred to Chunk 5. |
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

---

## 7. API Layer

**See also:** [web-control-plane-api-phase1.md](web-control-plane-api-phase1.md) for detailed API endpoint specification, response schemas, and authentication reference.

The current backend exposes read models plus triage mutation responses:

- `HealthResponse` with nested `ServiceStatus` objects.
- `StagingPage` with `items`, `cursor`, `has_more`, and `total`.
- `AuditPage` with `events`, `cursor`, and `has_more`.
- `EffectiveConfig` with redacted `api_token` and explicit `kpi_thresholds` keys.
- `BlockRuleList` with `rules` entries using the current backend `rule_type` constraints.
- `TriageResponse` with `action_correlation_id`, `item_id`, and target `state`.

### 7.1 Location and Structure (`src/lib/api/`)

```
api/
  client.ts        — Base fetch wrapper (bearer header, JSON handling, ApiError)
  health.ts        — GET /api/v1/health
  staging.ts       — GET /api/v1/staging, GET /api/v1/items/{id}
  audit.ts         — GET /api/v1/audit-log
  blocklist.ts     — GET /api/v1/blocklist
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
- Destructive-action confirmation dialogs remain deferred to Chunk 5 (blocklist CRUD).
