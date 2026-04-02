# UI Mockup Analysis and Component Mapping

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Source Mockups

Two mockups were analysed:

| Mockup | File |
|--------|------|
| Dashboard with KPIs and Audit | `design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png` |
| Staging Queue (Photo Wheel)   | `design/ui-mocks/Astronaut photo review interface.png` |

---

## 2. Mockup Analysis

### 2.1 Dashboard Mockup

**Header band:**
- Top-left: Page title "Photo-Ingress Dashboard" in large white text.
- Top-right: "Health Status:" label followed by four coloured indicator dots with labels
  (`OK`, `OK`, `Ready`, `Peak`), separated by a horizontal gradient colour bar below
  (green → amber → red). This represents system-wide health decomposed into four
  subsystems.

**Left column — Filters sidebar:**
- Full-height column with "Filters" heading.
- Checkbox list: `All Files` (checked, teal), `Images`, `Videos`, `Documents`.
- This is a filter scoped to the staging queue items and dashboard counts.

**Main content area — top row:**
- "Polling" status row with four inline status badges:
  - `Polling: ✓ OK`
  - `OneDrive Auth` (cloud icon)
  - `Registry Integrity ✓`
  - `Disk Usage ⚠` (amber)
- This row is a summarised system health bar inside the main content area.

**Main content area — KPI grid (2×2 + 1 chart):**
- `Pending in Staging` — large number `28`, green bottom bar.
- `Accepted Today` — large number `159`, teal/green bottom bar.
- `Rejected Today` — large number `34`, red bottom bar.
- `Poll Runtimes (Last 7 Days)` — sparkline line chart, teal line, green fill, x-axis days.
- `Live Photo Pairs Detected` — large number `12`, teal bottom bar.
- `Last Poll Duration` — `22s`, teal bottom bar.

**Main content area — Audit Timeline section:**
- Section heading "Audit Timeline" in teal.
- Scrollable list of events, each on its own row:
  - Teal dot + `IMG_3051.jpg` + `Accepted` (teal) + `25 mins ago`
  - Teal dot + `IMG_7539.jpg` + `Duplicate Skipped` (teal/cyan) + `46 mins ago`
  - Red ✕ dot + `IMG_1032.jpg` + `Rejected` (red) + `1 hr ago`
  - Trash icon + `IMG_8764.jpg` + `Sent to Trash` (grey) + `2 hrs ago`

---

### 2.2 Staging Queue (Photo Wheel) Mockup

**Page title:**
- Top-left: "Staging Queue" in large white text.

**Photo Wheel carousel:**
- 5 visible cards in a horizontal fan/arc. 
- Center card: fully visible, sharp, full size, slightly elevated.
  - Contents: file thumbnail image (astronaut photo), filename `IMG_3051.jpg`,
    SHA-256 hash `E007GAE...` (truncated), capture timestamp `Captured at 2:15 PM`,
    account `user@account.com`.
- Two cards immediately adjacent to center (left and right): smaller, blurred,
  partially overlapping the center card. Reduced opacity.
- Two outer cards (furthest left and right): smaller still, more blurred, more
  transparent.
- The carousel implies depth/perspective scaling.
- To the right of the center card: two small button overlays (`Accept` in teal,
  `Reject` in red). These are quick-action buttons inline with the card.

**Drop zone area (bottom):**
- Two large full-width buttons:
  - Left: teal border, teal icon (hand), teal text "Accept". Dark background fill.
  - Right: red border, red icon (hand), red text "Reject". Dark background fill.
- These serve as drag-and-drop target zones AND as tap/click targets.

---

## 3. Layout Pattern Extraction

### 3.1 Dashboard Layout Pattern

```
┌─────────────────────────────────────────────────────────────┐
│ HEADER BAND: Title (left) + Health Status (right)           │
│ Gradient health bar below title                             │
├──────────┬──────────────────────────────────────────────────┤
│ Filters  │ Polling status row                               │
│ Sidebar  ├──────────┬──────────┬──────────┬────────────────┤
│          │ KPI Card │ KPI Card │ KPI Card │ Poll Chart     │
│ All Files│          │          │          │                │
│ Images   ├──────────┴──────────┴──────────┴────────────────┤
│ Videos   │ KPI Card (wide)     │ KPI Card (wide)           │
│ Documents├─────────────────────────────────────────────────┤
│          │ Audit Timeline heading                          │
│          │ Audit event row                                 │
│          │ Audit event row                                 │
│          │ Audit event row                                 │
│          │ Audit event row                                 │
└──────────┴─────────────────────────────────────────────────┘
```

> **Phase 1 note:** The Filter Sidebar column is **deferred to Phase 2** (C9).
> The Phase 1 Dashboard uses a full-width main content area. The layout diagram above
> reflects the eventual Phase 2 layout for reference.

### 3.2 Staging Queue Layout Pattern

```
┌─────────────────────────────────────────────────────────────┐
│ PAGE TITLE: "Staging Queue"                                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  [Card3]  [Card2]  [CENTER CARD + meta + quick buttons]    │
│                         [Card4]  [Card5]                   │
│                                                            │
├───────────────────────┬────────────────────────────────────┤
│    ACCEPT DROP ZONE   │     REJECT DROP ZONE               │
│  (teal border + icon) │   (red border + icon)             │
└───────────────────────┴────────────────────────────────────┘
```

---

## 4. Component Mapping

### 4.1 Dashboard Page → Components

| UI Element | Svelte Component | Props / Slots |
|------------|-----------------|---------------|
| Page title + health bar | `PageTitle` + `HealthBar` | `title`, `services[]` |
| Polling status row | `HealthBar` (compact variant) | `services[]` (inline) |
| Filter sidebar | `FilterSidebar` *(Phase 2 — deferred; C9)* | `options[]`, `selected`, `onChange` |
| KPI card (count) | `KpiCard` | `label`, `value`, `status`, `trend?` |
| KPI chart card | `PollRuntimeChart` | `data[]`, `labels[]` |
| Audit timeline section | `AuditPreview` (dashboard) or `AuditTimeline` (full view) | `events[]`, `onViewAll` |
| Audit event row | `AuditEvent` | `icon`, `filename`, `action`, `actionColor`, `relativeTime` |

### 4.2 Staging Queue Page → Components

| UI Element | Svelte Component | Props / Slots |
|------------|-----------------|---------------|
| Photo Wheel carousel | `PhotoWheel` | `items[]`, `centerIndex`, `onNavigate` |
| Individual photo card | `PhotoCard` | `item`, `isFocused`, `blurLevel` |
| Item metadata below photo | `ItemMetaPanel` | `filename`, `hash`, `capturedAt`, `account` |
| Quick-action buttons (card overlay) | `TriageControls` (compact) | `onAccept`, `onReject`, `onDefer` |
| Accept drop zone | Part of `TriageControls` (full variant) | `onDrop`, `isHovered` |
| Reject drop zone | Part of `TriageControls` (full variant) | `onDrop`, `isHovered` |

### 4.3 Audit Timeline Page → Components

| UI Element | Svelte Component |
|------------|-----------------|
| Scrollable event list | `AuditTimeline` |
| Individual event row | `AuditEvent` |
| Filter tabs / action type filter | Inline tab bar (no separate component needed) |
| Load-more / pagination | `LoadMoreButton` (shared common component) |

### 4.4 Blocklist Page → Components

| UI Element | Svelte Component |
|------------|-----------------|
| Rule list | `BlockRuleList` |
| Individual rule row | `BlockRuleRow` (rendered inside `BlockRuleList`) |
| Enable/disable toggle | `StatusBadge` + toggle variant |
| Add rule button | `ActionButton` |
| Add/edit rule form | `BlockRuleForm` (in a modal via `ConfirmDialog` slot) |
| Delete confirmation | `ConfirmDialog` |

---

## 5. Reusable Primitives

The following primitive components are used across multiple pages and should be
designed as fully general-purpose:

| Primitive | Used by |
|-----------|---------|
| `KpiCard` | Dashboard (×5), potentially staging summary |
| `StatusBadge` | Header health indicator, audit event icons, blocklist rule status |
| `AuditEvent` | Dashboard preview (5 items), full audit page (paginated) |
| `ActionButton` | Triage controls, blocklist add button, settings |
| `ConfirmDialog` | Blocklist delete, any destructive action |
| `ErrorBanner` | Any page that can fail on data load |
| `LoadingSkeleton` | Any component with async data |
| `EmptyState` | Staging (empty queue), blocklist (no rules), audit (no events) |

---

## 6. Responsive Variants

### 6.1 Desktop (≥ 1024px)

- Full layout as in mockups (Phase 2 final state).
- Filter sidebar visible alongside main content area in Phase 2. In Phase 1, main
  content is full-width (no sidebar column).
- Photo Wheel shows 5 cards (center + 2 on each side).
- KPI grid: 3 columns + chart column.
- Header: all navigation tabs visible as text.

### 6.2 Tablet (768–1023px)

| Element | Change |
|---------|--------|
| Filter sidebar | Collapses to a slide-out drawer triggered by a filter icon button. |
| Photo Wheel | Reduces to 3 cards (center + 1 each side). |
| KPI grid | 2×3 grid instead of 3+1 layout. |
| Header nav | Tab labels shrink to icons with tooltips; logo remains. |
| Drop zones | Remain full-width below wheel. |

### 6.3 Mobile (< 768px)

| Element | Change |
|---------|--------|
| Filter sidebar | Becomes a modal sheet triggered by a button. |
| Photo Wheel | Shows only the center card. No neighbor cards rendered. |
| KPI grid | Single column stack. |
| Header | Collapses to app name + hamburger menu. |
| Drop zones | Stack vertically (one above the other). |
| Quick-action buttons | Remain visible on card overlay. |

**Responsive implementation note:** All breakpoint responses are implemented in CSS
using media queries on token-based grid/flex properties. No JavaScript breakpoint
detection is used in Svelte component logic.

---

## 7. Interaction Logic Specification

### 7.1 Photo Wheel

**Navigation:**
- Mouse wheel scroll: rotate items in wheel. Clockwise → advance to next item.
  Counter-clockwise → back to previous item.
- Arrow keys (`ArrowLeft`, `ArrowRight`): same as mouse wheel.
- Clicking a non-center card: advances or retreats the wheel to bring that card to
  center focus.

**Visual transform rules (per card position relative to center):**

| Position offset | Scale | Opacity | Blur | Z-index |
|----------------|-------|---------|------|-------|
| 0 (center)     | 1.0   | 1.0     | `var(--wheel-blur-center)` | 10 |
| ±1             | 0.78  | 0.7     | `var(--wheel-blur-near)` | 5 |
| ±2             | 0.60  | 0.4     | `var(--wheel-blur-far)` | 2 |

**Transition:** Position shifts use `--duration-slow` (`350ms`) with `--easing-spring`
for the snap-to-center animation.

**Center card metadata:** Appears only on the center card. Hidden on all other cards.
Quick-action buttons (Accept / Reject) appear as an overlay to the right of the center
card, not inside it.

### 7.2 Drag and Drop

Drag source: center card in the Photo Wheel.
Drop targets: Accept zone (left) or Reject zone (right).

**Drag states:**
- Drag start: center card gains slight upward translate and increased `--shadow-lg`.
- Hovering over Accept zone: zone background transitions to `--action-accept-surface`;
  border gains `--shadow-accept-glow`. All transitions use `--duration-default`.
- Hovering over Reject zone: zone background transitions to `--action-reject-surface`;
  border gains `--shadow-reject-glow`.
- Drop on zone: fires the corresponding triage action (accept or reject) with an
  idempotency key. Wheel advances to next item. The triage action is optimistic:
  item is removed from wheel immediately; error restores it with a toast.
- Drop cancelled (drag released outside zones): card snaps back to center position.

**Mobile fallback:** Drag and drop is not the primary interaction on mobile. Action
buttons below the card serve as the primary tap targets. Drag behaviour may be
suppressed on touch devices.

### 7.3 Audit Timeline

**Scrolling (Phase 1):** The audit timeline uses cursor-based pagination with an
explicit `LoadMoreButton`. The first page (default 20 items) loads on mount. The
`LoadMoreButton` is visible below the list if additional pages are available. Clicking
it fetches and appends the next cursor page to the existing list. This is simple,
predictable, and requires no scroll event or IntersectionObserver logic.

**Scrolling (Phase 2):** `LoadMoreButton` is replaced with an IntersectionObserver
sentinel. When the sentinel enters the viewport (within 200px of the bottom of the
list), the next cursor page is fetched and appended automatically. See
`design/web-control-plane-architecture-phase2.md` §14 for the migration plan.

**Event row interaction:** Clicking an event row expands it inline to show the full
audit entry (actor, action, item ID, timestamp, correlation ID). Keyboard: `Enter`
or `Space` on focused row triggers expansion.

**Filter:** An action-type filter above the list (tab strip or dropdown) filters events
by action. Changing the filter resets the cursor and reloads from the first page.

### 7.4 KPI Cards

**Hover interaction:** On hover, a KPI card slightly lifts (`box-shadow` increases,
`translateY(-2px)`). Duration: `--duration-default`.

**Click interaction:** In Phase 1, KPI cards are not clickable navigational elements.
The `Pending in Staging` card may gain a `cursor: pointer` and navigate to `/staging`
in a future iteration. This is not a Phase 1 requirement.

**Chart interaction:** The `Poll Runtimes` chart shows a tooltip with the exact value
when hovering over a data point. Tooltip appears above the hovered point.

### 7.5 Blocklist Rules

**Toggle:** Clicking the enabled/disabled toggle for a rule calls
`PATCH /blocklist/{rule_id}` with `{ enabled: !current }`. Optimistic update;
reverted on error.

**Delete:** Clicking delete opens `ConfirmDialog` with the rule pattern shown for
confirmation. Confirming calls `DELETE /blocklist/{rule_id}`. 

**Add rule:** Opens `BlockRuleForm` in a dialog. Submitting calls `POST /blocklist`.
On success, the rule list is invalidated and reloaded.

---

## 8. Icon System

The UI uses a minimal icon set. Icons are inline SVG components sourced from Lucide
Icons (MIT licence, tree-shakeable). No icon font is used.

Icons used per context:

| Icon | Usage |
|------|-------|
| CheckCircle (teal) | Accepted audit event |
| XCircle (red) | Rejected audit event |
| Copy (cyan) | Duplicate skipped |
| Trash2 | Sent to trash |
| CloudLightning | OneDrive status |
| Database | Registry status |
| HardDrive | Disk usage status |
| Activity | Polling status |
| Hand | Accept / Reject action zones |
| ChevronLeft / ChevronRight | Wheel navigation arrows |
| Plus | Add blocklist rule |
| Pencil | Edit blocklist rule |
| Trash2 | Delete blocklist rule |
| AlertTriangle | Warning states |
| Info | Info states |
| Settings | Settings nav item |
