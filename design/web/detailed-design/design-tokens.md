# Design Tokens — Web Control Plane

Status: Implemented
Date: 2026-04-03
Owner: Systems Engineering
Last Updated: 2026-04-03 (Chunk 2 complete)

---

## 1. Philosophy

The design token system is the single source of truth for all visual properties in the
Web UI. Tokens are defined as CSS custom properties (`--token-name`) in the `:root`
selector, making them available globally to all components. **Components reference
tokens exclusively; no raw colour hex values, pixel sizes, or named CSS values appear
in component `<style>` blocks.**

**Dark-mode-first:** The entire UI is dark. There is no light mode toggle in Phase 1.
The `color-scheme: dark` meta tag is set in `app.html` for native dark-mode browser
support.

**No hardcoded values:** All colour, spacing, typography, radius, shadow, and animation
properties reference CSS custom properties. This ensures:
- Single source of truth: palette updates require only one edit.
- Consistency: all uses of a given property receive the same value.
- Maintainability: new components automatically inherit the design system.

---

## 2. Token File Location and Integration

```
webui/src/styles/
  tokens.css          — All CSS custom properties (root level)
  reset.css           — Global normalization and defaults
```

**Global Import Order** (in `webui/src/routes/+layout.svelte`):

1. First: `import '../styles/reset.css'` — Normalizes default browser styles
2. Second: `import '../styles/tokens.css'` — Defines all design tokens

This ensures tokens are available to reset.css for typography and bg colour defaults,
and to all components globally. No per-component token imports are needed.

---

## 3. Colour Palette

All colour tokens are defined at the root level as CSS custom properties. The palette
is organized by category: background, status, action, surface, text, and border.

### 3.1 Background Colours

| Token                | Value     | Usage |
|----------------------|-----------|-------|
| `--color-bg-950`     | `#0a0e27` | Deepest background (not currently used) |
| `--color-bg-900`     | `#0f1419` | Primary page background |
| `--color-bg-800`     | `#1a1f2e` | Primary surface for cards and panels |
| `--color-bg-700`     | `#252d3d` | Elevated surface (sidebar, header) |

### 3.2 Neutral Colours

| Token                   | Value     | Role |
|-------------------------|-----------|------|
| `--color-neutral-50`    | `#f9fafb` | Very light text (rarely used) |
| `--color-neutral-100`   | `#f3f4f6` | Primary text |
| `--color-neutral-200`   | `#e5e7eb` | Secondary text |
| `--color-neutral-300`   | `#d1d5db` | Tertiary text |
| `--color-neutral-400`   | `#9ca3af` | Muted text and borders |
| `--color-neutral-500`   | `#6b7280` | Disabled state colour |
| `--color-neutral-600`   | `#4b5563` | Strong border |
| `--color-neutral-700`   | `#374151` | Default border |
| `--color-neutral-800`   | `#1f2937` | Subtle border |
| `--color-neutral-900`   | `#111827` | (not currently used) |

### 3.3 Status Colours

| Token                 | Value     | Usage |
|-----------------------|-----------|-------|
| `--status-ok`         | `#10e8cc` | Healthy status indicator (teal) |
| `--status-warning`    | `#fbbf24` | Warning/degraded status (amber) |
| `--status-error`      | `#f87171` | Error/down status (red) |
| `--status-unknown`    | `#6b7280` | Unknown status (grey) |

### 3.4 Action Colours

| Token                      | Value     | Usage |
|----------------------------|-----------|-------|
| `--action-primary`         | `#10e8cc` | Primary interactive elements (teal) |
| `--action-primary-hover`   | `#0dd1b5` | Primary element hover state |
| `--action-accept`          | `#10e8cc` | Accept button and zones |
| `--action-reject`          | `#ef4444` | Reject button and zones |
| `--action-destructive`     | `#ef4444` | Destructive actions (delete) |

### 3.5 Surface Tokens

| Semantic Token       | Value            | Usage |
|---------------------|------------------|-------|
| `--surface-base`    | `#111827`        | Page background |
| `--surface-card`    | `#1a1f2e`        | KPI cards, photo cards, panels |
| `--surface-raised`  | `#252d3d`        | Header, sidebar, elevated panels |
| `--surface-overlay` | `rgba(0, 0, 0, 0.8)` | Modal and dialog backdrop |
| `--surface-code`    | `#0f1419`        | Code block backgrounds |

### 3.6 Text Colours

| Token                | Value       | Usage |
|---------------------|-------------|-------|
| `--text-primary`    | `#f3f4f6`   | Headings, primary body text |
| `--text-secondary`  | `#d1d5db`   | Labels, descriptions |
| `--text-tertiary`   | `#9ca3af`   | Timestamps, metadata, placeholders |
| `--text-code`       | `#86efac`   | Monospace code text |

### 3.7 Border Colours

| Token                 | Value     | Usage |
|-----------------------|-----------|-------|
| `--border-default`    | `#374151` | Standard card borders, separator lines |
| `--border-subtle`     | `#1f2937` | Low-emphasis dividers |
| `--border-strong`     | `#4b5563` | Focused inputs, selected rows |

---

## 4. Primitive Tokens (Palette)

---

## 5. Spacing Scale

Spacing tokens use a consistent baseline grid. Components use only these values for
padding, margin, and gap. No raw pixel values appear in component styles.

| Token      | Value   | Equivalent | Usage |
|------------|---------|------------|-------|
| `--space-1` | `0.25rem` | 4px       | Tight inner padding, icon gap |
| `--space-2` | `0.5rem`  | 8px       | Small component inner padding |
| `--space-3` | `0.75rem` | 12px      | Default label/input gap |
| `--space-4` | `1rem`    | 16px      | Standard card padding |
| `--space-5` | `1.25rem` | 20px      | Component gap, section padding |
| `--space-6` | `1.5rem`  | 24px      | Large section gap |
| `--space-8` | `2rem`    | 32px      | Extra-large section spacing |
| `--space-10` | `2.5rem` | 40px      | Extra-large gap |
| `--space-12` | `3rem`   | 48px      | Large spacing |
| `--space-16` | `4rem`   | 64px      | Maximum layout spacing |

---

## 6. Typography

### 6.1 Font Families

```css
--font-family-base: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
--font-family-mono: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Courier New', monospace;
```

No external font CDN requests. System fonts fall back gracefully.

### 6.2 Type Scale

All typography values are split into three properties per size: `--text-SIZE`,
`--text-SIZE-line-height`, and `--text-SIZE-weight`. Components can reference all
three independently or use them together.

| Size  | `--text-SIZE` | `--text-SIZE-line-height` | `--text-SIZE-weight` | Usage |
|-------|---------------|---------------------------|----------------------|-------|
| `xs`  | `0.75rem` (12px) | `1rem` | `500` | Fine print, small labels |
| `sm`  | `0.875rem` (14px) | `1.25rem` | `500` | Metadata, timestamps, small text |
| `base`| `1rem` (16px) | `1.5rem` | `400` | Body text |
| `md`  | `1rem` (16px) | `1.5rem` | `500` | Card subtitles |
| `lg`  | `1.125rem` (18px) | `1.75rem` | `500` | Section headings |
| `xl`  | `1.25rem` (20px) | `1.75rem` | `600` | KPI values, page titles |
| `2xl` | `1.5rem` (24px) | `2rem` | `700` | Large headings, prominent values |

**Bold weight:**
- `--text-bold-weight: 700` — Applied to headings and emphasized text.

---

## 7. Border Radius

| Token         | Value   | Usage |
|---------------|---------|-------|
| `--radius-sm` | `0.375rem` (6px) | Small elements (badges, chips) |
| `--radius-md` | `0.5rem` (8px)   | Cards, buttons, inputs |
| `--radius-lg` | `0.75rem` (12px) | Panels, modals, larger components |
| `--radius-xl` | `1rem` (16px)    | Large photo cards, hero elements |
| `--radius-full` | `9999px`     | Pills, circular badges, status dots |

---

## 8. Shadow Scale

Shadows are used sparingly in dark mode. They employ dark-on-dark layering rather
than the grey shadows typical in light mode.

Shadows are used sparingly in dark mode. They employ dark-on-dark layering rather
than the grey shadows typical in light mode.

| Token                 | Value | Usage |
|-----------------------|-------|-------|
| `--shadow-sm`         | `0 1px 2px 0 rgba(0, 0, 0, 0.05)` | Subtle card lift |
| `--shadow-md`         | `0 4px 6px -1px rgba(0, 0, 0, 0.1)` | Elevated card, dropdown |
| `--shadow-lg`         | `0 10px 15px -3px rgba(0, 0, 0, 0.1)` | Modal, focus card |
| `--shadow-xl`         | `0 20px 25px -5px rgba(0, 0, 0, 0.1)` | Highest elevation |

---

## 9. Animation & Transition Tokens

Transitions make the UI responsive and polished without being distracting.

### 9.1 Durations

| Token                | Value   | Usage |
|---------------------|---------|-------|
| `--duration-fast`   | `150ms` | Micro-interactions (button press) |
| `--duration-default`| `200ms` | Hover transitions, fade-in |
| `--duration-slow`   | `300ms` | Large element transitions (carousel slide) |

### 9.2 Easing Functions

| Token                | Value | Usage |
|---------------------|-------|-------|
| `--easing-linear`    | `linear` | Constant speed (rare) |
| `--easing-default`   | `cubic-bezier(0.4, 0, 0.2, 1)` | Standard ease-out |
| `--easing-ease-in`   | `cubic-bezier(0.4, 0, 1, 1)` | Entrance animations |
| `--easing-ease-out`  | `cubic-bezier(0, 0, 0.2, 1)` | Exit animations |

**Complete transition example:**
```css
transition: all var(--duration-default) var(--easing-default);
```

---

## 10. KPI Card Status Indicators

KPI cards display a coloured bar along their bottom edge to indicate status. The colour
is determined by comparing the metric value against warning and error thresholds.

**No thresholds are hardcoded in components.** The `GET /api/v1/config/effective`
endpoint returns a `kpi_thresholds` object:

```json
{
  "kpi_thresholds": {
    "pending_in_staging": { "warning": 50, "error": 200 },
    "disk_usage_pct": { "warning": 70, "error": 85 },
    "last_poll_duration_s": { "warning": 10, "error": 30 }
  }
}
```

The `config.svelte.js` store fetches and caches these values. `KpiCard` receives
`thresholds: { warning: number, error: number }` as a prop. Parent pages source
thresholds from the config store.

**Status bar colour logic:**

| Condition | Token Applied |
|-----------|----------------|
| value < warning | `--status-ok` |
| warning ≤ value < error | `--status-warning` |
| value ≥ error | `--status-error` |

---

## 11. Token Usage Rules

All token usage follows these strict rules to maintain design system integrity:

1. **No raw colour values:** Components must NOT use `#rgb`, `hsl()`, or named CSS colours. Use token references only.
2. **No raw pixel sizes:** Components must NOT use hardcoded `px` values for spacing, font, or radius. Use tokens instead.
3. **No inline computed values:** Do not compute colours or sizes in component styles. Use pre-computed tokens.
4. **Accessibility:** Ensure sufficient colour contrast for text (WCAG AA minimum). All tokens meet this requirement.
5. **Dark mode only:** All tokens assume dark mode. No light-mode variants exist in Phase 1.

---

## 12. Token Naming Convention

Tokens follow a consistent naming pattern:

- **Primitives** (rare, not in component styles): `--color-CATEGORY-NAME` (e.g., `--color-neutral-500`)
- **Semantic** (common in components): `--ROLE-PROPERTY` (e.g., `--text-primary`, `--surface-card`, `--status-ok`)
- **Spacing**: `--space-NUMBER` (e.g., `--space-4`)
- **Typography**: `--text-SIZE` + `--text-SIZE-weight` + `--text-SIZE-line-height`
- **Radius**: `--radius-NAME` (e.g., `--radius-md`)
- **Shadows**: `--shadow-NAME` (e.g., `--shadow-lg`)
- **Animation**: `--duration-NAME` or `--easing-NAME`

---

## 13. Photo Wheel Blur Tokens (Phase 2+)

The Photo Wheel carousel will apply progressive blur based on card position. These
tokens are **not implemented in Phase 1** (Phase 1 has no interactive carousel).
They are reserved for Phase 2 when `PhotoWheel.svelte` is built.

**Planned tokens:**

| Token                 | Value | Usage |
|-----------------------|-------|-------|
| `--wheel-blur-center` | `0px` | Center card: fully sharp |
| `--wheel-blur-near`   | `4px` | Adjacent cards (±1): gently blurred |
| `--wheel-blur-far`    | `8px` | Outer cards (±2): strongly blurred |

When implemented, `PhotoCard` will reference these tokens via CSS `var()` instead of
hardcoding pixel values. This ensures blur levels can be adjusted from one location.

---

## 14. Component Compliance Checklist

All components must adhere to these constraints:

- [ ] No raw colour hex values (e.g., `#10e8cc`) — use semantic tokens only
- [ ] No raw pixel values for spacing (e.g., `16px`) — use `--space-N` tokens
- [ ] No raw pixel values for font size — use `--text-SIZE` tokens
- [ ] No raw pixel values for border radius — use `--radius-NAME` tokens
- [ ] No named CSS colours (e.g., `lightgrey`) — use tokens only
- [ ] All transitions reference `--duration-*` and `--easing-*` tokens
- [ ] Focus states use `--action-primary` or `--border-strong`
- [ ] Error states use `--status-error` token

**Compliant components (Phase 1):** ActionButton, KpiCard, AppHeader, AppFooter,
StatusBadge, ErrorBanner, ConfirmDialog, LoadingSkeleton, EmptyState, LoadMoreButton.

---

## 15. Global Reset Stylesheet

The `reset.css` file normalizes browser defaults and establishes a consistent baseline
for all elements:

- Removes default margins and padding from all HTML elements
- Normalizes form elements (input, button, textarea, select) with token-based styling
- Applies focus ring styling using `--action-primary`
- Establishes body background as `--surface-base` and text colour as `--text-primary`
- Provides consistent typography sizing and link styling
- Ensures all interactive elements inherit font and colour from parent

**Import order:** Reset is imported before tokens in the root layout so that both are
available globally. Components and reset.css both reference tokens, ensuring consistency
throughout the application.

---

## 16. Implementation Status

**Phase 1 (Chunk 2) Completion: 2026-04-03**

- ✅ `tokens.css` fully implemented with all colour, spacing, typography, radius, shadow, and animation tokens
- ✅ `reset.css` fully implemented with global normalization and defaults
- ✅ Root layout integration: both stylesheets imported globally
- ✅ `app.html` updated with `color-scheme: dark` meta tag
- ✅ All Phase 1 components (ActionButton, KpiCard, AppHeader, etc.) use tokens exclusively
- ✅ No raw colour, pixel, or typed values in component styles
- ⏳ Photo Wheel blur tokens: deferred to Phase 2 (carousel implementation)

**Next Steps (Phase 2+):** Implement carousel-specific tokens and expanded animation system.
