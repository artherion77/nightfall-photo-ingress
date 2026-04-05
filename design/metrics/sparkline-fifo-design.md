# Sparkline FIFO Design — LOC Trend + Coverage Trend

**Status:** Design / Pre-implementation  
**Applies to:** `nightfall-photo-ingress` metrics pipeline  
**Scope of change:** `dashboard_generator.py`, `+page.svelte`, `.gitignore`  
**Companion PR:** single controlled PR covering both sparklines

---

## 0. Executive Summary

This document specifies the design for two related dashboard enhancements:

**Part A — Python Test Coverage sparkline: refactor to commit-based FIFO.**  
The existing coverage sparkline is rebuilt from the full history directory on every dashboard
generation call. This is O(n) in the number of retained history runs, is sensitive to the
`max_history_runs` retention policy, and has a latent rendering direction bug (time flows
right-to-left). Replacing it with a small commit-keyed FIFO state file eliminates all three
problems while preserving identical visual semantics.

**Part B — Total LOC sparkline: new, using a day-based FIFO.**  
LOC is a repository volume metric with no natural per-commit unit; daily sampling is the
correct granularity. A new day-keyed FIFO state file drives a new sparkline in the existing
LOC card. This sparkline is net-new — no existing output is removed.

Both FIFOs share the same design principle and implementation pattern, making them consistent
to reason about, test, and maintain.

---

## 1. Rationale for Coverage FIFO Refactor

### 1.1 Problems with the current implementation

The current coverage trend is computed in `_dashboard_payload()` via
`_history_trend(repo_root, current_run_id, limit=6)`:

```python
# Current approach (dashboard_generator.py, ~line 507)
measured_trend = [item["coverage_percent"] for item in trends
                  if item.get("coverage_percent") is not None]
if coverage_percent is not None:
    measured_trend.append(coverage_percent)
if len(measured_trend) < 2:
    trend_series = [0.0, 0.0]
    coverage_trend_source = "fallback_flat"
else:
    trend_series = measured_trend[-7:]
    coverage_trend_source = "measured_history"
"sparklinePoints": _sparkline(list(reversed(trend_series)) if len(trend_series) > 1 else ...)
```

`_history_trend()` iterates every directory under `artifacts/metrics/history/`, reads three
JSON files per directory (summary, manifest, metrics), and sorts the results. At the default
`max_history_runs = 120` retention limit, this is up to 360 file reads per dashboard
generation call. Dashboard generation is called from both `run_now()` and `publish_metrics()`.

**Problem 1 — O(n) disk I/O.** The scan grows with retention. At 120 retained runs and two
calls per commit (run + publish), this becomes 720 file reads per commit processed.

**Problem 2 — Retention sensitivity.** When `apply_retention_policy()` prunes old history
runs, the sparkline may shorten. If history is cleared (e.g., `cleanup_runtime_artifacts
--include-history`), the sparkline resets to the flat-line fallback even though the trend data
existed. The sparkline is not durable across cleanup operations.

**Problem 3 — Rendering direction bug.** The `_history_trend()` function sorts trend items
descending by `generated_at`, so `trends[0]` is the most-recent history run and `trends[-1]`
is the oldest. After `measured_trend.append(current)`, the list is
`[newest-history, ..., oldest-history, current]`. The `list(reversed(...))` call produces
`[current, oldest-history, ..., newest-history]`. The resulting `_sparkline()` call maps index
0 (leftmost) to the *current* run, meaning time flows right-to-left on screen. When coverage
is constant this is invisible; with any slope it would be non-intuitive.

**Problem 4 — Coupling to `_history_trend()`.** The `_history_trend()` function reads
`metrics.json` from each history directory solely to extract `coverage_percent` for the
sparkline. The `trendRows` payload key (which also uses `_history_trend()`) only needs
`run_id`, `severity`, `warning_checks`, `failed_checks`, `delta_items`, `generated_at` — it
never uses `coverage_percent`. Removing the coverage extraction would clean up
`_history_trend()` without affecting `trendRows`.

### 1.2 Why commit-based granularity is correct for coverage

Coverage is a codebase quality metric scoped to a revision: running the same commit twice
always produces the same coverage percentage (given a deterministic test suite). One slot per
unique commit is the natural unit. A day-based FIFO would conflate multiple commits into one
slot, losing granularity during high-commit days and duplicating unchanged data across quiet
periods.

### 1.3 Feasibility verdict

**Accepted.** A commit-keyed FIFO eliminates all four problems above with minimal implementation
surface: one new helper function, one new state file, no schema-breaking changes.

---

## 2. Part A — Coverage Sparkline: Commit-Based FIFO

### 2.1 New state file: `metrics/state/coverage_trend.json`

Location: `metrics/state/coverage_trend.json`  
Tracked on `main`: **No** — requires a new `.gitignore` entry (see §6.1).

**Schema:**
```json
{
  "schema_version": 1,
  "max_slots": 10,
  "slots": [
    {
      "commit_sha": "aa54c50e...",
      "coverage_percent": 80.12,
      "run_id": "module6-20260404T...",
      "measured_at": "2026-04-04T10:00:00+00:00"
    }
  ],
  "updated_at": "2026-04-06T10:12:00+00:00"
}
```

- `commit_sha`: full 40-character SHA from `summary["source"]["commit_sha"]`.
- `coverage_percent`: nullable float (`null` when the coverage tool was unavailable for that commit).
- `run_id`: the run ID that produced this observation (for diagnostics only; not used for
  sparkline rendering).
- `measured_at`: ISO timestamp of the run that wrote this slot.
- Slots are ordered **oldest-first**. `slots[-1]` is always the most recent commit processed.
- `max_slots = 10`. Constant `_MAX_COVERAGE_TREND_SLOTS = 10` in `dashboard_generator.py`.

### 2.2 FIFO update rule — `_update_coverage_trend()`

Called from `_dashboard_payload()` after `coverage_percent` and `commit_full` are computed.

```
Input:  repo_root, commit_full (40-char SHA), coverage_percent (float | None),
        run_id (str), max_slots (int = 10)
Output: updated slots list
```

1. Read `coverage_trend.json` (or initialize `{"slots": [], "max_slots": 10}` on missing/corrupt).
2. If `slots` is non-empty and `slots[-1]["commit_sha"] == commit_full`:
   - Overwrite `slots[-1]` in-place (same-commit update — run + publish on same commit is safe).
3. Else:
   - Append `{"commit_sha": commit_full, "coverage_percent": coverage_percent,
     "run_id": run_id, "measured_at": _as_utc_now()}`.
   - If `len(slots) > max_slots`: pop `slots[0]`.
4. Write back `coverage_trend.json` with `updated_at = _as_utc_now()`.
5. Return the updated slots list.

### 2.3 Sparkline series derivation

After `_update_coverage_trend()` returns slots:

```python
# Filter null slots — don't plot points where tool was unavailable
cov_series = [float(s["coverage_percent"]) for s in slots
              if s["coverage_percent"] is not None]
if len(cov_series) < 2:
    sparkline_points = _sparkline([0.0, 0.0])
    coverage_trend_source = "fallback_flat"
else:
    sparkline_points = _sparkline(cov_series)   # oldest-first → left-to-right time
    coverage_trend_source = "measured_history"
```

**Direction correction:** Slots are oldest-first, so `cov_series[0]` is the oldest commit and
`cov_series[-1]` is the most recent. `_sparkline()` maps index 0 to x=0 (leftmost). Time now
flows left-to-right. The `list(reversed(...))` wrapping present in the current code is
**removed**. This is a deliberate correction, not a side-effect.

### 2.4 Changes to `_history_trend()`

Remove the metrics.json read and the `coverage_percent` extraction. The function reads only
`summary.json` and `manifest.json` (the metrics.json read was solely for coverage). This
reduces the per-call I/O of `_history_trend()` from 3 files/run to 2 files/run.

```python
# Lines to remove from _history_trend():
metrics_path = run_dir / "metrics.json"
if not ... or not metrics_path.exists():    ...
metrics = _read_json(metrics_path)
modules = metrics.get("modules", {})
...
coverage_percent = float(cov_value) if isinstance(cov_value, (int, float)) else None

# And remove from the appended dict:
"coverage_percent": coverage_percent,
```

The `trends` list passed to `_dashboard_payload()` no longer carries `coverage_percent`. The
two lines that read from it (`measured_trend = [...]`) are replaced by the FIFO approach.

### 2.5 Migration seeding

On the very first run after this change, `coverage_trend.json` does not exist. The empty-init
path appends one slot (the current run) and produces the flat-line fallback.

**Optional migration seeding** (recommended, but not mandatory):  
Before the first post-PR run, a one-time migration path in `_update_coverage_trend()` can
detect that the state file is absent and seed the FIFO from existing history:

1. Check if `coverage_trend.json` is absent.
2. If absent: scan `artifacts/metrics/history/` for distinct commits with non-null coverage
   (the same logic that `_history_trend()` currently uses, run once).
3. Sort ascending by `measured_at` / `finished_at`. Deduplicate by commit SHA (keep latest run
   per commit). Take the most recent `max_slots - 1` entries.
4. Build the initial slots list from these, then append the current run's slot as normal.
5. Write `coverage_trend.json`.

This migration is safe: it only runs once (when the file is absent), and it produces at most
`max_slots` entries. On existing installations, 16 distinct commits with coverage are available
in history (all at 80.12%), yielding a full 10-slot buffer from day one. On a clean clone
(no history), the migration path finds no entries and the file starts with 1 slot.

**Risk:** If history was pruned before the upgrade (e.g., `cleanup_runtime_artifacts
--include-history` was run), the seed produces fewer slots. This is safe — the fallback flat
line is used until enough entropy accumulates.

---

## 3. Part B — LOC Sparkline: Day-Based FIFO

### 3.1 Context

`locTotal` in the dashboard payload is computed in `_dashboard_payload()` from three sources:
`backend_loc.per_file`, `frontend_loc.per_file`, and `_collect_extra_loc()`. This computed
total is **not stored in `artifacts/metrics/history/`**, so the pattern of scanning history
files (used today for coverage) cannot be applied even if we wanted to. A dedicated state file
is the only correct approach.

### 3.2 Why day-based granularity is correct for LOC

LOC is a repository volume metric. Multiple commits on the same day may each represent small
incremental changes that together form a meaningful trend. The daily sampling rate is
appropriate for visualizing code volume growth over the natural unit of developer time (a
working day). Using commit-based granularity would produce a noisy, irregular sparkline on
high-commit days and a stale sparkline during low-commit periods.

### 3.3 New state file: `metrics/state/loc_trend.json`

Location: `metrics/state/loc_trend.json`  
Tracked on `main`: **No** — requires a new `.gitignore` entry (see §6.1).

**Schema:**
```json
{
  "schema_version": 1,
  "max_slots": 10,
  "slots": [
    { "date_utc": "2026-03-28", "loc_total": 36100 },
    { "date_utc": "2026-04-06", "loc_total": 37181 }
  ],
  "updated_at": "2026-04-06T10:12:00+00:00"
}
```

- `date_utc`: `YYYY-MM-DD` from `datetime.now(timezone.utc).date().isoformat()` at generation time.
- `loc_total`: raw integer from `_loc_detail["total"]`. **Not** the formatted string `"37.2k"`.
- Slots are ordered oldest-first.
- `max_slots = 10`. Constant `_MAX_LOC_TREND_SLOTS = 10`.

### 3.4 FIFO update rule — `_update_loc_trend()`

Called from `_dashboard_payload()` after `_loc_detail` is assembled.

```
Input:  repo_root, loc_total (int), max_slots (int = 10)
Output: updated slots list
```

1. Read `loc_trend.json` (or initialize `{"slots": [], "max_slots": 10}` on missing/corrupt).
2. Compute `today = datetime.now(timezone.utc).date().isoformat()`.
3. If `slots` is non-empty and `slots[-1]["date_utc"] == today`:
   - Overwrite `slots[-1]["loc_total"] = loc_total`.
4. Else:
   - Append `{"date_utc": today, "loc_total": loc_total}`.
   - If `len(slots) > max_slots`: pop `slots[0]`.
5. Write back `loc_trend.json` with `updated_at = _as_utc_now()`.
6. Return the updated slots list.

### 3.5 Day boundary

Always UTC. `datetime.now(timezone.utc).date()` is evaluated at generation time, not run-start
time. If a run starts at 23:59 UTC and `_dashboard_payload()` is called at 00:01 UTC, the slot
date is the next day. This is correct and expected.

### 3.6 Sparkline series derivation

```python
loc_trend_slots = _update_loc_trend(repo_root, _loc_total)
loc_series = [float(slot["loc_total"]) for slot in loc_trend_slots]
if len(loc_series) < 2:
    loc_sparkline_points = _sparkline([0.0, 0.0])
    loc_trend_source = "fallback_flat"
else:
    loc_sparkline_points = _sparkline(loc_series)  # oldest-first → left-to-right time
    loc_trend_source = "measured_history"
```

Two new keys in the payload dict: `"locSparklinePoints"` and `"locTrendSource"`.

### 3.7 Migration

No historical LOC data exists to seed from (LOC is not stored in history directories). The
trend starts from the first post-PR run. The flat-line fallback renders without error until 2+
days of data accumulate. No user-visible breakage.

---

## 4. UI Changes (`+page.svelte`)

### 4.1 `defaultData` additions

```js
locSparklinePoints: '0,36 180,36',
locTrendSource: 'fallback_flat',
```

The existing `sparklinePoints` default remains for the coverage sparkline. No change needed
for coverage defaults since the payload key is unchanged.

### 4.2 Coverage sparkline

The coverage sparkline renders from `data.sparklinePoints` — this payload key name is
**preserved unchanged**. No change to the `<polyline>` element, no change to the `<h2>` label
or tooltip. The rendering direction fix is transparent to the UI.

### 4.3 LOC sparkline (new)

Added inside the existing "Total Lines of Code" `<article class="card metric-card">` element,
after the `hero-value` div:

```html
<svg viewBox="0 0 180 42" aria-label="LOC trend sparkline" class="sparkline">
  <polyline points={data.locSparklinePoints} fill="none" stroke="#5bb8f5"
            stroke-width="2.5" stroke-linecap="round" />
</svg>
```

**Stroke color `#5bb8f5` (blue)** — distinct from coverage's `#9bf77a` (green). No new CSS
class, no new card, no grid layout changes. The `.sparkline` class already applies sizing via
existing stylesheet rules.

### 4.4 Style consistency table

| Attribute       | Coverage sparkline     | LOC sparkline          |
|-----------------|------------------------|------------------------|
| `viewBox`       | `0 0 180 42`           | `0 0 180 42`           |
| `class`         | `sparkline`            | `sparkline`            |
| `stroke`        | `#9bf77a` (green)      | `#5bb8f5` (blue)       |
| `stroke-width`  | `2.5`                  | `2.5`                  |
| `fill`          | `none`                 | `none`                 |
| Points function | `_sparkline()`         | `_sparkline()`         |
| Key in payload  | `sparklinePoints`      | `locSparklinePoints`   |
| Trend direction | left=oldest (fixed)    | left=oldest            |
| Fallback        | `0,36 180,36` (flat)   | `0,36 180,36` (flat)   |

---

## 5. Drift and Side-Effect Analysis

### 5.1 Coverage FIFO — O(n) I/O elimination

After the refactor, `_history_trend()` no longer reads `metrics.json` for any history run.
It reads only `summary.json` and `manifest.json`. The coverage FIFO reads exactly one small
JSON file (`coverage_trend.json`) and writes it back. Per dashboard generation: coverage trend
drops from O(n × 3) disk reads to O(1) reads + 1 write.

### 5.2 Coverage rendering direction fix

The existing code produces a left-to-right decreasing series when coverage increases over time
(bug). The FIFO approach produces a left-to-right increasing series when coverage increases
(correct). This is a visually observable change on any installation where coverage is not flat.
On this installation all recent commits show identical coverage (80.12%), so the visual
difference will not be observable until coverage changes.

This is a **deliberate improvement**, not a risk. The correct behavior (time flows left to
right on a sparkline) aligns with universal data visualization convention.

### 5.3 `sparklinePoints` key name preserved

The payload key for the coverage sparkline is `"sparklinePoints"` both before and after this
change. The `defaultData.sparklinePoints` in `+page.svelte` is untouched. The `<polyline>`
element is untouched. No dashboard rebuild is triggered by this rename since there is no
rename.

### 5.4 Static dashboard churn

Neither `coverage_trend.json` nor `loc_trend.json` is embedded in the compiled static output.
Both are only read at `_dashboard_payload()` time to populate `__data.json`. `__data.json` is
already written fresh on every run/publish. The addition of `locSparklinePoints` and
`locTrendSource` to `__data.json` does not change the compiled JS/CSS/HTML.

Changing `+page.svelte` (adding the LOC sparkline element) **does** change the source
fingerprint, triggering exactly one `dashboard_sync_mode: sync_local` publish, after which all
subsequent unchanged-source publishes revert to `reuse_published`. This is the correct and
expected behavior.

### 5.5 `skipped_unchanged` runs

`run_now()` returns `skipped_unchanged` without calling `run_dashboard_generation()` when the
commit hasn't changed. Neither FIFO file is mutated. The published dashboard is unaffected.

### 5.6 Same-commit republish safety

`publish_metrics()` calls `run_dashboard_generation()` unconditionally (to regenerate `__data.json`
for freshness). For the coverage FIFO:

- `slots[-1]["commit_sha"] == current_commit` → same-slot overwrite with identical data. Idempotent.

For the LOC FIFO:

- If publish happens on the same UTC day as the run: `slots[-1]["date_utc"] == today` → same-slot
  overwrite with the same `loc_total`. Idempotent.
- If publish happens on the next UTC day (e.g., run at 23:59, publish at 00:01): a new slot is
  appended with the same LOC value. This is correct — the codebase didn't change, but the daily
  snapshot records the measurement. No visual artifact; the sparkline adds a duplicate data point
  that is indistinguishable from the previous day's value.

### 5.7 `coverage_percent: null` slots in coverage FIFO

If coverage is unavailable for a given commit (tool not installed, partial run), the slot is
written with `coverage_percent: null`. The slot occupies a FIFO position but is excluded from
the sparkline series. This preserves the commit record in the trend history (useful for
diagnostics) while keeping the visual sparkline clean. This matches the existing behavior
(`measured_trend = [...for item in trends if item.get("coverage_percent") is not None]`).

### 5.8 `cleanup_runtime_artifacts()` interaction

`cleanup_runtime_artifacts()` removes `metrics/output/` and (optionally) `artifacts/metrics/history/`.
It does **not** touch `metrics/state/`. Both trend files survive all cleanup invocations,
including `--include-history`. This is a durability improvement over the current coverage
sparkline, which would reset to flat-line fallback if history was cleared.

### 5.9 `.gitignore` gap (risk)

`metrics/state/runtime.json`, `extensions.json`, `failure_taxonomy.json`, and `log_policy.json`
are **currently tracked by git** (they are installed configuration, not ephemeral state). The
four ephemeral state files are individually gitignored. `loc_trend.json` and
`coverage_trend.json` are runtime state and must **not** be tracked on `main`. They will appear
as untracked files until explicitly gitignored. This is a mandatory gitignore addition (see §6.1).

### 5.10 `_validate_dashboard_payload_contract()` — no required key additions

`locSparklinePoints` and `locTrendSource` are treated as optional payload extensions. They are
**not** added to the required-key list in `_validate_dashboard_payload_contract()`. Old
dashboards ignore unknown keys gracefully. If enforcement is desired, a follow-up PR can add
them — but it is premature for this PR since the LOC sparkline is brand new and may be
extended in a subsequent iteration.

---

## 6. Implementation Checklist

### 6.1 `.gitignore` additions (mandatory, blocker)

```
metrics/state/loc_trend.json
metrics/state/coverage_trend.json
```

These must land in the same commit as the new code. Failure to add these will cause both
files to appear as untracked changes after the first post-PR run and risk accidental `git add .`.

### 6.2 `dashboard_generator.py`

- [ ] Add constants: `_MAX_COVERAGE_TREND_SLOTS = 10`, `_MAX_LOC_TREND_SLOTS = 10`
- [ ] Add helpers: `_coverage_trend_path(repo_root)`, `_loc_trend_path(repo_root)`
- [ ] Add `_update_coverage_trend(repo_root, commit_full, coverage_percent, run_id, max_slots)` with optional migration seeding from history
- [ ] Add `_update_loc_trend(repo_root, loc_total, max_slots)` 
- [ ] `_history_trend()`: remove `metrics_path` read, remove `coverage_percent` extraction, remove `coverage_percent` from returned dict
- [ ] `_dashboard_payload()`: replace `measured_trend` / `trend_series` logic with `_update_coverage_trend()` call; add `_update_loc_trend()` call; remove `list(reversed(...))` wrapping; add `locSparklinePoints` + `locTrendSource` to returned dict
- [ ] Verify `trendRows` in payload still works (does not reference `coverage_percent` from trend items — confirmed already)

### 6.3 `+page.svelte`

- [ ] Add `locSparklinePoints: '0,36 180,36'` and `locTrendSource: 'fallback_flat'` to `defaultData`
- [ ] Add LOC sparkline `<svg>` element to the "Total Lines of Code" card (stroke `#5bb8f5`)
- [ ] No changes to the coverage sparkline element

### 6.4 Tests (see §7 for full test plan)

- [ ] `test_metrics_module5_dashboard.py`: 10 new tests
- [ ] `test_metrics_module6_poller.py`: 1 new test
- [ ] `test_metrics_module7_publication.py`: 2 new tests

### 6.5 Verification cycle

- [ ] Run full test suite (`pytest tests/unit/ -q`)
- [ ] `./dev/bin/build-metrics-dashboard` (required — `+page.svelte` changed)
- [ ] `./dev/bin/metrics-runner run`
- [ ] `./dev/bin/metrics-runner publish-github`
- [ ] Verify published `__data.json` contains `locSparklinePoints`, `locTrendSource`, and that `sparklinePoints` is still present
- [ ] Verify `metrics/state/loc_trend.json` and `coverage_trend.json` are created and NOT staged by `git status`

---

## 7. Test Plan

All tests in `tests/unit/`.

### 7.1 `test_metrics_module5_dashboard.py` — FIFO unit tests

| Test | Scope | Key assertions |
|------|-------|----------------|
| `test_coverage_trend_creates_on_first_run` | `_update_coverage_trend` | File created; 1 slot; `sparklinePoints` is flat fallback in payload |
| `test_coverage_trend_same_commit_overwrites` | `_update_coverage_trend` | Seed with 1 slot for commit A; call again with commit A and different coverage; slot count stays 1; value updated |
| `test_coverage_trend_new_commit_appends` | `_update_coverage_trend` | Seed with 1 slot for commit A; call with commit B; slot count becomes 2 |
| `test_coverage_trend_fifo_evicts_oldest` | `_update_coverage_trend` | Seed with `max_slots=3` full slots; add 4th commit; slot count stays 3; oldest commit SHA not present |
| `test_coverage_trend_null_slots_excluded_from_series` | `_update_coverage_trend` + sparkline | Seed with slots where some have `null` coverage; verify those are excluded from `cov_series` used in `_sparkline()` |
| `test_coverage_trend_direction_oldest_first` | payload | Seed FIFO with ascending coverage values [70.0, 75.0, 80.0]; verify `sparklinePoints` encodes monotonically decreasing y-coordinates (lower y = higher value in SVG space) from left to right |
| `test_loc_trend_creates_on_first_run` | `_update_loc_trend` | File created; 1 slot; `locSparklinePoints` is flat fallback |
| `test_loc_trend_same_day_overwrites` | `_update_loc_trend` | Seed with 1 slot today; call with different `loc_total`; slot count stays 1; value updated |
| `test_loc_trend_new_day_appends` | `_update_loc_trend` | Seed with 1 slot yesterday; call for today; slot count becomes 2 |
| `test_loc_trend_fifo_evicts_oldest` | `_update_loc_trend` | Seed with `max_slots=3` full slots; add 4th day; slot count stays 3; oldest date not present |
| `test_loc_trend_integer_not_formatted_string` | `_update_loc_trend` | Verify `loc_total` in each slot is an `int`, not a formatted string like `"37.2k"` |
| `test_loc_sparkline_in_full_payload` | `run_dashboard_generation` | Full generation with seeded artifacts; `locSparklinePoints` present; valid SVG points string; `locTrendSource` in `{"measured_history", "fallback_flat"}` |
| `test_sparkline_points_preserved_in_payload` | `run_dashboard_generation` | Regression: `sparklinePoints` key still present in payload after FIFO refactor |
| `test_history_trend_no_longer_reads_metrics_json` | `_history_trend` | Mock/spy: confirm `_history_trend` does not open any `metrics.json` file (verifies the O(n) I/O reduction) |

### 7.2 `test_metrics_module6_poller.py` — skipped-unchanged safety

| Test | Scope | Key assertions |
|------|-------|----------------|
| `test_trend_files_unchanged_after_skipped_unchanged` | `run_now` | After successful run creates both trend files; write `last_processed_commit` to current commit; call `run_now()` again; verify both trend files are byte-for-byte identical (mtime unchanged / content unchanged) |

### 7.3 `test_metrics_module7_publication.py` — publish integration

| Test | Scope | Key assertions |
|------|-------|----------------|
| `test_publish_includes_loc_sparkline_in_worktree` | `publish_metrics` | Published `__data.json` in worktree contains `locSparklinePoints` key |
| `test_publish_same_day_does_not_grow_loc_trend` | `publish_metrics` | Seed `loc_trend.json` with 1 slot for today; run publish (calls generation); verify trend still has exactly 1 slot |
| `test_publish_same_commit_does_not_grow_coverage_trend` | `publish_metrics` | Seed `coverage_trend.json` with 1 slot for current commit; run publish; verify trend still has exactly 1 slot |

---

## 8. Rejected Alternatives

### 8.1 LOC trend: commit-based (rejected)

LOC is influenced by many commits per day. A commit-keyed FIFO for LOC would grow by one slot
for every commit that runs through the pipeline. On days with multiple commits, the sparkline
accumulates multiple nearly-identical values. On low-commit days or during weekends/holidays,
the sparkline stagnates even as days pass. Neither behavior is useful for the intended
visualization (rate of code volume growth over time). Day-based granularity is correct for LOC.

### 8.2 Coverage trend: day-based (rejected)

Coverage is a revision-scoped metric. Two commits on the same day might have different
coverage (one adds tests, one adds code without tests). Day-based sampling would lose this
intra-day signal. Commit-based granularity is correct for coverage.

### 8.3 Coverage trend: continue scanning history directory (rejected)

Keeping the current `_history_trend()` approach for coverage is feasible but retains the O(n)
I/O cost, the retention-policy sensitivity, and the direction bug. All three problems are
solved by the FIFO approach at negligible implementation cost. There is no benefit to retaining
the scan-based approach.

### 8.4 Shared state file for both trends (rejected)

A single `trend_state.json` combining both FIFO buffers would reduce the file count but creates
coupling: a schema change to one trend would require updating parsers for both. Separate files
are more maintainable, independently versionable, and easier to debug.

### 8.5 Store LOC history in `artifacts/metrics/history/metrics.json` (rejected)

Re-using the history artifact path for LOC trend data would require changes to the aggregator
schema and would mix concerns (run-scoped measurement artifacts vs. dashboard trend state). The
`_collect_extra_loc()` data is not part of the aggregator's output — it is computed inside
`dashboard_generator.py`. Moving it upstream creates an implicit dependency between dashboard
generation logic and the aggregation schema that does not currently exist.

Critical Design Review: Sparkline FIFO
1. Drift Risk Assessment
1.1 _dashboard_payload() side-effect injection — SIGNIFICANT
The design places _update_coverage_trend() and _update_loc_trend() inside _dashboard_payload(). This converts a previously pure, side-effect-free transformation function into one that reads and writes files on every invocation. This has three downstream consequences the document does not fully resolve:

a) measured_at overwrite semantics on same-commit are unspecified. The FIFO update rule says "overwrite slots[-1] in-place" when commit_sha matches. The schema definition shows measured_at as a diagnostic field. The document does not say whether measured_at is updated during a same-commit overwrite. In practice, publish_metrics() calls run_dashboard_generation(), which calls _update_coverage_trend() which would overwrite slots[-1] with measured_at = now (publish time), replacing the original run time. If measured_at is subsequently used for diagnostics, it silently points to the last publish rather than the last measurement. The implementation spec must explicitly state that measured_at is not updated on a same-commit overwrite.

b) The module 7 test fixtures monkeypatch run_dashboard_generation entirely. Reading the actual test code in test_module7_publish_writes_publication_state_and_syncs_worktree, test_module7_publish_reports_push_failure, and both fingerprint tests: all of them use monkeypatch.setattr(poller_runner, "run_dashboard_generation", _fake_dashboard_gen). The _fake_dashboard_gen only writes a minimal __data.json — it never calls _dashboard_payload(). This means the two new module 7 tests described in §7.3 (test_publish_same_day_does_not_grow_loc_trend and test_publish_same_commit_does_not_grow_coverage_trend) cannot exercise the FIFO logic at all if they follow the same monkeypatching pattern. If they do NOT monkeypatch, they require full artifact seeding equivalent to the module 5 integration tests. The test plan does not resolve this tension. The two module 7 tests as described are either testing a code path that doesn't run (via monkeypatch) or require a structural departure from the module 7 fixture pattern.

c) Test isolation through tmp_path is correct. Since every test receives a distinct tmp_path, FIFO file accumulation across tests is not a risk. This is correctly handled.

1.2 Build-stamp / fingerprint interaction — CLEAN
The design correctly identifies that coverage_trend.json and loc_trend.json affect only __data.json content. They are not hashed by _compute_dashboard_source_fingerprint() (which hashes only .svelte, .ts, .js, .css and four config files). The LOC sparkline element in +page.svelte does change the fingerprint, triggering exactly one sync_local publish. All subsequent unchanged-source publishes revert to reuse_published. No hidden churn. ✓

The lastPublishedAt injection in publish_metrics() happens after run_dashboard_generation() returns — i.e., after both FIFOs are updated. This ordering is correct and the FIFO-written values are not disturbed by the lastPublishedAt injection. ✓

1.3 .gitignore gap — CORRECTLY IDENTIFIED, INCOMPLETELY MITIGATED
The document correctly flags this as a mandatory blocker. However, it does not specify the recovery procedure if either trend file is accidentally committed before the gitignore entry lands. Given that runtime.json IS git-tracked, a developer doing git add metrics/state/ accidentally pulls in the trend files. The review recommendation: both gitignore entries and the new state files should land in the same atomic commit; the PR checklist should include an explicit git status --porcelain validation step confirming the trend files are untracked (the §6.5 checklist already has this, which is good). No additional mitigation is needed beyond what is specified, but the accidental-commit recovery path should be documented.

1.4 UTC day-boundary — CORRECT
datetime.now(timezone.utc).date() evaluated at generation time is correct. The "run at 23:59, publish at 00:01" edge case is handled by the same-day overwrite rule for the intra-day path and correctly appends a new slot on the next day. The document's characterization ("No visual artifact; the sparkline adds a duplicate data point") is accurate and benign. ✓

1.5 Same-commit overwrite — CORRECT WITH ONE CAVEAT
The coverage FIFO same-commit overwrite is idempotent for coverage_percent (same commit always produces same value). The only non-idempotent field is measured_at — see §1.1(a) above.

1.6 cleanup_runtime_artifacts() interaction — CORRECT
Verified against the actual code: cleanup_runtime_artifacts() removes output and optionally history. state is untouched. Both trend files survive all cleanup invocations. This is a genuine durability improvement over the current history-scan approach. ✓

1.7 Publish-pipeline lock gap — UNADDRESSED IN DOCUMENT
run_now() holds poller.lock (exclusive flock). publish_metrics() does NOT acquire the lock. Both now call run_dashboard_generation(), which writes the FIFO state files. If publish_metrics() is invoked manually while a timer-triggered run_now() is active, both processes write to the same FIFO files without synchronization. In practice this is a low-probability event (publish is an operator command, not a timer call), and the risk is bounded (worst case: a slot is overwritten with a slightly different measured_at or loc_total). This is correctly an inherited constraint from the existing architecture. However, the document should explicitly acknowledge it rather than leaving it unstated.

2. Migration Risk Assessment
2.1 Coverage trend seeding from history — POOR COMPLEXITY/BENEFIT RATIO
The seeding logic performs the history scan that the entire refactor is designed to eliminate, running exactly once. On this installation, 16 distinct commits exist in history, all with coverage_percent = 80.12. Seeding produces a 10-slot FIFO where every slot has the same value. The resulting sparkline is a flat line at 80.12 — visually identical to the fallback_flat path (also a flat line, just at 0 rather than at the real value, but both render as flat). The practical benefit of seeding on this installation is: the coverageTrendSource field becomes "measured_history" instead of "fallback_flat" after the first post-PR run. That's the entire gain.

The seeding adds ~30-40 lines of history-scanning code that fires exactly once, implements a deduplication step (keep latest run per commit), handles the max_slots - 1 truncation, and must be tested with its own cases. This complexity is misaligned with the gain for the initial PR.

Recommendation: defer migration seeding entirely from the initial PR. Accept the flat-line period (which is visually identical to the current behavior anyway since all coverage is at 80.12 and the sparkline is currently flat). The seeding path can be added in a follow-up if coverage starts varying and the ramp-up period becomes noticeable.

2.2 LOC trend starting empty — NO RISK
Flat fallback for the first run is safe, expected, and visually equivalent to having no sparkline. ✓

2.3 Coverage rendering direction change — VISUAL STATE CHANGE, NOT JUST AN IMPROVEMENT
The document characterizes the direction fix as "a deliberate improvement, not a risk." This framing is partially correct but incomplete. On any installation where coverage has a visible slope (i.e., coverage is not a flat line), the sparkline shape would visually flip on the first post-PR publish: a previously downward-sloping line would become upward-sloping and vice versa. On this specific installation, coverage is flat — the flip is invisible. But the review should note this explicitly as a visual state change in deployed dashboards, not merely an implementation detail. Any existing screenshots, runbooks, or monitoring documentation about the sparkline direction would be invalidated.

2.4 sparklinePoints key preservation — NO REGRESSION RISK
The payload key is unchanged. The <polyline> element in +page.svelte is unchanged. Old compiled JS on the metrics branch (before the +page.svelte rebuild) reads sparklinePoints and continues to render correctly with the new FIFO-generated values. ✓

3. Missing Considerations
3.1 test_coverage_trend_direction_oldest_first — CONSTRUCTION TRAP
This test as described in §7.1 ("Seed FIFO with ascending coverage values [70.0, 75.0, 80.0]; verify sparklinePoints encodes monotonically decreasing y-coordinates from left to right") has a structural flaw if it proceeds through run_dashboard_generation().

_update_coverage_trend() inside _dashboard_payload() checks slots[-1]["commit_sha"] against commit_full from summary["source"]["commit_sha"]. If the test seeds three slots with fake commit SHAs ("aaa...", "bbb...", "ccc...") and then provides a summary.json with commit "ddd...", the function appends a fourth slot with the real coverage_percent value (from the test's metrics.json), not the seeded 70/75/80 values. The sparkline then reflects [70.0, 75.0, 80.0, real_coverage] — not the clean ascending series the test claims to verify.

This test must either:

Be implemented as a pure unit test of _update_coverage_trend() + _sparkline() directly, without going through run_dashboard_generation(), OR
Seed the FIFO with the first two slots using fake SHAs, and use the third slot's SHA as the current commit's SHA in the test's manifest.json/summary.json, so the current run overwrites slot 3 with the known coverage value and the direction is validated against [70.0, 75.0, current].
The test plan must specify which approach is taken.

3.2 Empty commit_sha guard for coverage FIFO — UNADDRESSED
commit_full = str((summary.get("source") or {}).get("commit_sha", "")) returns empty string when commit_sha is missing. If all runs share commit_sha = "", the FIFO permanently overwrites slots[-1] without ever appending a new slot. The sparkline never advances beyond 1 slot and remains on the flat-line fallback indefinitely. This scenario occurs on bootstrap runs and malformed test fixtures. The implementation of _update_coverage_trend() should guard: if commit_full is empty or fewer than 7 hex characters (a sanity check), skip the FIFO write and return the existing slots unmodified.

3.3 Zero _loc_total in LOC FIFO — UNADDRESSED
If all collectors fail and _loc_total = 0, the LOC FIFO records a slot with loc_total: 0. On the sparkline, this produces a spike to zero that may be mistaken for a real code deletion event. The LOC FIFO should treat _loc_total <= 0 as a sentinel indicating "no usable measurement" and store the slot as "loc_total": null — consistent with how coverage_percent: null is handled. The filter in the series derivation step ([[float(slot["loc_total"]) for slot in loc_trend_slots]](http://vscodecontentref/62)) then excludes null slots. This guard is cheap to add and prevents a misleading visual artifact.

3.4 _history_trend() still O(n) for trendRows — CORRECTLY OUT OF SCOPE, BUT NEEDS ACKNOWLEDGEMENT
After the refactor, _history_trend() drops the metrics.json read per run. It still reads summary.json + manifest.json per run for trendRows. The O(n) scan persists for this consumer. As the retention limit grows toward 120 runs, this remains a cost center. The document correctly leaves this out of scope, but should add a note that trendRows will be addressed in a subsequent optimization PR to avoid ambiguity about whether the O(n) claim (§0 executive summary: "eliminates O(n) disk I/O") is fully accurate. O(n × 2) is still O(n).

3.5 _collect_extra_loc() scan scope — CONFIRMED SAFE, NOT DOCUMENTED
_collect_extra_loc() scans Python files in metrics and shell scripts in install, bin, staging. The new trend files are .json files in state — they are not .py files and are excluded from the LOC count. The LOC metric is not contaminated by the new state files. This should be confirmed explicitly in the design document (under §5 or §3.1) as a one-line note, since the state files live inside the metrics directory that _collect_extra_loc() scans.

4. Verdict
The design is sound in principle but not yet implementation-ready as written. The FIFO data model, schema definitions, day boundaries, same-key overwrite rules, gitignore requirements, and migration paths for LOC are all correct. The rationale for the coverage FIFO refactor is well-argued and the four problems it eliminates are real.

Three issues require resolution before code is written:

The module 7 test plan is structurally incompatible with the module 7 fixture pattern. Tests test_publish_same_day_does_not_grow_loc_trend and test_publish_same_commit_does_not_grow_coverage_trend either need to avoid monkeypatching run_dashboard_generation (requiring full artifact seeding) or need to be moved into the module 5 test suite as pure generator-level tests, and replaced in module 7 with simpler idempotency checks at the publish layer.

measured_at overwrite semantics are unspecified. The implementation spec must say whether measured_at is preserved or updated on same-commit overwrite.

test_coverage_trend_direction_oldest_first cannot be written as described without careful SHA coordination between the seeded FIFO and the test's manifest. The test plan needs to specify the exact construction approach.

Two further additions are recommended before coding begins:

Remove migration seeding from the initial PR scope. It adds implementation complexity for zero visual benefit on this installation. Mark it "deferred" in the design.

Add the empty commit_sha and zero _loc_total guards to the specified behavior of _update_coverage_trend() and _update_loc_trend() respectively.

5. Recommended Safeguards Before Implementation
#	Safeguard	Applies to
S1	Specify measured_at is NOT updated on same-commit overwrite in §2.2	Design doc
S2	Add empty/invalid commit_sha guard to _update_coverage_trend() spec in §2.2	Design doc
S3	Add loc_total <= 0 → store as null rule to _update_loc_trend() spec in §3.4	Design doc
S4	Remove migration seeding from initial PR; defer to follow-up	Design doc §2.5
S5	Resolve module 7 test plan conflict — clarify that test_publish_same_* tests call real run_dashboard_generation(), document the full seeding they require, and restructure accordingly	Design doc §7.3
S6	Specify the exact SHA-matching construction pattern for test_coverage_trend_direction_oldest_first	Design doc §7.1
S7	Add one-line note confirming .json state files are below the _collect_extra_loc() filter threshold	Design doc §3 or §5
S8	Add explicit note that the coverage direction change is a visual state change on deployed non-flat installations, not only an implementation correction	Design doc §5.2
S9	Document the publish-lock gap as an acknowledged inherited constraint	Design doc §5
S10	Clarify O(n) claim scope: "sparkline I/O is now O(1); trendRows via _history_trend() remains O(n × 2)"	Design doc §0 or §1.1