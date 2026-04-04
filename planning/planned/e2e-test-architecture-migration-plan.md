# E2E Test Architecture Migration Plan

Status: Planned
Date: 2026-04-04
Scope: Execute Sections 4 and 5 from the E2E test architecture consolidation as deterministic, chunk-oriented execution units.

Source baseline:
- [E2E test architecture consolidation](../../design/rationale/e2e-test-architecture-consolidation.md)
- Section 4: Integration Plan (Devcontainer + devctl + MCP)
- Section 5: Migration Plan + Policy

## Chunk 1: Tooling Contract Normalization

### Goal
Define strict, non-placeholder execution contracts for frontend test commands and MCP mappings.

### Inputs
- [dev/devctl](../../dev/devctl)
- [.mcp/model.json](../../.mcp/model.json)
- [design/rationale/e2e-test-architecture-consolidation.md](../../design/rationale/e2e-test-architecture-consolidation.md)

### Steps
1. Define target behavior for `devctl test-web-unit` without a placeholder-pass fallback.
2. Define `devctl test-web-e2e` command contract (arguments, exit semantics, artifact path output).
3. Define MCP mappings for `web.test.e2e` and a real `web.test.integration` execution path.
4. Record pass/fail criteria and expected logs for each command.

### Acceptance Criteria
- A written command contract exists for `test-web-unit`, `test-web-e2e`, and MCP task mappings.
- No command contract includes placeholder success semantics.
- Command contracts are deterministic and produce unambiguous exit behavior.

### Non-Goals
- Implementing or editing scripts.
- Installing dependencies.

---

## Chunk 2: Directory and Naming Conventions

### Goal
Define stable repository structure and naming conventions for Vitest and Playwright tests.

### Inputs
- [webui](../../webui)
- [design/rationale/e2e-test-architecture-consolidation.md](../../design/rationale/e2e-test-architecture-consolidation.md)

### Steps
1. Define target test directories:
- `webui/tests/component/`
- `webui/tests/e2e/`
- `webui/tests/e2e/fixtures/`
2. Define naming conventions:
- Playwright: `<feature>.<behavior>.spec.ts`
- Vitest: `<component>.test.ts`
3. Define selector and fixture naming conventions.
4. Define metadata header conventions for test files (scope, risk class, owner).

### Acceptance Criteria
- Directory map and naming rules are documented and unambiguous.
- Conventions clearly separate component vs browser test ownership.
- Rules are concise enough to apply in a single implementation turn.

### Non-Goals
- Creating test files.
- Changing CI or scripts.

---

## Chunk 3: Minimal Initial Browser Suite Definition

### Goal
Specify 2-3 highest-value Playwright scenarios with deterministic test contracts.

### Inputs
- [webui/src/routes/staging/+page.svelte](../../webui/src/routes/staging/+page.svelte)
- [webui/src/lib/components/staging/PhotoWheel.svelte](../../webui/src/lib/components/staging/PhotoWheel.svelte)
- [webui/src/routes/blocklist/+page.svelte](../../webui/src/routes/blocklist/+page.svelte)
- [webui/src/lib/components/common/ConfirmDialog.svelte](../../webui/src/lib/components/common/ConfirmDialog.svelte)

### Steps
1. Define scenario 1: staging triage keyboard path (ArrowLeft/ArrowRight + A/R/D).
2. Define scenario 2: blocklist delete confirm/cancel semantics.
3. Define scenario 3: visible error feedback path for forced API failure.
4. For each scenario, define deterministic preconditions, assertions, and teardown behavior.

### Acceptance Criteria
- Exactly 2-3 scenarios are documented with explicit assertions and pass/fail outcomes.
- Each scenario targets a browser-only defect class not covered by pytest integration.
- Scenarios are small enough for one implementation turn each.

### Non-Goals
- Writing Playwright tests.
- Expanding to a full browser regression matrix.

---

## Chunk 4: CI and MCP Rollout Plan

### Goal
Define staged rollout for browser tests with clear blocking policy and artifact handling.

### Inputs
- [.mcp/model.json](../../.mcp/model.json)
- Existing CI/test workflow docs and scripts

### Steps
1. Define rollout phase 1: non-blocking browser smoke on PRs, blocking on nightly/main.
2. Define rollout phase 2: merge-blocking browser smoke after stability threshold is reached.
3. Define artifact retention policy: traces/screenshots only on failure.
4. Define MCP task output requirements for artifact discoverability.

### Acceptance Criteria
- Rollout policy includes phase boundaries and promotion criteria.
- Blocking/non-blocking transitions are objective and measurable.
- Artifact policy is explicit and bounded.

### Non-Goals
- Editing CI pipeline files.
- Executing browser tests in CI.

---

## Chunk 5: Rollback and Stabilization Plan

### Goal
Define deterministic rollback triggers and stabilization actions if the browser layer degrades reliability.

### Inputs
- Metrics policy from Chunk 4
- Baseline pytest gate behavior

### Steps
1. Define rollback trigger conditions (runtime/flakiness threshold breaches).
2. Define rollback actions:
- demote browser tests to non-blocking,
- reduce scope to one critical smoke flow,
- open a stabilization task list.
3. Define re-promotion criteria after stabilization.

### Acceptance Criteria
- Rollback criteria are objective and enforceable.
- Rollback preserves existing pytest gate confidence.
- Re-promotion path is explicit.

### Non-Goals
- Performing rollback in CI.
- Changing test implementation.

---

## Chunk 6: Evaluation Metrics and Decision Review

### Goal
Operationalize success metrics for DX, runtime, flakiness, and defect yield.

### Inputs
- Runtime baselines from pytest loops
- Planned browser suite definition (Chunk 3)

### Steps
1. Define DX metrics:
- cold and warm local run time,
- time-to-diagnose failed UI regressions,
- developer friction feedback.
2. Define quality metrics:
- defects uniquely found by browser layer,
- flaky failure ratio,
- false-positive ratio.
3. Define cost metrics:
- CI duration delta,
- artifact storage growth,
- maintenance overhead.
4. Define evaluation cadence (for example, 2-3 week windows).

### Acceptance Criteria
- Metrics are measurable and attributable to the browser layer.
- A formal Go/No-Go review checklist exists based on collected metrics.
- Review cadence and owners are defined.

### Non-Goals
- Running the evaluation.
- Automating metric collection in this chunk.

---

## Chunk 7: Future Test Policy Finalization (LLM-Usable)

### Goal
Provide a strict test-layer policy for future human and LLM contributors.

### Inputs
- [design/rationale/e2e-test-architecture-consolidation.md](../../design/rationale/e2e-test-architecture-consolidation.md)
- Outcomes from Chunks 1-6

### Steps
1. Define default layer routing policy:
- pytest by default,
- Vitest for component/store isolation,
- Playwright for browser-only semantics.
2. Define explicit "do not use Playwright" cases.
3. Define anti-flakiness rules (selectors, waits, deterministic fixtures).
4. Define over-testing guardrail (defect class and cheapest reliable layer checks).
5. Define LLM decision heuristic and required rationale style.

### Acceptance Criteria
- Policy is concise, enforceable, and test-layer specific.
- Policy prevents unnecessary Playwright expansion.
- Policy is executable as review criteria for future PRs/Claude turns.

### Non-Goals
- Enforcing policy via automation.
- Retrofitting old tests.

---

## Execution Order Summary

1. Chunk 1: Tooling contracts
2. Chunk 2: Directory and naming
3. Chunk 3: Minimal browser suite definition
4. Chunk 4: CI/MCP rollout policy
5. Chunk 5: Rollback/stabilization policy
6. Chunk 6: Metrics and review model
7. Chunk 7: Final policy for future contributors

The sequence is deterministic and minimizes ambiguity: contracts first, scope second, rollout controls third, governance last.
