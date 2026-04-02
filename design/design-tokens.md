# Design Tokens — Web Control Plane

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering

---

## 1. Philosophy

The design token system is the single source of truth for all visual properties in the
Web UI. Tokens are defined as CSS custom properties (`--token-name`) on the `:root`
selector. Svelte components reference tokens only; no raw values appear in component
styles.

**Dark-mode-first:** The entire UI is dark. There is no light mode toggle in Phase 1.
The `color-scheme: dark` meta tag is set in `app.html`.

**Semantic layering:** Tokens are named by their role, not their raw value. Components
use semantic tokens. Semantic tokens reference primitive tokens. This allows the palette
to be updated in one place.

---

## 2. Token File Location

```
webui/src/lib/tokens/
  tokens.css          — All custom property definitions (imported globally)
  README.md           — Token authoring guide (brief)
```

`tokens.css` is imported in `app.html` or the root layout's `<style>` block so all
tokens are available globally without per-component imports.

---

## 3. Primitive Tokens (Palette)

These define the raw colour palette. They are not used directly in components.

### 3.1 Background Palette

| Token                      | Value       | Role |
|----------------------------|-------------|------|
| `--color-bg-900`           | `#0d0f11`   | Deepest background (body, page root) |
| `--color-bg-800`           | `#141618`   | Primary surface (cards, panels) |
| `--color-bg-700`           | `#1c1f23`   | Elevated surface (sidebar, header) |
| `--color-bg-600`           | `#252a30`   | Hover/pressed state on surfaces |
| `--color-bg-overlay`       | `rgba(0,0,0,0.6)` | Modal backdrop |

### 3.2 Content Palette (Text and Icons)

| Token                      | Value       | Role |
|----------------------------|-------------|------|
| `--color-content-100`      | `#f0f2f4`   | Primary text |
| `--color-content-200`      | `#c4c8cc`   | Secondary text |
| `--color-content-300`      | `#878d95`   | Tertiary/muted text |
| `--color-content-400`      | `#4a5058`   | Disabled text |

### 3.3 Accent Palette

| Token                      | Value       | Role |
|----------------------------|-------------|------|
| `--color-accent-teal`      | `#0dccb5`   | Primary interactive accent (links, active nav, accept) |
| `--color-accent-teal-dim`  | `rgba(13,204,181,0.15)` | Teal surface highlight / card border hover |
| `--color-accent-red`       | `#e05555`   | Reject / danger |
| `--color-accent-red-dim`   | `rgba(224,85,85,0.15)`  | Red surface highlight |
| `--color-accent-amber`     | `#f0a030`   | Warning / degraded |
| `--color-accent-amber-dim` | `rgba(240,160,48,0.12)` | Amber surface highlight |
| `--color-accent-green`     | `#3ecf6a`   | Success / healthy |
| `--color-accent-blue`      | `#5299e0`   | Informational / neutral action |

### 3.4 Border Palette

| Token                    | Value       |
|--------------------------|-------------|
| `--color-border-subtle`  | `rgba(255,255,255,0.06)` |
| `--color-border-default` | `rgba(255,255,255,0.12)` |
| `--color-border-strong`  | `rgba(255,255,255,0.22)` |

---

## 4. Semantic Tokens

These are the tokens that components use. Each references a primitive.

### 4.1 Surface Tokens

| Semantic Token              | Maps to Primitive        | Usage |
|-----------------------------|--------------------------|-------|
| `--surface-base`            | `--color-bg-900`         | Page background |
| `--surface-card`            | `--color-bg-800`         | KPI cards, photo cards, panels |
| `--surface-raised`          | `--color-bg-700`         | Header, sidebar, elevated panels |
| `--surface-hover`           | `--color-bg-600`         | Interactive surface hover state |
| `--surface-overlay`         | `--color-bg-overlay`     | Modal and dialog backdrop |

### 4.2 Text Tokens

| Semantic Token           | Maps to Primitive        | Usage |
|--------------------------|--------------------------|-------|
| `--text-primary`         | `--color-content-100`    | Headings, primary body text |
| `--text-secondary`       | `--color-content-200`    | Labels, descriptions |
| `--text-muted`           | `--color-content-300`    | Timestamps, metadata, placeholders |
| `--text-disabled`        | `--color-content-400`    | Disabled controls |

### 4.3 Interactive / Action Tokens

| Semantic Token               | Maps to Primitive          | Usage |
|------------------------------|----------------------------|-------|
| `--action-accept`            | `--color-accent-teal`      | Accept button fill, accept border |
| `--action-accept-surface`    | `--color-accent-teal-dim`  | Accept drop-zone background |
| `--action-reject`            | `--color-accent-red`       | Reject button fill, reject border |
| `--action-reject-surface`    | `--color-accent-red-dim`   | Reject drop-zone background |
| `--action-primary`           | `--color-accent-teal`      | Primary interactive elements |
| `--action-primary-hover`     | `#10e8cc`                  | Primary element hover |
| `--action-destructive`       | `--color-accent-red`       | Destructive actions (delete) |

### 4.4 Status Tokens

| Semantic Token            | Maps to Primitive       | Usage |
|---------------------------|-------------------------|-------|
| `--status-ok`             | `--color-accent-green`  | Healthy status dot |
| `--status-warning`        | `--color-accent-amber`  | Degraded/warning status dot |
| `--status-error`          | `--color-accent-red`    | Error/down status dot |
| `--status-unknown`        | `--color-content-400`   | Unknown/pending status dot |
| `--status-info`           | `--color-accent-blue`   | Informational items |

### 4.5 Border Tokens

| Semantic Token            | Maps to Primitive            | Usage |
|---------------------------|------------------------------|-------|
| `--border-default`        | `--color-border-default`     | Card borders, separator lines |
| `--border-subtle`         | `--color-border-subtle`      | Low-emphasis dividers |
| `--border-strong`         | `--color-border-strong`      | Focused inputs, selected rows |
| `--border-accept`         | `--action-accept`            | Accept card/zone border |
| `--border-reject`         | `--action-reject`            | Reject card/zone border |

---

## 5. Spacing Scale

Spacing tokens use an 8pt baseline grid. Components use only these values for padding,
margin, and gap.

| Token            | Value  | Usage |
|------------------|--------|-------|
| `--space-1`      | `4px`  | Tight inner padding, icon gap |
| `--space-2`      | `8px`  | Small component inner padding |
| `--space-3`      | `12px` | Default label/input gap |
| `--space-4`      | `16px` | Standard card padding |
| `--space-5`      | `24px` | Section padding, component gap |
| `--space-6`      | `32px` | Large section gap |
| `--space-7`      | `48px` | Page-level section separation |
| `--space-8`      | `64px` | Maximum layout spacing |

---

## 6. Typography

### 6.1 Font Stack

```
--font-family-base: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
--font-family-mono: 'JetBrains Mono', ui-monospace, 'Cascadia Code', monospace;
```

Inter is loaded from a local static asset or system fallback. No external CDN font
load.

### 6.2 Type Scale

| Token                  | Size     | Weight | Line Height | Usage |
|------------------------|----------|--------|-------------|-------|
| `--text-xs`            | `11px`   | 400    | 1.5         | Fine print, footnotes |
| `--text-sm`            | `13px`   | 400    | 1.5         | Metadata, timestamps, labels |
| `--text-base`          | `15px`   | 400    | 1.6         | Body text |
| `--text-md`            | `17px`   | 500    | 1.4         | Card subtitles |
| `--text-lg`            | `20px`   | 600    | 1.3         | Section headings |
| `--text-xl`            | `24px`   | 700    | 1.2         | KPI values, page titles |
| `--text-2xl`           | `32px`   | 700    | 1.1         | Large KPI numbers |
| `--text-mono-sm`       | `12px`   | 400    | 1.5         | SHA-256 hashes, config values |
| `--text-mono-base`     | `13px`   | 400    | 1.5         | Code, API responses |

---

## 7. Border Radius

| Token               | Value  | Usage |
|---------------------|--------|-------|
| `--radius-sm`       | `4px`  | Small elements (badges, chips) |
| `--radius-md`       | `8px`  | Cards, buttons |
| `--radius-lg`       | `12px` | Panels, modals |
| `--radius-xl`       | `16px` | Photo cards in wheel |
| `--radius-full`     | `9999px` | Pills, status dots |

---

## 8. Shadow Scale

Shadows use a dark-mode appropriate approach: instead of grey box shadows, they use
dark colour with subtle opacity, plus an accent glow for focused and highlighted states.

| Token                    | Value | Usage |
|--------------------------|-------|-------|
| `--shadow-sm`            | `0 1px 3px rgba(0,0,0,0.4)` | Subtle card lift |
| `--shadow-md`            | `0 4px 16px rgba(0,0,0,0.5)` | Elevated card, dropdown |
| `--shadow-lg`            | `0 8px 32px rgba(0,0,0,0.6)` | Modal, focus card in Photo Wheel |
| `--shadow-accept-glow`   | `0 0 24px rgba(13,204,181,0.25)` | Accept drop zone highlight |
| `--shadow-reject-glow`   | `0 0 24px rgba(224,85,85,0.25)` | Reject drop zone highlight |
| `--shadow-focus-ring`    | `0 0 0 2px var(--action-primary)` | Keyboard focus outline |

---

## 9. Animation Tokens

| Token                     | Value     | Usage |
|---------------------------|-----------|-------|
| `--duration-fast`         | `100ms`   | Micro-interactions (button press) |
| `--duration-default`      | `200ms`   | Hover transitions, fade-in |
| `--duration-slow`         | `350ms`   | Photo Wheel slide transition |
| `--duration-enter`        | `250ms`   | Modal/panel enter |
| `--duration-exit`         | `150ms`   | Modal/panel exit |
| `--easing-default`        | `cubic-bezier(0.2, 0, 0, 1)` | Standard ease-out |
| `--easing-spring`         | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Springy/photo snap |

---

## 10. Z-Index Scale

| Token              | Value | Usage |
|--------------------|-------|-------|
| `--z-base`         | `0`   | Default stacking context |
| `--z-raised`       | `10`  | Cards on hover |
| `--z-dropdown`     | `100` | Dropdowns, tooltips |
| `--z-sticky`       | `200` | Sticky header |
| `--z-overlay`      | `300` | Modal backdrop |
| `--z-modal`        | `400` | Modal panel |
| `--z-toast`        | `500` | Toast notifications |

---

## 11. KPI Card Status Bar

KPI cards display a thin coloured bar along their bottom edge to convey status. The bar
colour is derived from thresholds defined per metric:

| KPI Metric         | Green (`--status-ok`) | Amber (`--status-warning`) | Red (`--status-error`) |
|--------------------|-----------------------|---------------------------|------------------------|
| Pending in Staging | 0–50                  | 51–200                    | > 200 |
| Disk Usage         | < 70%                 | 70–85%                    | > 85% |
| Last Poll Duration | < 10s                 | 10–30s                    | > 30s |

The status bar is a 3px tall `border-bottom` using the appropriate semantic status
token.

---

## 12. Health Bar Gradient

The top health bar (visible in mockup) uses a CSS linear gradient from green to amber
to red, with the overall system health expressed as the position of service status
indicators overlaid at fixed positions along the bar.

```
background: linear-gradient(
  to right,
  var(--status-ok) 0%,
  var(--status-ok) 50%,
  var(--status-warning) 70%,
  var(--status-error) 100%
);
```

The four service status dots (Polling, OneDrive Auth, Registry Integrity, Disk Usage)
are absolutely positioned along this bar at evenly spaced intervals.
