# Dashboard Metrics Improvement Plan (Chunked)

Status: In Progress
Date: 2026-04-06
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

| Chunk | Name | Objective | Status | Depends on |
|------|------|-----------|--------|------------|
| 0 | Baseline contracts | Stabilize payload schema and explain synthetic metrics | Done | None |
| 1 | Sparkline correctness | Replace synthetic curve with measured historical coverage series | Done | 0 |
| 2 | Python complexity enablement | Ensure backend complexity is collected in dev runtime | **Done** ✅ | 0 |
| 3A | Design Sonar Cognitive Complexity | Design methodology and parser choice | **Done** ✅ | 0 |
| 3B | Implement Sonar Cognitive Complexity | Frontend cognitive complexity via AST traversal | **Done** ✅ | 3A |
| 4 | Bundle analysis collector (with pipeline) | Add bundle-size metrics via test pipeline integration | **Done** ✅ | pipeline |
| 5 | Dependency graph actionable UX | Surface node metadata and meaningful hover details | Done | 0 |
| 6 | Optional collector hardening | Promote optional metrics from mostly unavailable to useful | Pending | 2,3B |
| 7 | New metric set expansion | Add high-value quality and delivery metrics | Pending | 1,6 |
| 8 | Build Cost & Schema Guardrails | Control build overhead and protect parser compatibility | Backlog (non-blocking) | 4 |

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

Implementation status: Complete (2026-04-05)

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

### Status note

**No further action required.** The implementation is correct. The flat sparkline observed in production (`"0.00,42.00 180.00,42.00"`) is expected behavior and not a defect: only 2 historical coverage runs exist in the artifact store, and both measured the same value (80.116%). As more collection runs succeed and accumulate diverse coverage measurements, the sparkline will naturally display variation. The system currently shows `coverageTrendSource: "measured_history"` (correct provenance), confirming measured values are used rather than synthetic approximations.

---

## Chunk 2: Python complexity enablement

Implementation status: **Implemented (2026-04-05)** ✅

### Goal
Make backend cyclomatic and maintainability consistently available in dev container runs.

### Current state

- Backend complexity collector is operational and emits measured complexity metrics
- Latest artifact reports non-null backend complexity means for both cyclomatic and maintainability index
- Focused regression tests for backend collector and dashboard payload contract pass

### Verification evidence

1. **Artifact evidence (`artifacts/metrics/latest/metrics.json`):**
  - `modules.backend.metrics.complexity.status == "success"`
  - `modules.backend.metrics.complexity.cyclomatic.mean` is non-null
  - `modules.backend.metrics.complexity.maintainability_index.mean` is non-null

2. **Regression evidence:**
  - `tests/unit/test_metrics_module2_backend.py` passes
  - `tests/unit/test_metrics_module5_dashboard.py` passes

3. **Dashboard payload behavior:**
  - `complexityCard.cyclomatic` and `complexityCard.maintainability` are populated when metrics are available

### Status note

**No further implementation action required for Chunk 2.** Keep a lightweight regression check in future chunk work to ensure backend complexity remains available and measured.

### Testable acceptance criteria

- `metricsctl collect-backend --run-id <id>` emits:
  - `modules.backend.metrics.complexity.status == "available"`
  - non-null `cyclomatic.mean` and `maintainability_index.mean`
  - `collectors.backend.tool_versions.radon != "not_available"`
- Dashboard `complexityCard.cyclomatic` and `complexityCard.maintainability` show numeric values (not null)
- Regression test verifies non-availability reason contains actionable text when radon is missing

---

## Chunk 3: Frontend complexity v2 — Implemented, with parser hardening follow-up

### Current state

- Sonar Cognitive Complexity design docs exist in `design/metrics/frontend/sonar-cognitive-complexity.md` and `design/metrics/frontend/frontend-metrics-integration.md`
- AST-based collector is implemented in `metrics/runner/frontend_collector.py`
- Regression coverage exists in `tests/unit/test_metrics_module3_frontend.py` and `tests/unit/test_cognitive_complexity.py`
- Latest artifact reports `modules.frontend.metrics.cognitive_complexity.source == "sonar_cognitive"` with a non-null mean
- Dashboard payload exposes provenance via `complexityCard.frontend.source`, `complexityCard.frontend.status`, and `complexityCard.frontend.parser_version_label`

### Revised approach: Sonar Cognitive Complexity

Chunk 3 is now split into design (3A) and implementation (3B) phases using **Sonar Cognitive Complexity** reference (G. Ann Campbell, "Cognitive Complexity — A new way of measuring understandability", SonarSource 2017):

### Drift note

- The design and implementation are complete enough to mark Chunk 3A and 3B done, but the previous plan state is stale
- Latest live metrics are still `status: "partial"` because `.svelte` files currently hit parse errors
- Current implementation parses `.svelte` with JS grammar fallback rather than dedicated Svelte script extraction, so runtime coverage on Svelte-heavy trees remains incomplete

---

## Chunk 3A: Design Sonar Cognitive Complexity Collector

Implementation status: **Implemented (2026-04-05)** ✅

### Goal

Produce a design specification for a stable, AST-based cognitive complexity collector for JS/TS/Svelte that adheres to the Sonar methodology.

### Verification evidence

1. **Design docs exist:**
   - `design/metrics/frontend/sonar-cognitive-complexity.md`
   - `design/metrics/frontend/frontend-metrics-integration.md`
2. **Methodology is documented:**
   - Sonar Cognitive Complexity reference is cited
   - AST traversal/scoring rules are documented
   - Payload contract and provenance model are defined
3. **Design direction is implemented:**
   - `metrics/runner/frontend_collector.py` follows the tree-sitter Python approach documented here

### Status note

**No further design-gate work is required for Chunk 3A.** The design phase is complete and implementation has already proceeded from it.

### Testable acceptance criteria

- Design documents exist and reference Sonar Cognitive Complexity (2017) paper
- Algorithm pseudocode is complete and maps to Sonar-style scoring rules
- Technology choice is justified and implemented via Python tree-sitter collector
- Payload schema is documented and backwards-compatible

---

## Chunk 3B: Implement Sonar Cognitive Complexity Collector

Implementation status: **Implemented (2026-04-05)** ✅

### Goal

Implement the AST-based Sonar Cognitive Complexity collector and integrate into metrics pipeline.

### Current state

- Collector implementation lives in `metrics/runner/frontend_collector.py`
- Frontend collection integrates the collector through `run_frontend_collection()`
- Dashboard payload wiring is implemented in `metrics/runner/dashboard_generator.py`
- Dashboard rendering consumes provenance from `complexityCard.frontend.*`
- Focused tests exist in `tests/unit/test_metrics_module3_frontend.py` and `tests/unit/test_cognitive_complexity.py`

### Verification evidence

1. **Artifact evidence (`artifacts/metrics/latest/metrics.json`):**
  - `modules.frontend.metrics.cognitive_complexity.source == "sonar_cognitive"`
  - `modules.frontend.metrics.cognitive_complexity.mean` is non-null
  - `modules.frontend.metrics.cognitive_complexity.status == "partial"` in the latest run because `.svelte` parse failures are recorded, not because the collector is absent

2. **Dashboard evidence (`metrics/output/dashboard/module6-20260405T223210-1/__data.json`):**
  - `complexityCard.frontend.source == "sonar_cognitive"`
  - `complexityCard.frontend.status` is populated
  - `complexityCard.frontend.parser_version_label` is populated

3. **Regression evidence:**
  - `tests/unit/test_metrics_module3_frontend.py` exists and covers scoring, parser info, per-file output, and integration writes
  - `tests/unit/test_cognitive_complexity.py` exists and covers rule-level scoring cases

### Status note

**Chunk 3B is implemented and active in the dashboard pipeline.** Remaining drift is hardening work, not missing implementation: the current collector still parses `.svelte` files with JS grammar fallback, so Svelte-heavy runs can remain `partial` until dedicated Svelte parsing or script extraction is added.

### Testable acceptance criteria

- `modules.frontend.metrics.cognitive_complexity.source == "sonar_cognitive"` when scores are emitted
- Scores match the implemented Sonar-style methodology covered by unit tests
- Dashboard exposes provenance through `complexityCard.frontend.source`
- Dashboard displays a numeric frontend complexity score when successful files are present, even if the overall collector status is `partial`

---

## Chunk 4: Bundle analysis collector

Implementation status: **Implemented (2026-04-05)** ✅

### Current state

- Producer contract implemented in `webui/vite.config.js` with JSON bundle stats emission
- Build dependency added in `webui/package.json` (`rollup-plugin-visualizer`)
- Handover contract documented in `metrics/docs/bundle-stats-handover-contract.md`
- `bundle_size` collector enabled in `metrics/state/extensions.json`
- Optional collector emits `status: available` when `webui/dist/bundle-stats.json` is present
- Dashboard payload now carries populated `system.bundleSizeKb` and `system.bundleSizeDetail`

### Goal

Establish a complete handover contract between frontend build pipeline (test/package step) and metrics collector (consumption step).

### Verification evidence

1. **Producer output path:**
  - `webui/dist/bundle-stats.json` generated via `pnpm build`

2. **Schema compatibility:**
  - `bundle-stats.json` validates with `_parse_bundle_stats()` in `metrics/runner/module8_ops.py`
  - Parser returns `status: available`

3. **Collector and dashboard propagation:**
  - `modules.optional_collectors.collectors.bundle_size.status == "available"` in run artifacts
  - `metrics/output/dashboard/<run-id>/__data.json` contains non-null `system.bundleSizeKb`
  - `system.bundleSizeDetail` populated with total/gzip/brotli/largest chunk/top contributors

### Producer contract

The **test/build pipeline** produces `bundle-stats.json` as a side effect of `pnpm build`:

#### Producer: Frontend build step

**Requirement:** Running `pnpm build` must produce `bundle-stats.json` at a stable path:
- Configure Vite / Rollup to include `rollup-plugin-visualizer`
- Visualizer must output JSON to one of:
  - `webui/dist/bundle-stats.json` (preferred)
  - `frontend/dist/bundle-stats.json` (fallback)
  - `metrics/dashboard/dist/bundle-stats.json` (fallback)

#### Consumer: Metrics bundle collector

**Requirement:** After producer is ready:
- Set `bundle_size.enabled: true` in `metrics/state/extensions.json`
- Run metrics collection
- Dashboard will show numeric bundle size values

### Work items

1. **Update build configuration:** Done
2. **Enable collector:** Done
3. **Document handover:** Done

### Testable acceptance criteria

**For producer:**
- `pnpm build` completes without errors
- Valid `bundle-stats.json` appears at one of the three candidate paths

**For consumer:**
- `modules.optional_collectors.collectors.bundle_size.status == "available"`
- Dashboard `system.bundleSizeKb` is numeric (not null)
- Dashboard `system.bundleSizeDetail` includes all expected fields

---

## Chunk 5: Dependency graph actionable UX

Implementation status: Implemented (2026-04-05)

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

## Chunk 8: Build Cost & Schema Guardrails (Non-blocking)

Implementation status: Backlog (non-blocking)

### Goal
Keep bundle metrics sustainable over time by managing build overhead and guarding against upstream schema drift.

### Scope note
This chunk is intentionally non-blocking and does not gate Chunk 3A/3B, 6, or 7 delivery.

### Work items

- Add build cost awareness controls for bundle stats generation, such as:
  - a `--metrics` or CI-only enablement flag
  - optional caching/reuse of visualizer output when inputs are unchanged
- Keep parser compatibility protection explicit and tested:
  - retain fixture-based parser tests for `bundle-stats.json`
  - ensure schema drift failures remain actionable and visible in test output

### Testable acceptance criteria

- Build can run in a mode that skips bundle stats generation when metrics are not required.
- CI metrics mode continues to emit `bundle-stats.json` and keeps Chunk 4 behavior intact.
- Parser fixture tests fail clearly on schema changes and identify the compatibility break.

---

## 4. Execution order and batching — REVISED

Updated execution order (as of 2026-04-06 drift review):

1. ✅ **Chunk 0** (contract hardening) — DONE
2. ✅ **Chunk 1** (sparkline correctness) — DONE
3. ✅ **Chunk 2** (Python complexity enablement) — DONE
4. ✅ **Chunk 5** (dependency graph actionable UX) — DONE
5. ✅ **Pipeline support** (build -> bundle-stats.json) — DONE
6. ✅ **Chunk 4** (bundle analysis) — DONE
7. ✅ **Chunk 3A** (design Sonar) — DONE
8. ✅ **Chunk 3B** (implement Sonar) — DONE
9. 📋 **Chunk 6** (optional collector hardening) — **NEXT**
10. ⏳ **Chunk 7** (new metric expansion) — after 1 and 6 are done
11. 🧩 **Chunk 8** (build cost and schema guardrails) — non-blocking hardening follow-up

Rationale:
- **Chunk 2 and Chunk 5 are complete:** keep only regression checks, no new implementation work required there
- **Pipeline support and Chunk 4 are complete:** bundle metrics now have a producer/consumer contract and verified data flow
- **Chunk 3A and 3B are complete:** Sonar design, collector code, regression tests, and dashboard payload wiring are in place
- **Chunk 6 is now the next delivery target:** use it to harden collector readiness and reduce avoidable `partial`/`not_available` states across the dashboard
- **Chunk 8 is non-blocking hardening:** optimize build overhead and preserve schema-compatibility safeguards without gating delivery

---

## 5. Collector Health Requirements

To ensure the metrics dashboard remains reliable and intentional, the following collector health standards must be upheld:

### Minimal availability expectations

- **Baseline collectors** (backend LOC, frontend LOC, coverage): Must be available on every run, or failure must be logged and surfaced as a critical warning
- **Complexity collectors** (once Chunk 2 & 3B complete): Must be available on every run; if unavailable, log actionable reason (e.g., "radon not installed")
- **Optional collectors** (bundle, openapi, etc.): May be unavailable; but reason must be clear and non-availability must not degrade whole-run exit status

### Dashboard provenance requirements

- **Every displayed metric must include provenance:** Fields like `coverageTrendSource` and `complexityCard.frontend.source` must be exposed in the dashboard payload
- **Synthetic/fallback metrics must be labeled:** UI must explicitly indicate when a metric is derived from heuristics or synthetic data (not measured)
- **Null/N/A handling:** When a metric is unavailable, the dashboard must show N/A with a tooltip explaining why

### Requirements for adding new collectors

- Design must define clear failure modes and non-availability reasons
- Implementation must include unit tests covering both success and graceful degradation cases
- Dashboard generator must extract and expose the `reason` field alongside numeric values
- Plan must document whether the collector is mandatory (blocks run) or optional (non-blocking)

---

## 6. Definition of done for this plan

This plan is considered complete when:

- Every chunk has an implementation PR linked from this document.
- Each chunk acceptance criteria is automated in tests where feasible.
- Dashboard can state provenance for every major metric card.
- Remaining `not_available` states are intentional and documented.
