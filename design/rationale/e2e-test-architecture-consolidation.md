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
