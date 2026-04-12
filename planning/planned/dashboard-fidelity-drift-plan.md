# Dashboard Fidelity Drift Analysis and Correction Plan

Status: PLANNED
Created: 2026-04-12
Authoritative mock: design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png
Live reference: staging-photo-ingress (screenshot captured 2026-04-12)

---

## 1. Drift Analysis

### 1.1 Methodology

Compared three sources pixel-for-pixel:

- UI mock (design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png)
- Live staging dashboard (https://staging-photo-ingress, captured 2026-04-12)
- Component source code (webui/src/)

Each drift item is tagged with severity (HIGH / MEDIUM / LOW) and whether it
was reported by the operator or discovered during analysis.

### 1.2 Operator-Reported Findings (Evaluation)

#### Finding 1 — "Loaded Files" tile too large, breaks iPad, rename to "Pending Files"
Verdict: ACCEPTED

Evidence:
- The "Loaded Files" section (webui/src/routes/+page.svelte, dashboard-files
  section) renders an unbounded list of staging items with no max-height or
  overflow-y constraint.
- On an iPad or any viewport under ~900px the section pushes the audit preview
  off-screen.
- The mock does not include a "Loaded Files" section at all; it transitions
  directly from KPI cards to "Audit Timeline." Renaming to "Pending Files" is
  operationally accurate (the data is staging items = pending).
- Severity: HIGH (layout-breaking on tablet).

#### Finding 2 — Filter system must be extended with "account" filter
Verdict: ACCEPTED

Evidence:
- Current filter sidebar (FilterSidebar.svelte) operates only on file
  extension, derived from filenames via filterStore.ts.
- StagingItem schema (api/schemas/staging.py) exposes
  account: str | None = None. The data is available.
- The mock shows conceptual filter categories ("All Files", "Images", "Videos",
  "Documents") — not per-extension buttons.
- An account dimension is operationally useful for multi-source households and
  is supported by the data model.
- Severity: MEDIUM (functional gap, data already available).

#### Finding 3 — Audit entries show "Account unknown" despite registry data
Verdict: ACCEPTED

Evidence:
- AuditEvent.svelte renders event.account_name ?? 'account unavailable'.
- AuditEvent schema (api/schemas/audit.py) has account_name: str | None = None.
- Live screenshot confirms every audit row shows "account unavailable."
- StagingItem has the account field populated. The audit_hook or triage service
  is not propagating account from the staging registry into audit events.
- Severity: HIGH (operator-facing data loss in audit trail).

#### Finding 4 — Audit entries lack client IP/hostname for API events
Verdict: PARTIALLY ACCEPTED — deferred to D4 as optional scope

Evidence:
- AuditEvent schema has no client_ip or hostname field.
- The mock does not show client IP either; this is a purely operational request.
- Adding client IP requires: capture Request.client.host in the audit hook,
  extend the AuditEvent schema, migrate existing data or backfill nulls.
- Severity: LOW (nice-to-have, not a mock drift item).
- Plan: scope as optional within D4; implement only if backend change is low
  risk.

#### Finding 5 — Typography does not match UI mock
Verdict: ACCEPTED

Evidence:
- The mock shows distinctly larger, bolder KPI values and prominent section
  headings compared to the live dashboard.
- Token scale is well-defined (tokens.css: --text-xs through --text-2xl) but
  components under-use it.
- KpiCard.svelte uses --text-xl (24px) for values and --text-sm (13px) for
  labels. Mock suggests --text-2xl (32px) for KPI values.
- H1 on the dashboard uses browser default sizing; mock shows a larger title
  consistent with --text-2xl or above.
- Section headings ("Loaded Files", "Recent Audit Events") use --text-md (17px);
  mock suggests --text-lg (20px) with the teal accent underline.
- Severity: MEDIUM (visual fidelity gap, all tokens already defined).

### 1.3 Additional Drift Discovered

#### D-A: Dashboard title mismatch
- Mock: "Photo-Ingress Dashboard" / Live: "Dashboard"
- Source: webui/src/routes/+page.svelte line 56: <h1>Dashboard</h1>
- Severity: LOW

#### D-B: KPI label mismatches (3 of 5 cards)
- "Pending" vs mock "Pending in Staging"
- "Live Photo Pairs" vs mock "Live Photo Pairs Detected"
- "Last Poll (s)" vs mock "Last Poll Duration"
- Source: webui/src/lib/components/dashboard/KpiGrid.svelte
- Severity: MEDIUM

#### D-C: Health gradient bar missing
- Mock shows a teal-to-amber-to-red gradient bar above the health badges row,
  with "Health Status: OK OK Ready Peak" legend.
- Live has no gradient bar; only four simple dot+label status badges.
- Source: webui/src/lib/components/dashboard/HealthBar.svelte — renders only
  StatusBadge components, no gradient element.
- Severity: MEDIUM

#### D-D: Health badge labels abbreviated
- Mock: "Polling", "OneDrive Auth", "Registry Integrity", "Disk Usage" (with
  descriptive icons: checkmark, cloud, checkmark, checkmark)
- Live: "Polling", "Auth", "Registry", "Disk" (dot only, no icons)
- Source: HealthBar.svelte hardcodes short labels; StatusBadge.svelte renders
  only a dot + text, no icon slot.
- Severity: MEDIUM

#### D-E: Filter sidebar structure mismatch
- Mock: heading "Filters", checkboxes with conceptual categories ("All Files",
  "Images", "Videos", "Documents").
- Live: heading "File Type Filters", button toggles with per-extension labels
  ("JPG" with count).
- Source: FilterSidebar.svelte, filterStore.ts (deriveDashboardFileTypeOptions
  groups by raw extension).
- Severity: MEDIUM

#### D-F: Poll runtime chart — bar sparkline vs line chart
- Mock: "Poll Runtimes (Last 7 Days)" with full SVG/Canvas line chart, Y-axis
  (0s-30s), X-axis (Mon-Sun), area fill under curve.
- Live: single teal bar in a minimal container, no title, no axes.
- Source: PollRuntimeChart.svelte renders <span class="bar"> per value with
  pixel height. Only a single value is passed from +page.svelte (latest
  poll_duration_s).
- Backend gap: /api/v1/health returns only the latest poll_duration_s, not a
  7-day series.
- Severity: HIGH (major visual difference, requires backend + frontend work).

#### D-G: Audit event layout
- Mock: Each row is [status-icon] [bold filename] [colored action label]
  [relative time]. Four distinct icons: green circle (accepted), teal circle
  (duplicate), red X (rejected), trash (deleted).
- Live: Pipe-delimited flat text: description | filename | account | action |
  sha256 | actor | ISO timestamp. No icons, no color coding, no relative time.
- Source: AuditEvent.svelte renders all fields inline with "|" separators.
- Severity: HIGH (major UX difference).

#### D-H: "Loaded Files" section absent from mock
- The mock has no "Loaded Files" / file listing section. It transitions from
  KPI cards + poll chart directly to "Audit Timeline."
- Live dashboard has a prominent "Loaded Files" section between the chart and
  audit events.
- This section may be a development convenience that was never in the design.
- Severity: MEDIUM (addressed in operator finding #1 — constrain and rename).

#### D-I: Audit section heading and accent
- Mock: "Audit Timeline" with a teal left-border accent bar.
- Live: "Recent Audit Events" with "View all" link, no accent bar.
- Source: AuditPreview.svelte header uses plain h2 + anchor.
- Severity: LOW

---

## 2. Correction Plan

Six chunks (D1-D6), ordered by dependency. Each chunk is independently
deliverable and testable. No chunk requires infrastructure changes or E2E
browser tests.

### D1 — Dashboard Chrome and KPI Normalization

Scope:
- Rename dashboard title: "Dashboard" -> "Photo-Ingress Dashboard" (D-A)
- Fix KPI labels in KpiGrid.svelte (D-B):
  - "Pending" -> "Pending in Staging"
  - "Live Photo Pairs" -> "Live Photo Pairs Detected"
  - "Last Poll (s)" -> "Last Poll Duration"
- Rename "Loaded Files" section to "Pending Files" (operator #1)
- Add max-height (320px) and overflow-y: auto to dashboard-files section
  (operator #1)
- Add title attribute to truncated file names for tooltip (operator #1)

Files changed:
- webui/src/routes/+page.svelte
- webui/src/lib/components/dashboard/KpiGrid.svelte

Acceptance criteria:
- H1 reads "Photo-Ingress Dashboard"
- KPI card labels match mock exactly (5/5)
- "Pending Files" section has visible scrollbar when items > ~8
- File name hover shows full name in tooltip
- Existing unit tests pass (govctl run web.test.unit --json)
- TypeScript check passes (govctl run web.typecheck --json)

Validation:
- govctl run web.test.unit --json
- Visual: compare staging screenshot with mock for title + KPI labels

Stop-gate:
- If KpiGrid label changes break any E2E selectors or snapshot tests, halt and
  update test expectations first.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (KPI section)


### D2 — Filter Sidebar Redesign

Scope:
- Rename sidebar heading: "File Type Filters" -> "Filters" (D-E)
- Replace per-extension button toggles with checkbox-based conceptual categories
  matching mock: "All Files", "Images", "Videos", "Documents" (D-E)
- "All Files" acts as select-all/deselect-all toggle
- Refactor filterStore.ts to map conceptual categories to extension sets
  (IMAGE_EXTENSIONS, VIDEO_EXTENSIONS already defined; add DOCUMENT_EXTENSIONS)
- Add "account" filter dimension (operator #2):
  - Derive unique accounts from StagingPage items
  - Add account filter section below file type section
  - Filter client-side by item.account

Files changed:
- webui/src/lib/stores/filterStore.ts
- webui/src/lib/components/dashboard/FilterSidebar.svelte
- webui/src/routes/+page.svelte (wire account filter)

Acceptance criteria:
- Sidebar shows "Filters" heading
- Four checkbox rows: All Files (checked by default), Images, Videos, Documents
- Account filter section appears when multiple accounts exist
- Selecting "Images" filters to IMAGE_EXTENSIONS set; same for Videos, Documents
- "All Files" unchecked clears all; checked selects all
- Existing filterStore unit tests updated or extended
- TypeScript check passes

Validation:
- govctl run web.test.unit --json
- Visual: sidebar matches mock checkboxes

Stop-gate:
- Do not change backend API surface. All filtering remains client-side.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (Filters panel)
- api/schemas/staging.py (StagingItem.account field)


### D3 — Health Bar and Status Badge Overhaul

Scope:
- Add gradient bar to HealthBar: teal (ok) -> amber (warning) -> red (error),
  matching mock (D-C)
- Expand badge labels (D-D):
  - "Auth" -> "OneDrive Auth"
  - "Registry" -> "Registry Integrity"
  - "Disk" -> "Disk Usage"
- Add icon support to StatusBadge:
  - Replace plain dot with icon slot (checkmark-circle for ok, warning-triangle
    for warning, x-circle for error, cloud icon for auth)
  - Use inline SVG icons (no external icon library dependency)
- Add "Health Status:" legend row above gradient bar per mock

Files changed:
- webui/src/lib/components/dashboard/HealthBar.svelte
- webui/src/lib/components/common/StatusBadge.svelte

Acceptance criteria:
- Gradient bar visible above health badges
- Badge labels match mock verbatim
- Each badge shows an appropriate status icon (not just dot)
- Existing health-bar test selectors still work
- TypeScript check passes

Validation:
- govctl run web.test.unit --json
- Visual: compare health section with mock

Stop-gate:
- Keep inline SVG small (<500 bytes per icon). Do not add icon font or external
  sprite sheet.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (Health Status row)
- webui/src/lib/tokens/tokens.css (--status-ok, --status-warning, --status-error)


### D4 — Audit Event Layout and Data Fidelity

Scope:
- Redesign AuditEvent.svelte to match mock layout (D-G):
  - [status-icon] [bold filename] [colored action text] [relative time]
  - Remove pipe-delimited flat text layout
- Add action-to-icon mapping:
  - accepted/triage_accept_applied -> green filled circle
  - duplicate_skipped -> teal hollow circle
  - rejected/triage_reject_applied/triage_reject_requested -> red X circle
  - deleted/sent_to_trash -> trash icon
  - default -> gray circle
- Add action-to-color mapping using existing tokens:
  - accepted -> --action-accept (teal)
  - rejected -> --action-reject (red)
  - duplicate -> --status-info (blue)
  - deleted -> --text-muted
- Add relative time formatting (e.g., "25 mins ago", "2 hrs ago"):
  - Implement lightweight relativeTime() utility, no external dependency
  - Fall back to short ISO if timestamp is older than 7 days
- Fix "account unavailable" (operator #3):
  - Backend: in audit_hook.py, resolve account from staging registry when
    creating audit events. Look up StagingItem by sha256 and copy account into
    account_name.
  - This is a backend data-flow fix, not a schema change.
- Optional — client IP (operator #4):
  - Add client_ip: str | None = None to AuditEvent schema
  - Capture request.client.host in audit_hook.py for API-originated events
  - Display in AuditEvent.svelte only if non-null, as small muted text
  - IF this causes migration complexity, defer to a future chunk
- Rename audit preview heading: "Recent Audit Events" (keep as-is for dashboard
  preview; "Audit Timeline" is for the full /audit page) (D-I)
- Add teal left-border accent to audit preview section (D-I)

Files changed:
- webui/src/lib/components/audit/AuditEvent.svelte
- webui/src/lib/components/dashboard/AuditPreview.svelte
- webui/src/lib/utils/relativeTime.ts (new utility)
- api/audit_hook.py (account resolution)
- api/schemas/audit.py (optional: client_ip field)

Acceptance criteria:
- Each audit row renders: icon + bold filename + colored action + relative time
- No pipe separators remain
- Action colors match token palette
- Relative time shows human-friendly strings for events < 7 days old
- account_name populated for events where staging item accounts exist
- Existing audit E2E test selectors updated if needed
- TypeScript check passes; backend unit tests pass

Validation:
- govctl run web.test.unit --json
- govctl run backend.test.unit --json
- Visual: compare audit section with mock

Stop-gate:
- If backend account resolution requires DB migration, split into separate
  backend-only sub-chunk.
- If client_ip addition touches migration scripts, defer to future chunk.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (Audit Timeline)
- api/schemas/audit.py (AuditEvent)
- api/schemas/staging.py (StagingItem.account)


### D5 — Poll Runtime Chart Upgrade

Scope:
- Replace bar sparkline with SVG line chart matching mock (D-F):
  - Title: "Poll Runtimes (Last 7 Days)"
  - Y-axis: labeled scale (0s to max rounded up)
  - X-axis: day-of-week labels (Mon-Sun)
  - Line with area fill under curve using --action-primary with 15% opacity
  - Dot markers on data points
- Backend: add /api/v1/health/poll-history endpoint returning last 7 days of
  poll durations (array of {day: string, duration_s: number})
- Update +page.svelte load function to fetch poll history
- Pass full 7-value array to PollRuntimeChart

Files changed:
- webui/src/lib/components/dashboard/PollRuntimeChart.svelte
- webui/src/routes/+page.svelte (load function)
- webui/src/routes/+page.ts or +page.server.ts (if server-side load exists)
- api/routers/ (new poll-history endpoint or extend health router)
- api/services/ (poll history data retrieval)

Acceptance criteria:
- Chart renders as SVG line graph, not bars
- Y-axis shows time labels; X-axis shows day abbreviations
- Area fill uses --color-accent-teal-dim
- Chart gracefully handles missing days (zero or interpolated)
- Backend endpoint returns 7-day array
- TypeScript check passes; backend unit tests pass

Validation:
- govctl run web.test.unit --json
- govctl run backend.test.unit --json
- Visual: compare chart with mock

Stop-gate:
- If poll duration history is not stored in the database, this chunk requires
  a data model discussion. Halt and document the gap before implementing.
- Do not add external charting libraries (D3, Chart.js). Use hand-rolled SVG.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (Poll Runtimes chart)
- api/routers/health.py


### D6 — Typography and Visual Polish Pass

Scope:
- Audit all dashboard component font-size usage against token scale and mock
  (operator #5):
  - Dashboard H1: use --text-2xl (32px, weight 700) to match mock
  - KPI card values: consider --text-2xl (32px) instead of current --text-xl
    (24px) to match mock proportions
  - KPI card labels: --text-sm (13px) is acceptable per mock
  - Section headings (h2): use --text-lg (20px, weight 600) with teal
    accent underline per mock pattern
  - Audit event filename: --text-base (15px) bold per mock
  - Audit event action text: --text-sm (13px) colored per action
  - Audit event time: --text-xs (11px) muted
- Add teal accent underline to section headings ("Pending Files", "Recent
  Audit Events") matching the "Audit Timeline" mock accent bar
- Verify all components use token variables, no raw px values
- Verify font-family-base (Inter) is loaded and applied

Files changed:
- webui/src/routes/+page.svelte (H1 style)
- webui/src/lib/components/common/KpiCard.svelte (.value font-size)
- webui/src/lib/components/audit/AuditEvent.svelte (if not done in D4)
- webui/src/lib/components/dashboard/AuditPreview.svelte (heading style)

Acceptance criteria:
- H1 visually matches mock prominence
- KPI value numbers are visually larger than current
- Section headings have consistent teal accent underline
- No raw pixel values in component styles (all tokenized)
- TypeScript check passes

Validation:
- govctl run web.test.unit --json
- Visual side-by-side comparison of live dashboard vs mock at 1440px and 768px

Stop-gate:
- If Inter font is not loaded (CDN or local), add font-face declaration before
  adjusting sizes.

Cross-references:
- design/ui-mocks/Photo-ingress dashboard with KPIs and audit.png (all sections)
- webui/src/lib/tokens/tokens.css (typography scale)

---

## 3. Dependency Order

```
D1 (Chrome & KPIs)
 |
 +---> D2 (Filter Sidebar)      [independent of D1]
 |
 +---> D3 (Health Bar)           [independent of D1, D2]
 |
 +---> D4 (Audit Events)         [independent of D1-D3]
 |         |
 |         +---> D6 (Typography) [depends on D4 for audit styles]
 |
 +---> D5 (Poll Chart)           [independent of D1-D4]
```

D1 through D5 are independent and can be executed in parallel. D6 should run
last as it is a cross-cutting polish pass that may touch files modified by
D1-D5.

Recommended serial order: D1 -> D3 -> D2 -> D4 -> D5 -> D6

---

## 4. Risk Register

| Risk | Mitigation |
|------|------------|
| Poll history data not stored | D5 stop-gate: halt and document data model gap |
| Account resolution requires DB migration | D4 stop-gate: split backend sub-chunk |
| Client IP capture breaks audit schema compatibility | D4: defer client_ip to future if risky |
| Filter redesign breaks existing test selectors | Update test selectors in same chunk |
| SVG chart accessibility | Add aria-label and role="img" to chart SVG |
| Inter font not loaded | D6 stop-gate: verify font loading first |

---

## 5. Scope Exclusions

The following are explicitly out of scope for this correction plan:

- Backend infrastructure changes (DB migrations, new tables)
- E2E browser test additions (deferred to post-correction validation)
- Photo Wheel / Staging page drift (separate analysis if needed)
- Settings / Blocklist page drift (separate analysis if needed)
- Footer state machine changes (already implemented per staging-footer.md)
- Mobile-first responsive redesign (only fix iPad breakage in D1)

---

## 6. Summary Table

| Chunk | Title | Operator Finding | Additional Drift | Severity | Backend |
|-------|-------|-----------------|-----------------|----------|---------|
| D1 | Chrome & KPI Normalization | #1 (Loaded Files) | D-A, D-B, D-H | HIGH | No |
| D2 | Filter Sidebar Redesign | #2 (account filter) | D-E | MEDIUM | No |
| D3 | Health Bar Overhaul | — | D-C, D-D | MEDIUM | No |
| D4 | Audit Event Fidelity | #3 (account), #4 (IP) | D-G, D-I | HIGH | Yes |
| D5 | Poll Runtime Chart | — | D-F | HIGH | Yes |
| D6 | Typography Polish | #5 (typography) | — | MEDIUM | No |
