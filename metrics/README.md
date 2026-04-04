# Metrics Runtime Layout

This directory is the host-side authority for metrics runtime assets.

Runtime directories:

- `metrics/runner/`: host-side execution modules.
- `metrics/systemd/`: generated unit templates (service/timer).
- `metrics/state/`: runtime state (`last_processed_commit`, runtime configuration).
- `metrics/output/`: staging area for generated output before publication.

Publication layout contract:

- `dashboard/index.html`
- `dashboard/assets/...`
- `artifacts/latest/manifest.json`
- `artifacts/latest/metrics.json`
- `artifacts/latest/summary.json` (future module)
- `artifacts/history/<run-id>/...`
- `reports/latest.md` (future module)

Module 1 focuses on schema and manifest contracts plus initialization artifacts.

Module 2 adds backend collector responsibilities:

- Python LOC collection for `src/`, `api/`, `tests/`
- Cyclomatic complexity and maintainability index collection (when radon is available)
- Python dependency graph extraction
- Host-side pytest coverage execution (with explicit `not_available` when coverage toolchain is unavailable)

Collector outputs are staged under:

- `metrics/output/backend/<run-id>/...`

Module 3 adds frontend collector responsibilities:

- LOC for JS/TS/Svelte in `webui/src` and `webui/tests`
- frontend cognitive complexity estimate
- JS dependency graph extraction from import/require statements
- explicit deferred frontend test coverage marker (`not_available`)

Collector outputs are staged under:

- `metrics/output/frontend/<run-id>/...`

Module 4 adds aggregation and delta responsibilities:

- merge backend/frontend module outputs into one `metrics.json`
- compute delta against previous successful run
- classify warnings/failures and generate summary severity indicators
- emit compact `summary.json` for dashboard/report consumers

Module 4 writes:

- `artifacts/metrics/latest/summary.json`
- `artifacts/metrics/history/<run-id>/summary.json`
- `metrics/output/aggregator/<run-id>/summary.json` (staged transient output)

