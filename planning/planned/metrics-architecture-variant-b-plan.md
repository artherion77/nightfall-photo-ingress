# Metrics Architecture Plan (Variant B)

Status: Planned
Date: 2026-04-04
Scope: Remote-host polling architecture for automated metrics, coverage, complexity collection, publication, and review visibility.

## 1. Architecture Decision Summary

Authoritative decision: Variant B is the only accepted architecture.

- The remote host is the single authoritative execution instance.
- Metrics, coverage, complexity analysis, aggregation, and publication preparation run only on the remote host.
- GitHub is used only as presentation and review surface.
- Triggering is polling-based via systemd timer only, not webhook-driven, runner-driven, or cron-driven.
- Publication target is a dedicated metrics branch plus GitHub Pages output.
- MCP is an optional host-local control and inspection surface, not an execution authority independent of the systemd-managed runtime.

Operational consequence:

- No GitHub-hosted CI is required for metric generation.
- All coverage values come from real host-side test execution.
- Determinism, auditability, and recoverability are enforced on the host.

## 2. Scope and Quality Goals

The system must provide a simple, robust, and extensible quality pipeline for:

- LOC for Python, JS/TS, and Svelte
- Cyclomatic Complexity for Python
- Maintainability Index for Python
- Cognitive Complexity for frontend code
- Dependency graphs for Python and JS
- Python test coverage from real host-side test runs
- Optional later metrics:
	- bundle size
	- API surface
	- OpenAPI complexity

Relevant current test domains:

- Backend domain/CLI/registry/OneDrive: strong unit coverage
- Backend API: strong integration coverage
- Ingest/flow: strong integration coverage
- UI contract simulation: moderate coverage
- Staging live/prod-like smoke: present
- Web component/DOM unit: minimal today
- Browser E2E: early capability path only

Design constraints:

- Host-side execution only
- GitHub for visibility only
- Deterministic runs with manifests and stable outputs
- Modular growth path for frontend metrics and browser coverage later

## 3. Runtime Separation Model

### Host-side execution responsibilities

The remote host is responsible for:

- polling for new commits
- checking out or updating the target repository state
- running tests and collecting coverage
- computing metrics and dependency graphs
- aggregating all results into versioned artifacts
- generating static dashboard output
- publishing generated artifacts into the metrics branch worktree
- installing and managing the authoritative systemd service/timer pair through `metricsctl`
- exposing runtime status and selected controls through MCP endpoints or MCP task mappings where useful

### GitHub-side presentation responsibilities

GitHub is responsible only for:

- displaying the generated static dashboard via GitHub Pages
- exposing the published metrics branch for review and diff inspection
- preserving history of generated reports in git

GitHub does not execute the metrics pipeline.

## 4. Target Architecture

The system consists of eight modules executed in a deterministic host-side pipeline.

### End-to-end flow

1. Poller detects a new target commit on the source branch.
2. Runner acquires lock and creates a run id.
3. Repository is synchronized to the exact commit under analysis.
4. Backend tests run on host and produce coverage artifacts.
5. Metrics collectors compute backend and frontend metrics.
6. Aggregator creates normalized JSON outputs and deltas versus previous run.
7. Dashboard generator creates static HTML and Markdown summaries.
8. Publisher updates metrics branch and GitHub Pages content.
9. Manifest and audit records are stored for traceability.

## 5. Module Plan

## Module 1: Metrics Schema and Run Manifest

Goal:
- Define the canonical data contract for every run.

Responsibilities:
- versioned metrics schema
- run manifest schema
- tool version recording
- commit sha, branch, timestamp, hostname, duration, exit state

Outputs:
- `artifacts/metrics/latest/manifest.json`
- `artifacts/metrics/latest/metrics.json`
- `artifacts/metrics/history/<run-id>/manifest.json`
- `artifacts/metrics/history/<run-id>/metrics.json`
- `metrics/state/last_processed_commit`
- `metrics/state/runtime.json`

Runtime layout:
- `metrics/runner/` for host-side execution modules
- `metrics/systemd/` for generated service and timer unit templates
- `metrics/state/` for last processed commit, lock metadata, and runtime configuration
- `metrics/output/` for staging generated dashboard and raw artifacts before publication
- `metricsctl` as the host-side administrative entrypoint

Determinism rules:
- Every run gets exactly one run id.
- Every artifact references exactly one commit sha.
- Partial failures are represented explicitly, not silently dropped.

Acceptance criteria:
- Schema is stable and machine-readable.
- Manifest can reconstruct what was executed and with which tool versions.

## Module 2: Backend Metrics Collector

Goal:
- Collect backend code metrics and real coverage from host-side execution.

Responsibilities:
- LOC for Python
- Cyclomatic Complexity for Python
- Maintainability Index for Python
- Python dependency graph
- pytest coverage collection

Expected sources:
- `src/`
- `api/`
- `tests/`

Execution model:
- Run host-side pytest commands in the authoritative environment.
- Collect coverage output from real test execution only.
- Mark unavailable metrics explicitly if a tool fails.

Acceptance criteria:
- Coverage is derived from host test runs.
- Complexity and maintainability values are reproducible for a fixed commit.

## Module 3: Frontend Metrics Collector

Goal:
- Collect frontend structure and complexity metrics independently of browser maturity.

Responsibilities:
- LOC for JS/TS/Svelte
- cognitive complexity for frontend logic
- JS dependency graph
- optional future integration of Vitest and Playwright coverage when those layers mature

Expected sources:
- `webui/src/`
- `webui/tests/`

Execution model:
- Run host-side static analysis tools against the checked-out commit.
- Report missing optional frontend test coverage as `not_available` rather than assuming zero.

Acceptance criteria:
- Frontend metrics are emitted consistently even if browser tests are not yet active.
- Output distinguishes implemented metrics from deferred metrics.

## Module 4: Aggregator and Delta Engine

Goal:
- Normalize all collector outputs into one audit-friendly dataset.

Responsibilities:
- merge backend and frontend metrics
- compute deltas versus previous successful run
- classify warnings and collection failures
- generate summary severity indicators

Outputs:
- merged `metrics.json`
- compact `summary.json`
- delta section against previous published run

Acceptance criteria:
- Re-running the same commit without source changes produces stable aggregate results except timestamp fields.

## Module 5: Dashboard Generator

Goal:
- Create human-readable presentation artifacts from normalized data.

Responsibilities:
- static HTML dashboard
- Markdown executive summary
- trend snippets from history
- direct links to manifest and raw metric artifacts

Rendering decision:
- The dashboard should be implemented with SvelteKit and published as a static prerendered site.
- The host-side pipeline builds the dashboard into static assets for GitHub Pages.
- If the first implementation slice needs lower complexity, a temporary plain-HTML generator is acceptable, but the target rendering architecture remains SvelteKit static output.

UI mock:
- [Code quality and metrics overview](../../design/ui-mocks/Code%20quality%20and%20metrics%20overview.png)

Presentation sections:
- repository and commit context
- backend metrics
- frontend metrics
- coverage summary
- dependency graph references
- trend delta
- warnings and unavailable metrics

Acceptance criteria:
- Dashboard is fully renderable from generated artifacts only.
- No live server is needed to inspect results on GitHub Pages.

## Module 6: Poller and Orchestration Runner

Goal:
- Provide the only authoritative execution loop on the remote host.

Responsibilities:
- polling source branch on interval
- detecting new head commit
- queueing exactly one active run
- lock file or system-level mutual exclusion
- timeout and retry policy
- safe failure handling and resumability
- exposing operational control through `metricsctl`

Authoritative trigger mode:
- systemd timer plus oneshot service

Runtime control surface:
- `metricsctl start`
- `metricsctl stop`
- `metricsctl status`
- `metricsctl run-now`
- `metricsctl install --frequency-minutes <n>`
- `metricsctl uninstall`
- `metricsctl publish`

MCP integration surface:
- MCP may expose read-first operations such as:
	- current runtime status
	- last processed commit
	- last successful run id
	- latest manifest and summary paths
	- last publication result
- MCP may expose explicit operator actions that delegate to `metricsctl`, such as:
	- `metrics.status`
	- `metrics.run-now`
	- `metrics.publish`
	- `metrics.install`
	- `metrics.stop`
- MCP actions must call the same host runtime and state files used by systemd and `metricsctl`.
- MCP must not introduce a second scheduler or a parallel execution path.

Determinism rules:
- Only one run per branch target at a time.
- If the remote source head matches `last_processed_commit`, the runtime exits immediately without regenerating artifacts or dashboard output.
- Every run writes manifest even on failure.

Acceptance criteria:
- Poller can run unattended.
- Concurrent execution is prevented.
- Runtime frequency is configurable, with 60 minutes as the default.

## Module 7: Publication Pipeline

Goal:
- Publish generated metrics artifacts into GitHub-facing outputs without giving GitHub execution authority.

Responsibilities:
- maintain a dedicated metrics branch worktree
- update Pages-ready content from latest successful run
- commit generated artifacts with run metadata
- preserve history for review and audit

Publication targets:
- metrics branch
- GitHub Pages static site rooted in published dashboard content
- dashboard published under `/dashboard/` path on GitHub Pages

Acceptance criteria:
- New host-side run updates metrics branch deterministically.
- GitHub Pages reflects latest published successful run.
- Dashboard URL layout is stable and predictable for operators and review links.

## Module 8: Operations, Audit, and Extensibility

Goal:
- Keep the system operable, inspectable, and easy to extend.

Responsibilities:
- failure taxonomy
- retention policy
- log policy
- extension points for new metrics
- explicit handling for optional collectors

Extension examples:
- bundle-size collector
- OpenAPI complexity collector
- API-surface diff collector
- future Vitest coverage collector
- future Playwright coverage collector

Acceptance criteria:
- New collectors can be added without redesigning the pipeline.
- Historical runs remain readable after schema extension.

## 6. Polling Mechanism (systemd only)

Authoritative mode: systemd timer.

Recommended structure:

- `nightfall-metrics-poller.service`
- `nightfall-metrics-poller.timer`
- `metricsctl` installs, updates, enables, disables, and removes these units on the host.

Timer behavior:

- default cadence: every 60 minutes
- cadence is configurable through `metricsctl install --frequency-minutes <n>` and `metricsctl reconfigure --frequency-minutes <n>`
- persistent timer enabled so missed runs after reboot are resumed
- service invokes the host-side runner script with lock enforcement

Polling algorithm:

1. Fetch source branch metadata.
2. Compare remote head to last processed commit recorded in state file.
3. Exit immediately and cleanly if unchanged.
4. Acquire lock if changed.
5. Execute full pipeline.
6. On success, update last processed commit.
7. On failure, preserve failure manifest and keep previous successful publication intact.

Operational rule:

- systemd polling is authoritative. Manual runs may exist for debugging, but they do not replace the poller model.

## 7. Publication Logic (metrics branch + GitHub Pages)

Publication model:

- The host writes generated output into a dedicated local worktree for the metrics branch.
- The branch contains:
	- latest dashboard
	- latest machine-readable artifacts
	- historical run snapshots
	- Markdown summaries
- The host commits and pushes metrics branch updates after successful publication preparation.

Recommended branch structure:

- `dashboard/index.html`
- `dashboard/assets/...`
- `artifacts/latest/manifest.json`
- `artifacts/latest/metrics.json`
- `artifacts/latest/summary.json`
- `artifacts/history/<run-id>/...`
- `reports/latest.md`

GitHub Pages model:

- Pages serves static content from the metrics branch publishing path.
- GitHub is passive presentation only.
- If a run fails, existing published Pages content remains unchanged until next successful run.
- The intended operator-facing dashboard path is `/dashboard/`.
- The exact full URL depends on repository Pages configuration, but the published site layout must make `/dashboard/index.html` the canonical dashboard entrypoint.

Review model:

- Each host publication commit documents:
	- source commit sha
	- run id
	- success/failure state
	- generated timestamp

MCP-aware publication visibility:

- The latest published dashboard path and report paths should also be exposed through MCP status output for agent/operator discovery.
- MCP should return the canonical Pages-relative dashboard location as `/dashboard/`.

## 8. Metrics and Coverage Collection Model

### Backend collection

- Run pytest on the remote host in the authoritative environment.
- Use pytest-cov for real coverage data.
- Collect:
	- total coverage
	- per-package coverage where practical
	- complexity and maintainability for Python modules

### Frontend collection

- Run static analysis on `webui/src` and related frontend sources.
- Collect LOC and complexity metrics independently from browser test maturity.
- Frontend test coverage remains optional until the Vitest and Playwright layers are operationalized.

### Domain-aware interpretation

The pipeline should reflect the current maturity split:

- backend coverage is authoritative today
- frontend structural metrics are authoritative today
- frontend runtime coverage is explicitly staged for later introduction
- browser-chain capability can later feed dashboard sections without changing the core architecture

## 9. Audit and Manifest Structure

Each run must produce a manifest with at least:

- schema version
- run id
- source repository path
- source branch
- source commit sha
- poll trigger timestamp
- start and end timestamps
- hostname
- executor identity
- tool versions
- executed steps
- per-step exit codes
- artifact paths
- publication result
- dashboard relative path
- MCP exposure metadata for latest paths where implemented

Each metrics payload must include:

- collection status per module
- values per metric family
- `not_available` or `failed` markers when appropriate
- delta versus prior successful run

Audit rules:

- Never overwrite historical manifests.
- Latest pointers may move, history entries must not.
- Failed runs are retained for diagnosis.

## 10. Concrete Implementation Plan

Implementation is organized as deterministic steps that can later be executed as Claude Code work chunks.

### Step 1: Define schemas and directories

- create `metrics/runner`, `metrics/systemd`, `metrics/state`, and `metrics/output` directory structure
- create `metricsctl` administrative script
- define manifest and metrics JSON schema
- define branch publication directory layout

### Step 2: Build host runner skeleton

- create runner entrypoint script or Python module in `metrics/runner`
- implement state file handling
- implement lock handling
- implement no-change short-circuit that exits before collector or dashboard work for unchanged commit heads
- implement runtime config loading with default `frequency_minutes = 60`

### Step 3: Implement `metricsctl`

- add `start`, `stop`, `status`, `run-now`, `publish`, `install`, `reconfigure`, and `uninstall` subcommands
- generate and install systemd unit files on the host
- enable and disable timer/service as needed
- validate frequency input and write runtime config
- expose safe git publication command for metrics branch updates

### Step 4: Implement MCP integration layer

- add MCP task mappings or endpoints for `metrics.status`, `metrics.run-now`, and `metrics.publish`
- ensure MCP delegates to the same `metricsctl` commands and runtime state
- expose latest manifest, summary, and dashboard relative paths through MCP status output
- explicitly forbid independent MCP scheduling logic

### Step 5: Implement backend collector

- run pytest with coverage
- collect Python LOC
- collect Python complexity and maintainability
- collect Python dependency graph

### Step 6: Implement frontend collector

- collect JS/TS/Svelte LOC
- collect frontend cognitive complexity
- collect JS dependency graph
- mark optional coverage as deferred if unavailable

### Step 7: Implement aggregator

- merge collector outputs
- compute deltas against latest successful run
- generate summary severity fields

### Step 8: Implement dashboard generator

- static HTML dashboard
- Markdown summary
- machine-readable latest pointers
- SvelteKit static prerender build for GitHub Pages publication
- dashboard published under `dashboard/`

### Step 9: Implement publication pipeline

- metrics branch worktree management
- copy generated outputs into branch structure
- commit and push from host
- publish dashboard to `dashboard/index.html`

### Step 10: Implement systemd installation and timer wiring

- oneshot service definition
- timer definition
- `metricsctl install` writes or updates unit files
- `metricsctl uninstall` removes unit files and disables timer/service
- `metricsctl reconfigure` updates timer frequency without changing source artifacts

### Step 11: Add operational guardrails

- timeout policy
- failure taxonomy
- retention cleanup policy
- explicit skip logic for unchanged commits
- MCP delegation guard so host runtime state remains single-source-of-truth

### Step 12: Add audit and verification tests

- schema validation tests
- deterministic aggregation tests
- publication layout tests
- state and lock handling tests
- `metricsctl` command tests
- unchanged-commit fast-exit tests
- systemd unit generation tests
- MCP delegation and status-output tests

## 11. Determinism and Auditability Rules

- One authoritative host-side runner.
- One run id per execution.
- One commit sha per artifact set.
- One latest pointer to the most recent successful publication.
- History is append-only.
- Publication does not destroy prior successful data.
- GitHub never becomes execution authority.

## 12. Extensibility Model

The design is intentionally collector-driven.

New metrics can be added by:

1. adding a collector module
2. extending the schema version
3. registering the collector in the runner
4. teaching the dashboard generator how to render the new section

Expected future extensions:

- Vitest coverage integration
- Playwright coverage integration
- bundle-size trend charts
- OpenAPI complexity and endpoint churn
- API-surface change risk scoring

Compatibility rule:

- Optional future collectors must not break existing manifests or dashboard rendering when unavailable.

## 13. Recommended Next Implementation Slice

The first implementation slice should deliver:

- Module 1 skeleton
- Module 6 runner skeleton with polling state and unchanged-commit fast-exit
- Module 3 `metricsctl` with systemd install/start/stop/status support
- Module 2 backend collector MVP
- Module 4 aggregator MVP
- Module 5 dashboard MVP
- Module 7 metrics branch publication MVP

That slice is sufficient to establish an authoritative systemd-managed host runtime, real host-side coverage publication, and a first GitHub-visible dashboard with deterministic audit artifacts.