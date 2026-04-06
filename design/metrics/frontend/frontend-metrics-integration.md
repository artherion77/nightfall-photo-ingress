# Frontend Cognitive Complexity: System Integration

Status: Implemented
Date: 2026-04-06
Owner: Systems Engineering
Purpose: Define collector integration with metrics pipeline, dashboard, and devctl runtime

Implementation status:

- Collector implementation is live in `metrics/runner/frontend_collector.py`
- Dashboard payload integration is live in `metrics/runner/dashboard_generator.py`
- Latest artifacts show `source: "sonar_cognitive"` and dashboard provenance fields populated
- Current runtime caveat: `.svelte` files still parse through JS grammar fallback, so Svelte-heavy runs can remain `partial`

## 1. Collector Integration Architecture

### 1.1 System context

The frontend cognitive complexity collector is a new optional module in the metrics pipeline:

- **Input:** `webui/` source tree snapshot (from container or host)
- **Output:** JSON payload under `modules.frontend.metrics.cognitive_complexity` in metrics artifact
- **Trigger:** Called by `metricsctl-runner` as part of frontend metrics collection phase
- **Container environment:** Runs inside LXC devctl container (tree-sitter + Python environment available)
- **Failure mode:** Non-fatal; if collection fails, whole run continues with `status: error`

### 1.2 Pipeline flow

```
metricsctl-runner (orchestrator)
    ↓
[collect-backend] → modules.backend
[collect-frontend] ← new cognitive complexity collector
[collect-optional-*] (bundle, openapi, etc.)
    ↓
[aggregate] → combine all module outputs
    ↓
[generate-dashboard] → render + publish
```

Frontend cognitive complexity collector is invoked as part of `collect-frontend` phase.

## 2. Collector Invocation

### 2.1 Command surface

**Container invocation:**

```bash
# Inside devctl container
./dev/bin/metricsctl collect-frontend --run-id <id> 2>&1 | tee logs/frontend-<id>.log
```

**Implemented entry point:** `metrics/runner/frontend_collector.py`

**Invocation pattern:**

```python
python -m metrics.runner collect_frontend \
    --webui-root ./webui \
    --run-id <run_id> \
    --output-path ./artifacts/metrics/<run_id>/modules.json
```

### 2.2 Configuration

Current implementation does not gate frontend cognitive complexity through `metrics/state/extensions.json`.

- The collector runs whenever `collect-frontend` is invoked and eligible frontend files are present
- `not_available` is currently used for "no eligible files found"
- Config-driven enable/disable behavior remains a future hardening option, not a verified implementation detail

### 2.3 Exit semantics

- Collector returns exit code 0 on success (even if parse errors occurred).
- Parse errors are reported in payload as `failures[]` with `status: partial`.
- Fatal runtime errors (e.g., missing tree-sitter) return non-zero exit code; orchestrator propagates failure.

## 3. Payload Contract and Versioning

### 3.1 Schema

Core payload structure:

```json
{
  "modules": {
    "frontend": {
      "metrics": {
        "cognitive_complexity": {
          "source": "sonar_cognitive",
          "status": "available|partial|not_available|error",
          "version": "1.0",
          "parser_info": {
            "library": "tree-sitter",
            "library_version": "0.25.2",
            "grammar_js": "0.25.0",
            "grammar_ts": "0.23.2",
            "grammar_svelte": "0.25.0"
          },
          "mean": 7.4,
          "file_count": 42,
          "failed_file_count": 1,
          "files": [
            {
              "path": "webui/src/routes/+page.svelte",
              "language": "svelte",
              "function_count": 3,
              "file_total": 19,
              "file_mean": 6.33,
              "functions": [
                {
                  "name": "loadDashboard",
                  "start_line": 24,
                  "end_line": 88,
                  "cognitive_complexity": 11
                }
              ]
            }
          ],
          "failures": [
            {
              "path": "webui/src/lib/broken.svelte",
              "reason": "parse_error",
              "detail": "unexpected token at line 17",
              "remediation": "fix syntax error or exclude file"
            }
          ],
          "collection_time_ms": 5843
        }
      }
    }
  }
}
```

### 3.2 Status semantics

- **`available`:** All eligible files parsed and scored; zero failures.
- **`partial`:** Scores present; at least one file failed to parse.
- **`not_available`:** No eligible files found under `webui/`, or collector explicitly disabled.
- **`error`:** Collector runtime failed before analysis (missing toolchain, permission error, etc.).

### 3.3 Versioning and evolution

**Payload version field:** `"version": "1.0"` — incremented only on breaking changes.

**Backward compatibility:**
- New fields added as optional; missing fields default to null.
- Dashboard generator must handle missing optional fields without crashing.
- Parser info is optional in v1.0 (added for v1.1 if needed).

**Migration policy:**
- If payload schema changes (e.g., new required field), bump version to 2.0.
- Bump parser_info library_version when tree-sitter or grammar updates occur.
- Treat minor grammar patches (0.20.7 → 0.20.8) as compatible; major bumps (0.20 → 0.21) signal potential score changes.

## 4. Dashboard Integration

### 4.1 Rendering semantics

Frontend cognitive complexity renders as a first-class metric adjacent to backend complexity:

```
┌─────────────────────────────────────┐
│ Backend Complexity     │ Frontend CC │
│                        │             │
│ Cyclomatic: 5.2        │ Cognitive:  │
│ Maintainability: 71    │ 7.4 (42)    │
└─────────────────────────────────────┘
```

### 4.2 Provenance labeling

Dashboard payload exposes:

```json
{
  "complexityCard": {
    "backend": { ... },
    "frontend": {
      "value": 7.4,
      "source": "sonar_cognitive",
      "parser_version_label": "tree-sitter 0.20.8",
      "status": "available"
    }
  }
}
```

Dashboard **must** display provenance when rendering; no implicit source.

### 4.3 N/A and error handling

| Status | Display | Tooltip |
|--------|---------|---------|
| `available` | Numeric score + unit | Show parser version info |
| `partial` | Numeric score + ⚠️ | "Parsed 41/42 files; 1 parse error" |
| `not_available` | N/A | "Collector disabled or no eligible files" |
| `error` | N/A | Failure detail from payload |

### 4.4 No synthetic fallback

- Do **not** compute or display a heuristic frontend complexity score when data unavailable.
- If `status != available`, show N/A only.

## 5. Failure Modes and Propagation

### 5.1 Expected failure classes

| Failure | Handling |
|---------|----------|
| Parser unavailable (tree-sitter not installed) | Fatal; return error status |
| Parse error on single file | Per-file failure; continue; degrade to `partial` |
| Unsupported syntax (e.g., new ES2024 feature) | Per-file failure |
| File read/decode error (permission, encoding) | Per-file failure |
| Collector runtime exception (OOM, timeout) | Fatal; return error status |

### 5.2 Aggregation policy on partial failures

- When some files fail to parse, continue collecting others.
- Final status is `partial` (not error).
- Report all failures in `failures[]` array with reason and detail.
- Compute `mean` across successfully parsed files only.

### 5.3 Propagation to orchestrator

- `status: available` → orchestrator continues normally.
- `status: partial` → orchestrator logs warning; continues normally.
- `status: not_available` → no warning; continues normally (expected state if disabled).
- `status: error` → orchestrator may stop whole run or mark run as degraded.

### 5.4 Remediation hints

Every failure entry includes a `remediation` field with actionable text:

```json
{
  "path": "webui/src/broken.svelte",
  "reason": "parse_error",
  "detail": "unexpected token at line 17: got `!@#` expected identifier",
  "remediation": "Fix syntax error or add file to exclude list in metrics config"
}
```

## 6. Interaction with Bundle Pipeline (Chunk 4)

### 6.1 Sequencing

Frontend cognitive complexity collection happens **after** the frontend build pipeline:

```
webui/ (source tree)
    ↓
[pnpm build] → generates bundle-stats.json
    ↓
[collect-frontend] ← cognitive complexity on source
              ↓ (separate path)
[collect-optional: bundle] ← reads bundle-stats.json artifact
```

### 6.2 No coupling

- Cognitive complexity collector does **not** depend on bundle output.
- Bundle stats do not affect cognitive scores.
- Both are independent optional collectors reporting under `modules.frontend.metrics.*`.

### 6.3 Artifact layout

```
artifacts/
  metrics/
    <run_id>/
      modules.json
        ├── modules.backend.metrics.complexity
        ├── modules.frontend.metrics.cognitive_complexity  ← this design
        ├── modules.optional_collectors.collectors.bundle_size
        └── ...
```

## 7. Test Infrastructure

### 7.1 Unit tests

Implemented regression coverage is centered on:

- `tests/unit/test_metrics_module3_frontend.py`
- `tests/unit/test_cognitive_complexity.py`

**Coverage:**
- Function-level scoring rules using inline JavaScript snippets
- Project/file aggregation behavior
- Parse errors and graceful degradation
- Parser metadata presence
- Per-file output contract used by dashboard breakdowns
- Frontend collection artifact writing

**Integration expectations:**
- Dashboard generator consumes collector output without error
- Live dashboard payloads expose provenance through `complexityCard.frontend.*`

### 7.2 Test coverage notes

- No fixture-tree plus snapshot harness is currently checked in for this collector
- Deterministic expectations are covered by rule-based unit tests rather than snapshot files
- Dedicated Svelte success fixtures remain a gap while `.svelte` parsing is still incomplete

## 8. Regression Assurance

### 8.1 Existing tests unaffected

- `tests/unit/test_metrics_module2_backend.py`: must pass with no changes.
- `tests/unit/test_metrics_module5_dashboard.py`: must pass; dashboard rendering handles missing optional fields.
- `tests/unit/test_metrics_module8_optional_collectors.py`: bundle collector must remain functional.

### 8.2 New module tests

Chunk 3B implementation adds `test_metrics_module3_frontend.py` which passes if:
- Scores match the implemented rule set for representative inline samples.
- Parser metadata and per-file outputs are present.
- Parser version is included in payload.
- Failure handling is graceful.

## 9. Devctl Runtime Considerations

### 9.1 Container setup

Frontend cognitive complexity collector requires:

- Python 3.9+
- tree-sitter library (pinned version in `requirements.txt`)
- Bundled grammar packages for JS/TS; `.svelte` currently uses JS grammar fallback

Container startup includes:
```bash
pip install -r metrics/requirements.txt
```

### 9.2 Source sync

Before collection:

```bash
devctl sync ./webui → /home/runner/workspace/webui
```

Collector reads from container's `/home/runner/workspace/webui`.

### 9.3 Performance in container

- AST parsing + traversal for 42 files: expect 5–15 seconds.
- Timeout: collector should complete within 60 seconds.
- If collection exceeds 30 seconds, emit warning to metrics log for visibility.

## 10. Migration and Rollout Plan

### 10.1 Phased availability

- **Phase 1:** Design completed.
- **Phase 2:** Collector implemented and included in `collect-frontend`.
- **Phase 3 (current):** Dashboard payload and UI provenance wiring are live.
- **Phase 4 (next hardening):** Improve `.svelte` parsing coverage and any optional config gating.

### 10.2 Gradual dashboard adoption

- Initially, frontend complexity and backend complexity render side-by-side without cross-referencing.
- Dashboard copy explicitly states source and parser version to avoid confusion.
- No synthetic complexity fallback; metric is either measured or N/A.

---

## Reference: Acceptance Criteria for Implementation

Frontend cognitive complexity collector implementation is correct when:

1. **Schema:** Payload matches contract; `source: "sonar_cognitive"`; parser_info included.
2. **Determinism:** Fixed inputs produce stable scores across rule-based tests.
3. **Tests:** Algorithm changes produce unit-test failures in the current suite.
4. **Svelte support:** This remains only partially satisfied in live runs; `.svelte` parse coverage is an active hardening gap.
5. **Failure handling:** Partial failures produce `status: partial`; full failures produce `error`.
6. **Dashboard:** Frontend complexity appears with provenance label; N/A states include reason.
7. **Regressions:** Existing module2/module5/module8 tests pass; no breaking changes to pipeline.
