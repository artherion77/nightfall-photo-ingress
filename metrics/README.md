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

