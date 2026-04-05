# Dashboard Metrics Improvement Plan (Chunked)

Status: In Progress
Date: 2026-04-04
Owner: Systems Engineering
Scope: Metrics dashboard quality, metric correctness, collector enablement, and observability upgrades

## 1. Context and findings

Recent dashboard iterations improved UX, but several gaps remain:

- Some visualizations are heuristic or synthetic, not directly derived from measured series.
- Python complexity is often unavailable due to missing collector toolchain.
- Frontend complexity currently uses a custom heuristic and lacks rule-backed per-file diagnostics.
- Dependency graph tiles render abstract nodes without actionable metadata.
- Optional collector surfaces (bundle size, openapi complexity, API drift) are mostly unavailable.
- Dashboard metric coverage can be broadened with pragmatic engineering metrics.

This plan decomposes improvements into independent chunks with hard acceptance checks.

---

## 2. Chunk overview

| Chunk | Name | Objective | Depends on |
|------|------|-----------|------------|
| 0 | Baseline contracts | Stabilize payload schema and explain synthetic metrics | None |
| 1 | Sparkline correctness | Replace synthetic curve with measured historical coverage series | 0 |
| 2 | Python complexity enablement | Ensure backend complexity is collected in dev runtime | 0 |
| 3 | Frontend complexity v2 | Add rule-backed complexity collection for JS/TS/Svelte | 0 |
| 4 | Bundle analysis collector | Add bundle-size and composition metrics from Vite/Rollup | 0 |
| 5 | Dependency graph actionable UX | Surface node metadata and meaningful hover details | 0 |
| 6 | Optional collector hardening | Promote optional metrics from mostly unavailable to useful | 2,3,4 |
| 7 | New metric set expansion | Add high-value quality and delivery metrics | 1,6 |

---

## 3. Chunk details

## Chunk 0: Baseline contracts

Implementation status: Implemented (2026-04-04)

### Goal
Document metric provenance and lock the dashboard payload contract so future chunks remain backwards compatible.

### Work items

- Add payload contract notes for each key metric field in generator docs.
- Mark synthetic metrics explicitly in UI tooltip copy where still applicable.
- Add schema assertions for required payload fields used by dashboard rendering.

### Testable acceptance criteria

- `tests/unit/test_metrics_module5_dashboard.py` verifies presence and type of:
  - `runId`, `lastRunAt`, `repoUrl`, `repoHeadUrl`, `repoCommitUrl`
  - `versions.python`, `versions.typescript`
  - `runMeta.startedAt`, `runMeta.finishedAt`, `runMeta.durationSeconds`
- Dashboard copy includes explicit source label for synthetic-only visuals.
- No existing dashboard rendering path throws when optional fields are absent.

---

## Chunk 1: Sparkline correctness

### Goal
Use measured coverage trend history instead of synthetic warning-based points.

### Work items

- Persist historical coverage percentages per run from backend coverage collector output.
- Build sparkline from actual historical series plus current run only.
- Fall back to flat line only if fewer than 2 measured points exist.

### Testable acceptance criteria

- Given 5 historical runs with known coverage values, generated `sparklinePoints` maps monotonically to those 5 values plus current run.
- `dashboard/__data.json` contains a new provenance field such as `coverageTrendSource: "measured_history"`.
- Unit tests fail if warning-count values are used to derive coverage sparkline.

---

## Chunk 2: Python complexity enablement

### Goal
Make backend cyclomatic and maintainability consistently available in dev container runs.

### Work items

- Ensure `radon` is installed in the metrics execution environment in the dev container.
- Verify collector records radon version and non-empty complexity payload.
- Add failure diagnostics for parser errors or unsupported files.

### Testable acceptance criteria

- `metricsctl collect-backend --run-id <id>` emits:
  - `modules.backend.metrics.complexity.status == "available"`
  - non-null `cyclomatic.mean` and `maintainability_index.mean`
  - `collectors.backend.tool_versions.radon != "not_available"`
- A regression test verifies non-availability reason contains actionable text when radon is missing.

---

## Chunk 3: Frontend complexity v2

### Goal
Add rule-backed frontend complexity metrics (in addition to or replacing heuristic score).

### Work items

- Add ESLint-based complexity collector path for JS/TS/Svelte files.
- Parse and aggregate per-file complexity stats.
- Preserve current heuristic as fallback with source tag.

### Testable acceptance criteria

- `modules.frontend.metrics.cognitive_complexity` includes:
  - `source` in {`eslint_rules`, `heuristic_fallback`}
  - per-file entries with score values when ESLint path is available.
- If ESLint toolchain is unavailable, collector returns `status: not_available` with explicit reason and fallback metric remains rendered.
- Dashboard tooltip text changes based on source field.

---

## Chunk 4: Bundle analysis collector

### Goal
Expose real bundle intelligence from frontend build artifacts.

### Work items

- Run Vite/Rollup bundle visualizer in non-interactive JSON output mode.
- Collect totals: raw, gzip, brotli, chunk count, largest chunk/module.
- Add top-5 contributors table in payload.

### Testable acceptance criteria

- `modules.optional_collectors.collectors.bundle_size.status == "available"` for successful frontend build.
- `dashboard/__data.json` includes:
  - total KB, gzip KB, brotli KB
  - largest chunk name and size
  - top contributor list length >= 1
- Unit test validates parser behavior against a saved visualizer JSON fixture.

---

## Chunk 5: Dependency graph actionable UX

### Goal
Make graph tiles informative and debuggable rather than decorative.

### Work items

- Include node metadata: module path, fan-in, fan-out, local/external classification, cycle membership.
- Add hover tooltip in graph tile for node details.
- Add quick links to source path when repo URL is known.

### Testable acceptance criteria

- Graph payload includes node metadata keys for both backend and frontend graphs.
- Dashboard hover on graph node displays at least:
  - module path
  - fan-in/fan-out
  - cycle flag
- Snapshot/UI test confirms tooltip renders inside tile bounds on desktop and mobile breakpoints.

---

## Chunk 6: Optional collector hardening

### Goal
Reduce `not_available` warnings for optional collectors to improve signal quality.

### Work items

- Add collector readiness preflight in `metricsctl extensions-status` output.
- Add explicit remediation hints for each optional collector missing dependency.
- Gate optional collector errors to avoid whole-run degradation.

### Testable acceptance criteria

- `metricsctl extensions-status` reports each optional collector as one of:
  - ready
  - missing_dependency
  - disabled_by_config
- For missing dependency, output includes install hint and expected command/tool name.
- Aggregation summary warning count decreases after enabling configured optional collectors in dev environment.

---

## Chunk 7: New metric set expansion

### Goal
Add practical engineering health metrics beyond current baseline.

### Candidate metrics

- Test duration trend (unit/integration).
- Flaky test index (rolling pass/fail instability signal).
- Dependency vulnerability trend (count by severity over time).
- Coverage by test scope (unit/integration/e2e) when available.
- API contract drift score against prior OpenAPI snapshot.
- Build duration and bundle delta trend.

### Work items

- Implement 2 to 3 metrics first (time-boxed), keep others in backlog.
- Add trend history integration and dashboard cards.
- Add thresholds with warning semantics.

### Testable acceptance criteria

- At least 2 new metrics are emitted with historical trend entries across 3 runs.
- Dashboard renders new cards with clear source/provenance tooltips.
- Summary severity and warning indicators update when threshold breaches occur.

---

## 4. Execution order and batching

Recommended short-cycle sequence:

1. Chunk 0 (contract hardening)
2. Chunk 2 (Python complexity availability)
3. Chunk 1 (coverage sparkline correctness)
4. Chunk 4 (bundle analysis)
5. Chunk 3 (frontend complexity v2)
6. Chunk 5 (dependency graph actionable UX)
7. Chunk 6 (optional collector hardening)
8. Chunk 7 (new metric expansion)

Rationale:
- Establish correctness and tooling availability first.
- Upgrade metric fidelity before adding new metric families.
- Defer broad expansion until existing optional surfaces are stable.

---

## 5. Definition of done for this plan

This plan is considered complete when:

- Every chunk has an implementation PR linked from this document.
- Each chunk acceptance criteria is automated in tests where feasible.
- Dashboard can state provenance for every major metric card.
- Remaining `not_available` states are intentional and documented.
