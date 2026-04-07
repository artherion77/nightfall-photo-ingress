# Metrics Dashboard Drift Repair — 2026-04-05

## Summary

Full-system drift analysis and repair of the nightfall-photo-ingress metrics
dashboard. The live dashboard at `artherion77.github.io/nightfall-photo-ingress`
was showing N/A for all complexity metrics, "0 modules" in the complexity
breakdown, bold tooltip text, and stale timestamps.

**Commit**: `fdeb684`  
**Branch**: `main`  
**Published**: `module6-20260405T202507-1` → `metrics` branch → GitHub Pages  

---

## Drift Points Found and Fixed

### 1. Frontend Collector — Missing `per_file` Dict

**Symptom**: Complexity Breakdown showed "0 modules" on the live dashboard.

**Root Cause**: `collect_cognitive_complexity()` returned a `files` array (list
of per-file results), but the dashboard generator expected a `per_file` dict
(path → float score). Iterating an empty dict produced zero modules.

**Fix** (`metrics/runner/frontend_collector.py`): Added post-processing in
`collect_cognitive_complexity()` that builds a `per_file` dict mapping relative
paths to rounded `file_mean` values from the `files` array.

### 2. Frontend Collector — Missing `max` Field

**Symptom**: Aggregator delta tracking could not compute deltas for
`modules.frontend.metrics.cognitive_complexity.max`.

**Root Cause**: `score_project()` computed and returned `mean` but not `max`.

**Fix** (`metrics/runner/frontend_collector.py`): Added `project_max =
max(file_means) if file_means else None` and included `"max": project_max` in
the return dict.

### 3. Dashboard Generator — `lastRunAt` Using Wrong Source

**Symptom**: "Last Run" timestamp on the dashboard showed the summary generation
time rather than when data collection actually finished.

**Root Cause**: `_dashboard_payload()` read `summary.generated_at` instead of
`manifest.execution.finished_at`.

**Fix** (`metrics/runner/dashboard_generator.py`): Changed `lastRunAt` to prefer
`manifest.execution.finished_at` with fallback to `summary.generated_at`.

### 4. Bold Tooltip Text

**Symptom**: Tooltip bubbles rendered in bold text.

**Root Cause**: `.tip-bubble` CSS class had no explicit `font-weight`, inheriting
`font-weight: 700` from the parent `.hero-value` element.

**Fix** (`metrics/dashboard/src/app.css`): Added `font-weight: 400` to
`.tip-bubble`.

### 5. Duplicate Tooltip Sentence

**Symptom**: Bundle Size tooltip contained two nearly-identical sentences:
"Classification and scale..." and "Scale and classification...".

**Root Cause**: Prior fix introduced a duplicate line.

**Fix** (`metrics/dashboard/src/routes/+page.svelte`): Removed the duplicate.

### 6. Publish Pipeline — Stale Fallback Paths

**Symptom**: Publishing could silently copy an old `__data.json` from a previous
run, making the live dashboard show stale data even after a successful pipeline
run.

**Root Cause**: `publish_metrics()` had an `else` branch that fell back to
copying `__data.json` from `repo_root/dashboard/` when the generated file didn't
exist.

**Fix** (`metrics/runner/poller_runner.py`):
- Removed all stale fallback paths.
- Made fresh generated `__data.json` mandatory (raises `RuntimeError` if missing).
- Added `_validate_publish_payload()` that checks `runId` and `commitFull` in
  the payload match the expected values before publishing.

### 7. Dashboard Generator — Missing Observability Fields

**Symptom**: No visibility into collector health or build provenance.

**Fix** (`metrics/runner/dashboard_generator.py`): Added two new payload
sections:
- `collectorStatuses`: dict with status/reason for backendComplexity,
  frontendCognitive, coverage, bundleSize.
- `buildStamp`: dict with `generatedAt`, `commitSha`, `runId`.

---

## Test Coverage

| Test File | New Tests | Description |
|-----------|-----------|-------------|
| `test_metrics_module3_frontend.py` | +3 | `per_file` dict shape, `max` field, empty-project edge case |
| `test_metrics_module5_dashboard.py` | +3 | `lastRunAt` source, `collectorStatuses`, `buildStamp` |
| `test_metrics_module6_poller.py` | +4 | `_validate_publish_payload`: match, runId mismatch, commit mismatch, empty-commit skip |
| `test_metrics_module7_publication.py` | updated | Mocks now write valid `__data.json` for publish validation |

**Regression**: 368 passed, 1 pre-existing skip (`test_module1_required_output_files_exist` — local state file absent).

---

## Verification

Published `__data.json` fields confirmed:

| Field | Before | After |
|-------|--------|-------|
| `complexityCard.cyclomatic` | N/A | 3.25 |
| `complexityCard.maintainability` | N/A | 56.42 |
| `complexityCard.frontend.value` | N/A | 0.68 |
| `complexityBreakdownDetail` total modules | 0 | 186 |
| `lastRunAt` | summary.generated_at | manifest.execution.finished_at |
| `collectorStatuses` | absent | 4 collectors reported |
| `buildStamp` | absent | runId + commitSha + generatedAt |
| Tooltip font-weight | 700 (inherited) | 400 (explicit) |
| Duplicate tooltip sentence | present | removed |
| Publish stale fallback | possible | blocked + validated |

---

## Files Modified

- `metrics/runner/frontend_collector.py` — `per_file` + `max`
- `metrics/runner/dashboard_generator.py` — `lastRunAt`, `collectorStatuses`, `buildStamp`
- `metrics/runner/poller_runner.py` — stale fallback removal, `_validate_publish_payload()`
- `metrics/dashboard/src/app.css` — `.tip-bubble` font-weight
- `metrics/dashboard/src/routes/+page.svelte` — duplicate tooltip line removed
- `tests/unit/test_metrics_module3_frontend.py` — 3 new tests
- `tests/unit/test_metrics_module5_dashboard.py` — 3 new tests
- `tests/unit/test_metrics_module6_poller.py` — 4 new tests
- `tests/unit/test_metrics_module7_publication.py` — mock updates
- `dashboard/` — rebuilt statics
