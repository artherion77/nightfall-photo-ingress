# Chunk 3 UI Drift Analysis — Staging Deploy Review

**Status:** Partially resolved — blocking bugs fixed, visual drift remains  
**Date:** 2026-04-03  
**Source:** Visual comparison of live staging preview (`http://192.168.200.184:8000/`)
against UI mockups in `design/ui-mocks/` during Chunk 3 validation.

Tracking issue: #3 (`Follow-up: complete remaining chunk3 UI drift corrections`)
- https://github.com/artherion77/nightfall-photo-ingress/issues/3

---

## 1. Context

The Chunk 3 staging deploy revealed two categories of problem:

1. **Part 1 — Blocking build defect:** `import.meta.env.PUBLIC_API_TOKEN` is compiled
   to the string `"undefined"` in the layout bundle, causing every page's `load()`
   function to receive an HTTP 401 from the API and route to `+error.svelte`. The
   `+error.svelte` component additionally uses the deprecated SvelteKit v1 prop API
   (`export let error`), so the error message is always rendered as "unknown error".
   See §2 for root cause detail. **Fix applied and verified in commit `3a94e06`**.

2. **Part 2 — UI mockup drift:** With the blocking defect set aside, the implemented
   pages differ from the mockups in `design/ui-mocks/` in both visual presentation and
   data completeness. Drift items are catalogued in §3 and §4.

---

## 2. Part 1 — Bug Detail (for record; fixed in commit `3a94e06`)

### Bug A — `import.meta.env.PUBLIC_API_TOKEN` compiles to `undefined`

**Affected files:**
- `webui/src/lib/api/client.ts` (line 13)
- `webui/src/lib/stores/health.svelte.js` (line 19)

**Root cause:** SvelteKit exposes build-time `PUBLIC_*` environment variables through
its own virtual module `$env/static/public`. Vite's native `import.meta.env` mechanism
only statically replaces variables with the `VITE_` prefix (the default `envPrefix`).
Because `vite.config.js` does not customise `envPrefix`, any reference to
`import.meta.env.PUBLIC_API_TOKEN` is left as-is by Vite and evaluates to `undefined`
at runtime.

`client.ts` evaluates the token at module initialisation time, which compiles to the
literal string `"undefined"`. Every `apiFetch()` call therefore sends
`Authorization: Bearer undefined`, which the backend auth middleware rejects with 401.

**Fix:** Replace `import.meta.env.PUBLIC_API_TOKEN` with the SvelteKit-idiomatic
`import { PUBLIC_API_TOKEN } from '$env/static/public'` in both files.

### Bug B — `+error.svelte` uses the SvelteKit v1 prop API

**Affected file:** `webui/src/routes/+error.svelte`

**Root cause:** `export let error` is the SvelteKit v1 pattern. In SvelteKit v2
(installed: `@sveltejs/kit ^2.5.18`), the error state is no longer passed as a prop;
it must be read via `$page.error` from `$app/stores`. The prop is always `undefined`,
so `{error?.message ?? 'Unknown error'}` always renders "unknown error" regardless of
the actual error.

**Fix:** Replace prop binding with `import { page } from '$app/stores'` and render
`{$page.error?.message ?? 'Unknown error'}`.

---

## 3. Part 2 — Dashboard Drift

**Reference mockup:** `design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png`

### 3.1 Items within Chunk 3 scope (visual / text corrections)

These are gaps in the existing Chunk 3 implementation, not new scope:

| ID | Area | Mock shows | Implementation shows | Correction |
|----|------|-----------|---------------------|-----------|
| D-V1 | Page heading | "Photo-Ingress Dashboard" | "Dashboard" | Update `<h1>` text in `+page.svelte` |
| D-V2 | Component order | HealthBar row above KPI grid | HealthBar below KpiGrid | Reorder components in `+page.svelte` |
| D-V3 | HealthBar labels | "Polling", "OneDrive Auth", "Registry Integrity", "Disk Usage" | "Polling", "Auth", "Registry", "Disk" | Update label strings in `HealthBar.svelte` |
| D-V4 | KpiCard borders | Colour-coded bottom border per threshold state (teal/green/red) | No accent border | Add bottom border to `KpiCard.svelte`; drive colour from threshold state |
| D-V5 | AuditPreview heading | "Audit Timeline" in teal accent colour | "Recent Audit Events" (plain) | Rename heading; apply `--text-accent` or `--action-primary` colour |
| D-V6 | Audit event display | Coloured dot icon + action badge (coloured text) | Plain `action` text | Add colour-coded `StatusBadge` per action type; use icon dot |
| D-V7 | Audit event timestamp | Relative time ("25 mins ago", "1 hr ago") | Raw ISO timestamp | Compute relative display string from `ts` field |
| D-V8 | Audit event identifier | Filename (e.g., "IMG_3051.jpg") | SHA-256 prefix (first 12 chars) | See API gap D-A2 below; use filename when available, fall back to sha256 prefix |

### 3.2 API data gaps requiring new backend work

These cannot be fixed in the frontend alone; they require new or extended API endpoints:

| ID | KPI / Field | Current API state | Required | Planned location |
|----|-------------|-------------------|----------|-----------------|
| D-A1 | `accepted_today`, `rejected_today` | Not returned by any current endpoint | New summary counts (derivable from audit log with date filter) | Phase 2 — P2-I (new) |
| D-A2 | `live_photo_pairs` | Not returned by any current endpoint | Requires domain-level count of paired Live Photo items | Phase 2 — P2-I (new) |
| D-A3 | `last_poll_duration_s` | Not returned by any current endpoint (health returns subsystem status, not timing) | Extend health or add new endpoint | Phase 2 — P2-I (new) |
| D-A4 | 7-day poll runtime history | Not returned | New `GET /api/v1/poll-history` endpoint | Phase 2 — P2-J (new) |
| D-A5 | Filename in audit events | `AuditEvent` schema has `sha256` but no `filename` | Extend schema; populate at write time | Phase 2 — P2-K (new) |

### 3.3 Already planned in Phase 2

| ID | Feature | Phase 2 chunk |
|----|---------|--------------|
| D-P1 | Filter Sidebar (All Files / Images / Videos / Documents) | P2-F |

---

## 4. Part 2 — Staging Queue Drift

**Reference mockup:** `design/ui-mocks/Astronaut photo review interface.png`

### 4.1 Items within Chunk 3 scope (visual / layout corrections)

| ID | Area | Mock shows | Implementation shows | Correction |
|----|------|-----------|---------------------|-----------|
| S-V1 | PhotoWheel visual style | 3D coverflow — perspective transform, cards scale and recede by distance from centre | Flat horizontal flex row; CSS blur filter only (`filter: blur()`) | Add CSS 3D `perspective` scene to `.wheel`; drive `transform: translateZ() scale()` per slot |
| S-V2 | Blur/scale algorithm | Each card blurs/scales proportionally to its distance from the active index | Even/odd index logic (`index % 2 === 0`) unrelated to active card position | Replace with `Math.abs(index - activeIndex)` distance calculation in `PhotoWheel.svelte` |
| S-V3 | Blur tokens | `--wheel-blur-near`, `--wheel-blur-far` tokens referenced in Chunk 3 expected output | Tokens not defined in `tokens.css`; hardcoded values fall through to undefined | Define `--wheel-blur-near` and `--wheel-blur-far` in `tokens.css`; use in `PhotoWheel.svelte` |
| S-V4 | PhotoCard thumbnail | Actual image rendered | Grey box with text "IMG" | See API gap S-A1; placeholder acceptable for Phase 1 if thumbnail endpoint is deferred |
| S-V5 | PhotoCard SHA field | Prefixed "SHA-256: E007GAE..." | Raw truncated hash with no prefix | Prepend "SHA-256: " label |
| S-V6 | PhotoCard timestamp | "Captured at 2:15 PM" (locale time) | Raw `first_seen_at` ISO string | Format with `toLocaleTimeString()`: "Captured at HH:MM" |
| S-V7 | ItemMetaPanel | Not present in mock; metadata embedded in card | Separate `<dl>` detail panel below wheel | Not a blocking gap; panel provides extra detail not shown in mock. Keep as-is (additive) |

### 4.2 API data gaps requiring new backend work

| ID | Feature | Current API state | Required | Planned location |
|----|---------|-------------------|----------|-----------------|
| S-A1 | Item thumbnail image | No image URL or endpoint | `GET /api/v1/items/{sha256}/thumbnail` returning image bytes | Phase 2 — P2-L (new) |

### 4.3 Interaction gaps (already planned in Phase 1 Chunk 4)

The following staging interaction items were confirmed present in the Chunk 4 expected
output and acceptance criteria. They are not drift — they are unimplemented Chunk 4
deliverables:

| ID | Feature | Phase 1 chunk |
|----|---------|--------------|
| S-I1 | Large full-width Accept / Reject CTAs below the wheel | Chunk 4 — `TriageControls.svelte` |
| S-I2 | Inline Accept / Reject buttons overlaid on active card | Chunk 4 — `TriageControls.svelte` |
| S-I3 | Carousel left/right navigation (ArrowLeft / ArrowRight) | Chunk 4 — `PhotoWheel.svelte` |
| S-I4 | Keyboard shortcuts A / R / D for triage actions | Chunk 4 — `PhotoWheel.svelte` |

---

## 5. Work Assignment Summary

| ID | Work item | Where to fix | When |
|----|-----------|-------------|------|
| Bug A | `PUBLIC_API_TOKEN` undefined in bundle | `client.ts`, `health.svelte.js` | Done in `3a94e06` |
| Bug B | `+error.svelte` SvelteKit v1 API | `+error.svelte` | Done in `3a94e06` |
| D-V1–D-V8 | Dashboard visual / text corrections | Chunk 3 remaining work | Before Chunk 4 UI half |
| S-V1–S-V3 | PhotoWheel 3D coverflow + blur tokens | Chunk 3 remaining work; `tokens.css` | Before Chunk 4 UI half |
| S-V5–S-V6 | PhotoCard metadata formatting | Chunk 3 remaining work | Before Chunk 4 UI half |
| D-A1–D-A4 | Dashboard summary counts + poll history | Phase 2 — P2-I, P2-J | Phase 2 mandatory |
| D-A5 | Filename field in audit events | Phase 2 — P2-K | Phase 2 mandatory |
| S-A1 | Item thumbnail endpoint | Phase 2 — P2-L | Phase 2 mandatory |
| D-P1 | Filter Sidebar | Phase 2 — P2-F | Phase 2 mandatory (already planned) |
| S-I1–S-I4 | Triage interaction controls | Phase 1 Chunk 4 | Next Phase 1 chunk |

---

## 6. Notes

- All "visual / text corrections" (D-V*, S-V*) are within the defined scope of Chunk 3
  as specified in the Phase 1 roadmap. They represent incomplete rather than
  out-of-scope deliverables.
- The 3D coverflow CSS (S-V1) was not explicitly specified in the Chunk 3 roadmap
  wording, but is clearly implied by the mock and by Chunk 3's expected output
  describing "neighbor cards at ±1: blurred/scaled". Treating it as within Chunk 3 scope.
- `--wheel-blur-near` / `--wheel-blur-far` tokens were marked "reserved for Phase 2"
  in Chunk 2 but listed as in-use in Chunk 3's expected output. The tokens should be
  defined in `tokens.css` as part of completing Chunk 3.
- The `ItemMetaPanel` (S-V7) is an additive element not in the mock. It provides
  useful detail (size, OneDrive ID) that the mock card doesn't show. Keeping it as-is
  is acceptable; it does not contradict the mock.
