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

Module 5 adds dashboard generation responsibilities:

- static HTML dashboard generated from latest manifest/metrics/summary artifacts
- Markdown executive summary for operators
- historical trend snippets from prior history runs
- direct links to manifest and raw metric artifacts

Module 5 writes:

- `metrics/output/dashboard/latest/__data.json`
- `metrics/output/reports/latest.md`
- `metrics/output/dashboard/<run-id>/index.html` (staged transient output)
- `metrics/output/reports/<run-id>/latest.md` (staged transient output)

Module 6 adds poller and orchestration responsibilities:

- lock-protected single-run execution loop via `metricsctl run-now`
- unchanged commit fast-exit using `metrics/state/last_processed_commit`
- retry and timeout policy for unattended operation
- failure manifest emission on failed runs
- runtime control surface for install/reconfigure/start/stop/status/uninstall/publish

Module 6 writes:

- `metrics/systemd/nightfall-metrics-poller.service`
- `metrics/systemd/nightfall-metrics-poller.timer`
- `metrics/state/poller_status.json`
- `metrics/state/last_publication.json` (publication surface state)

Module 7 adds publication pipeline responsibilities:

- maintain a dedicated `metrics` branch worktree for publication commits
- sync latest successful dashboard/report/artifacts into the publication worktree
- create deterministic publication commits with run metadata
- preserve run history snapshots under published `artifacts/metrics/history/<run-id>/`

Module 7 writes:

- `metrics/state/last_publication.json` (published/no-change/skip state)
- `metrics/output/publication/metrics-branch-worktree/...` (published branch worktree)

Module 8 adds operations, audit, and extensibility responsibilities:

- failure taxonomy classification for run and publication errors
- retention pruning policy for historical run artifacts
- append-only event logging with field policy
- extension registry for optional collectors and explicit deferred states
- aggregation compatibility with schema extension module slots

Module 8 writes:

- `metrics/state/failure_taxonomy.json`
- `metrics/state/log_policy.json`
- `metrics/state/extensions.json`
- `metrics/output/logs/metrics-events.ndjson`
- `metrics/output/extensions/<run-id>/optional_collectors.json`

