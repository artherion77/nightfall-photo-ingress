# E2E Test Architecture Consolidation

Status: Active analysis baseline
Date: 2026-04-04
Scope: Test architecture consolidation for nightfall-photo-ingress

Related documents:
- [Execution migration plan](../../planning/planned/e2e-test-architecture-migration-plan.md)
- [Architecture decision log](architecture-decision-log.md)

## 1. Current Test Architecture (Matrix)

Current state, verified in the repository:

- The Python test stack is broad, mature, and fast.
- Current web UI tests are API/state-driven, not browser-driven.
- Playwright/Vitest setup exists in devctl and MCP scaffolding, but there is no established web test suite in the web project yet.

Evidence:
- Python configuration and test paths: [pyproject.toml](../../pyproject.toml)
- Unit/integration suites: [tests/unit](../../tests/unit), [tests/integration](../../tests/integration)
- UI integration tests (pytest): [tests/integration/ui](../../tests/integration/ui)
- API integration tests (pytest + ASGI/httpx): [tests/integration/api](../../tests/integration/api), [tests/integration/api/conftest.py](../../tests/integration/api/conftest.py)
- Dev container lifecycle (LXC-based): [dev/devctl](../../dev/devctl), [docs/deployment/dev-container-workflow.md](../../docs/deployment/dev-container-workflow.md)
- MCP mappings/tasks: [.mcp/model.json](../../.mcp/model.json)

Measured runtime in this analysis turn:
- Integration API+UI: 49 passed in 3.03s, elapsed 3.78s
- Unit: 289 passed in 11.86s, elapsed 12.34s

Domain x test type x tool x coverage

| Domain | Test Type | Tooling | Current Coverage |
|---|---|---|---|
| Backend domain/CLI/registry/OneDrive | Unit | pytest | Very high (289 tests in tests/unit) |
| Backend API | Integration | pytest + anyio + httpx ASGITransport | High (auth, health, staging, audit, config, triage, blocklist) |
| Ingest/flow | Integration (no browser) | pytest | High (many cross-module flows in tests/integration) |
| UI contract (dashboard/staging/audit/settings/blocklist) | Integration simulation | pytest against API + SPA fallback | Medium to good for data/flow, but no DOM-level checks |
| Staging live/prod-like | E2E/smoke + partially interactive | stagingctl/flowctl + pytest contracts | Present, but not browser E2E |
| Web component/DOM unit | Unit/component | Vitest/Testing Library | Practically absent (no active test files/config in webui) |
| Browser E2E | E2E | Playwright | Not implemented yet |

Important frontend gaps:
- No true DOM assertions (rendering, focus, CSS states, overlays, ARIA).
- Keyboard interactions are implemented but not browser-validated: [webui/src/routes/staging/+page.svelte](../../webui/src/routes/staging/+page.svelte), [webui/src/lib/components/staging/PhotoWheel.svelte](../../webui/src/lib/components/staging/PhotoWheel.svelte)
- ConfirmDialog interaction details (overlay click, stopPropagation) are not browser-tested: [webui/src/lib/components/common/ConfirmDialog.svelte](../../webui/src/lib/components/common/ConfirmDialog.svelte)
- Toast store exists, but a visible toast-rendering component is currently missing as a browser assertion target: [webui/src/lib/stores/toast.svelte.js](../../webui/src/lib/stores/toast.svelte.js)

Devcontainer/MCP/devctl status:
- devctl can install Node, Vitest, Playwright, and cache browser binaries: [dev/devctl](../../dev/devctl)
- Cache mounts are already defined (npm/pip/playwright): [dev/devctl](../../dev/devctl), [.mcp/model.json](../../.mcp/model.json)
- Chunk 1 delivery: `devctl test-web-unit` and `devctl test-web-e2e` now use strict, non-placeholder contracts with deterministic failure behavior and explicit logs/artifact path output: [dev/devctl](../../dev/devctl)
- Chunk 1 delivery: MCP mappings `web.test.e2e` and `web.test.integration` now resolve to real command paths (`./dev/devctl test-web-e2e`) without placeholder echo paths: [.mcp/model.json](../../.mcp/model.json)

## 2. Playwright Potential (Pros/Cons + Concrete Scenarios)

What Playwright would realistically improve in this project:
- Real browser event execution for keyboard/mouse/focus behavior.
- Reliable validation of overlay/dialog interaction semantics.
- Better detection of rendering and interaction regressions.
- Stronger debugging via trace/screenshot/video artifacts.

Concrete high-value scenarios with real added value:
1. Triage keyboard flow
- Validate A/R/D and ArrowLeft/ArrowRight on the real page.
- Currently covered only indirectly via API outcomes.
- Target file: [webui/src/routes/staging/+page.svelte](../../webui/src/routes/staging/+page.svelte)

2. PhotoWheel accessibility/focus behavior
- Validate role button, tabindex, Enter/Space selection behavior.
- Currently not verified at DOM level.
- Target file: [webui/src/lib/components/staging/PhotoWheel.svelte](../../webui/src/lib/components/staging/PhotoWheel.svelte)

3. Blocklist confirm/cancel dialog behavior
- Validate overlay click closes, content click remains open, confirm triggers delete.
- Current tests simulate cancel only as API-level no-delete behavior.
- Target files: [webui/src/routes/blocklist/+page.svelte](../../webui/src/routes/blocklist/+page.svelte), [webui/src/lib/components/common/ConfirmDialog.svelte](../../webui/src/lib/components/common/ConfirmDialog.svelte)

4. Error/feedback visibility
- Validate visible toast/ErrorBanner behavior and timing.
- Store logic exists, but no browser-level visual assertions.
- Target files: [webui/src/lib/stores/blocklist.svelte.js](../../webui/src/lib/stores/blocklist.svelte.js), [webui/src/lib/stores/stagingQueue.svelte.js](../../webui/src/lib/stores/stagingQueue.svelte.js)

5. End-to-end sanity for operator path
- Validate one to two primary operator workflows in a real browser.

Where pytest integration is already sufficient:
- API contracts, status codes, idempotency replay, conflict handling.
- Domain transitions and ingest enforcement.
- Fast backend regression feedback loops.
- Examples: [tests/integration/api/test_api_triage.py](../../tests/integration/api/test_api_triage.py), [tests/integration/api/test_blocklist.py](../../tests/integration/api/test_blocklist.py)

Playwright cost/risk profile:
- Additional toolchain complexity (browsers, runner, traces, CI artifacts).
- Longer runtime than 3-12 second pytest loops.
- Flakiness risk without strict wait/selector/isolation practices.
- More moving parts in devctl/MCP, even with baseline scaffolding already present.

## 3. Variant Comparison (A/B/C + Recommendation)

Variant A: pytest-only (consolidated)
- DX: Very good for backend, medium for UI
- Runtime: Very good
- Maintainability: High (single stack)
- Defect coverage: Strong for API/state, weak for DOM/interactions
- devctl+MCP complexity: Low
- Conclusion: Stable baseline, but UI blind spots remain

Variant B: pytest + selective Playwright layer
- DX: Well-balanced
- Runtime: Good to medium (small browser scope)
- Maintainability: Good (two layers, clear responsibilities)
- Defect coverage: Covers API/state plus critical UI interactions
- devctl+MCP complexity: Medium, but already scaffolded
- Conclusion: Highest value per additional complexity

Variant C: Playwright-first for UI, pytest mainly for API/domain
- DX: Medium (higher setup/debug overhead)
- Runtime: Medium to weak
- Maintainability: Medium to weak
- Defect coverage: Very good for UI, but significant migration/maintenance overhead
- devctl+MCP complexity: High
- Conclusion: Over-scaled for the current project stage

Recommendation: Variant B

Rationale in five points:
1. The current pytest suite is already fast, deep, and valuable, and should remain primary.
2. The most significant remaining gaps are browser-specific (keyboard/focus/dialog/feedback).
3. devctl and MCP already include Playwright bootstrap and cache mount scaffolding.
4. A selective browser layer controls flakiness and runtime cost.
5. This provides real UI realism where needed without forcing an architecture rewrite.

Chunk 2 delivery note (Directory and Naming Conventions):
- Planned frontend test directories are explicitly standardized as:
	- `webui/tests/component/`
	- `webui/tests/e2e/`
	- `webui/tests/e2e/fixtures/`
- Naming conventions are finalized as:
	- Playwright files: `<feature>.<behavior>.spec.ts`
	- Vitest files: `<component>.test.ts`
- Selector and fixture conventions are finalized as:
	- Prefer stable `data-testid` and role-based selectors over style/text-only selectors.
	- Keep reusable browser fixtures in `webui/tests/e2e/fixtures/` and name them by scope (`app.fixture.ts`, `api.fixture.ts`, `auth.fixture.ts`).
- Test file metadata header conventions are finalized as:
	- Include a short header with `scope`, `risk_class`, and `owner` for traceability.

Chunk 3 delivery note (Minimal Initial Browser Suite Definition):
- Scenario 1 finalized: staging triage keyboard path (`staging.keyboard-triage.spec.ts`).
	- Preconditions: route `/staging` with seeded queue of at least 3 items; first item active; network stub for triage endpoints enabled.
	- Assertions:
		- `ArrowRight` moves active card to index 1, `ArrowLeft` returns to index 0.
		- `A`, `R`, and `D` each trigger exactly one POST to accept/reject/defer endpoint for the active item.
		- After each successful action, item count decreases by 1 and active index remains bounded.
	- Teardown: restore network routing and clear seeded queue fixture.
	- Pass/fail outcome: fail on missing request, duplicate request, wrong endpoint, or index/count mismatch.
- Scenario 2 finalized: blocklist delete confirm and cancel semantics (`blocklist.delete-confirm.spec.ts`).
	- Preconditions: route `/blocklist` with one deterministic rule visible in list; delete button reachable from rule row.
	- Assertions:
		- Clicking Delete opens confirm dialog with expected title and rule pattern text.
		- Clicking Cancel closes dialog and emits no delete request.
		- Re-open dialog and click Confirm emits exactly one delete request and removes rule row from list.
		- Clicking dialog overlay closes dialog; clicking inside dialog content does not close it.
	- Teardown: reset rule fixture and clear request interceptors.
	- Pass/fail outcome: fail on any request count mismatch, unexpected close behavior, or missing row removal.
- Scenario 3 finalized: forced API failure with visible error feedback (`blocklist.delete-error-feedback.spec.ts`).
	- Preconditions: route `/blocklist`, delete dialog open for seeded rule, delete API forced to return deterministic `500` with message body.
	- Assertions:
		- Confirm action keeps rule in list after failed request (optimistic update rollback verified through visible row).
		- A visible error feedback element is shown with the API message text.
		- Error feedback is operator-discoverable within 2 seconds and remains visible long enough for assertion.
	- Teardown: restore API mock and clear error feedback state.
	- Pass/fail outcome: fail if request does not fail as configured, rollback is not visible, or no visible error feedback appears.

Implementation guard for scenario 3:
- The current web layout does not mount a toast renderer, so the implementation turn must first provide a deterministic visible error surface (for example route-level `ErrorBanner` bound to store error or a dedicated toast viewport) before adding the Playwright assertion.

Chunk 4 delivery note (CI and MCP Rollout Plan):
- Rollout phase 1 finalized (adoption/stabilization):
	- PR pipelines: browser smoke remains non-blocking, but always executes when web UI changes are detected.
	- Nightly and `main` branch validation: browser smoke is blocking.
	- Required smoke scope in phase 1 is limited to the three Chunk 3 scenarios only.
- Rollout phase 2 finalized (promotion to merge gate):
	- PR browser smoke becomes merge-blocking only after all promotion criteria are met for two consecutive evaluation windows.
	- Promotion criteria:
		- Flaky failure ratio <= 2 percent over the evaluation window.
		- Median browser smoke runtime <= 6 minutes in CI.
		- At least one browser-only defect detected or a documented risk-review confirming continued coverage value.
		- No unresolved Severity 1 tooling incidents in Playwright/devctl/MCP path.
- Artifact retention policy finalized:
	- On pass: no trace/video/screenshot artifacts retained.
	- On fail: retain trace + screenshot bundles; retain video only for failed retries.
	- Retention window: 14 days for PR artifacts, 30 days for nightly/main artifacts.
	- Storage guardrail: if weekly artifact growth exceeds policy budget, reduce retained media to trace + one screenshot per failed test.
- MCP task output requirements finalized for artifact discoverability:
	- `web.test.e2e` and `web.test.integration` task outputs must include a deterministic artifact marker line:
		- `E2E_ARTIFACT_PATH=<absolute-or-workspace-relative-path>`
	- On failed runs, MCP status/log payload must include:
		- task id,
		- phase (`phase1` or `phase2`),
		- blocking mode (`blocking` or `non_blocking`),
		- artifact path marker,
		- final exit code.
	- On successful runs, MCP output must still emit `E2E_ARTIFACT_PATH` (or explicit `E2E_ARTIFACT_PATH=none`) to keep parsing deterministic.

Rollout boundary rule:
- Chunk 4 defines policy only; CI pipeline file edits and execution enablement remain implementation work for a later chunk.
