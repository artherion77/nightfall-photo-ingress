# SvelteKit Web UI Architecture

Status: Implemented (Chunk 2 design system complete)
Date: 2026-04-03
Owner: Systems Engineering
Last Updated: 2026-04-03

---

## 1. Overview

The photo-ingress Web UI is a SvelteKit single-page application (SPA) built with
`@sveltejs/adapter-static`. It is served as pre-built static assets by the FastAPI
backend. There is no server-side rendering (SSR) at runtime — the app is fully
client-side after the initial asset delivery.

**Phase 1 Chunk 2 Status:** Global design tokens and reset stylesheet fully implemented.
All components reference tokens exclusively; no raw colour, pixel, or named CSS values
appear in component styles.

This document describes:
- Design token system and global styling
- Layout system
- Route and page structure
- Component hierarchy
- State management strategy
- API layer design
- Error handling and loading state patterns

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

The root layout's `+layout.js` loads only version metadata (a static value). It does
**not** perform a health API call. Health state is owned entirely by the `health.svelte.js`
store (see §6.1). `+layout.svelte` calls `health.connect()` in `onMount` and
`health.disconnect()` in `onDestroy`. `AppHeader` and `AppFooter` subscribe to the
health store directly. This keeps side-effect lifecycle management out of layout files.

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
  +error.svelte            — Global error boundary

  staging/
    +page.svelte           — Staging Queue: Photo Wheel, accept/reject controls
    +page.js               — Load: paginated staging items

  audit/
    +page.svelte           — Audit Timeline: scrollable event log
    +page.js               — Load: paginated audit events

  blocklist/
    +page.svelte           — Blocklist: rule list, add/edit/delete
    +page.js               — Load: blocklist rules

  settings/
    +page.svelte           — Settings: effective config display (read-only)
    +page.js               — Load: GET /api/v1/config/effective
```

### 4.1 Page Responsibilities

| Route       | Responsibility |
|-------------|----------------|
| `/`         | Dashboard with health status, KPIs (pending/accepted/rejected counts, poll runtime chart), and recent audit events (last 5). |
| `/staging`  | Photo Wheel triage interface. Displays center item with neighbors. Accept, Reject, Defer actions. |
| `/audit`    | Full paginated audit log with cursor-based infinite scroll or pagination. Filter by action type. |
| `/blocklist`| List of blocked rules. Toggle enabled/disabled. Add new rule. Edit pattern/reason. Delete with confirmation. |
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
    FilterSidebar.svelte     — Checkbox filter panel (All Files / Images / Videos / Documents)

  staging/
    PhotoWheel.svelte        — Carousel: center focus, blurred/scaled neighbors
    PhotoCard.svelte         — Individual photo/file card (thumbnail, filename, metadata)
    TriageControls.svelte    — Accept / Reject / Defer buttons and drop zones
    ItemMetaPanel.svelte     — Detail panel: filename, SHA-256, timestamp, account

  audit/
    AuditTimeline.svelte     — Scrollable event list
    AuditEvent.svelte        — Single audit event row (icon, filename, action, time)

  blocklist/
    BlockRuleList.svelte     — List of block rules with toggle/edit/delete controls
    BlockRuleForm.svelte     — Add / edit rule form (pattern, type, reason)

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
| `health.svelte.js` | `{ polling_ok, auth_ok, registry_ok, disk_ok, last_updated }` | Store owns polling lifecycle: exposes `connect()` / `disconnect()`. Polling interval (default 30s) starts on `connect()`, stops on `disconnect()`. `+layout.svelte` calls both. |
| `kpis.svelte.js`   | `{ pending_count, accepted_today, rejected_today, live_photo_pairs, last_poll_duration_s }` | Loaded by dashboard page load; refreshed on interval |
| `stagingQueue.svelte.js` | Current page of staging items, cursor, total, loading flag | Updated by staging page load and triage actions |
| `auditLog.svelte.js` | Current page of audit events, cursor, filter, loading flag | Updated by audit page load and pagination actions |
| `blocklist.svelte.js` | List of block rules, loading flag, last mutation result | Updated by blocklist page load and CRUD actions |
| `toast.svelte.js`  | Array of transient notifications `{ id, message, type, expires }` | Appended by error handler; auto-expired |

### 6.2 Store Design Pattern

Stores use Svelte 5's `$state` rune syntax (via `.svelte.js` files) or the classic
writable store pattern. Each store exposes:

- A readable state object (or derived stores for computed values).
- Action functions that call the API layer and update state.
- An error field for per-store error display.

Stores are not global singletons used by components directly. Pages load data via
`+page.js` load functions and pass it as props. Stores are used for:
- Cross-component state (health indicator visible in header and footer simultaneously).
- Persistent cursor state across paginated views.
- Toast notification queue (global in the layout).

**Health store lifecycle (architectural note):** The `health.svelte.js` store is the
exception to the load-function pattern. Because health data must be available at all
times in both the header and footer regardless of which page is active, it uses a
managed polling lifecycle rather than a page load function. The polling interval and
error backoff are internal to the store. No component or layout file contains
`setInterval` or fetch calls related to health — all of that is encapsulated in the
store module.

### 6.3 Optimistic UI

Optimistic updates are applied only where an idempotency key is supplied with the
request. For triage actions (accept, reject, defer), the staging queue optimistically
removes the triaged item and stores the idempotency key. On server error, the item is
restored and a toast notification appears.

---

## 7. API Layer

**See also:** [web-control-plane-api-phase1.md](web-control-plane-api-phase1.md) for detailed API endpoint specification, response schemas, and authentication reference.

### 7.1 Location and Structure (`src/lib/api/`)

```
api/
  client.ts        — Base fetch wrapper (auth header, error handling, idempotency key)
  health.ts        — GET /health
  staging.ts       — GET /staging, GET /items/{id}
  triage.ts        — POST /triage/{id}/accept|reject|defer
  audit.ts         — GET /audit-log
  blocklist.ts     — GET/POST/PATCH/DELETE /blocklist, /blocklist/{id}
  config.ts        — GET /config/effective
  metadata.ts      — POST /metadata/{id}/sidecar-fetch
```

### 7.2 Base Client (`client.ts`)

The base client wraps `fetch` with the following behaviours:

- Adds `Authorization: Bearer {token}` header on every request. Token is read from a
  module-level constant loaded from a build-time environment variable
  (`PUBLIC_API_TOKEN`) or from a configuration endpoint on first load.
- Adds `X-Idempotency-Key` header on mutating requests. The key is generated as a UUID
  v4 per action, stored in the mutation call site.
- On non-2xx responses, extracts the error body and throws a typed `ApiError` object
  with `{ status, message, correlationId }`.
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

### 7.4 Error Handling Strategy

| Error Source | Handling |
|-------------|---------|
| API 4xx (client error) | Display `ErrorBanner` inline on the relevant component; do not push toast. |
| API 5xx (server error) | Display toast notification; log to console. |
| Network failure (status 0) | Display full-page `<ErrorBanner>` with retry button; also update health store. |
| Auth failure (401) | Display toast "Session token rejected" + link to settings. |
| Rate limit (429) | Display toast "Too many requests"; back off 5s before retry is allowed. |
| Duplicate idempotency key (200 replay) | Accept silently; apply prior response result. |

---

## 8. SvelteKit Configuration Points

### 8.1 `svelte.config.js`

- Adapter: `@sveltejs/adapter-static` with `fallback: '200.html'` (SPA fallback).
- No SSR: `ssr: false` in root `+layout.js` via `export const ssr = false`.
- Paths: no base path prefix (served at `/`).

### 8.2 `vite.config.js`

- Dev proxy: `/api` → `http://localhost:8000/api` for local development.
- No special asset handling beyond defaults (Svelte/Vite handles CSS and image imports).

### 8.3 `app.html`

- Sets `<meta charset="utf-8">` and `<meta name="viewport">`.
- Loads inter or system font stack via CSS.
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

## 10. Accessibility Baseline

- All interactive controls have `aria-label` attributes.
- Photo Wheel supports keyboard navigation: `ArrowLeft` / `ArrowRight` to shift focus;
  `A` / `R` / `D` as keyboard shortcuts for Accept / Reject / Defer.
- Color is never the sole indicator of status — icon + color is used throughout.
- Destructive actions require a confirmation dialog before execution.
- Focus is returned to the triggering element after a modal dialog closes.
