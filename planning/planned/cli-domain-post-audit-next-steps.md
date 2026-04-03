# photo-ingress Post-Audit Next Steps Plan

Date: 2026-04-01
Status: Partially executed — Gate 4 complete; Gates 1–3 open as of 2026-04-03
Owner: Systems Engineering

## Gate execution summary (as of 2026-04-03)

| Gate | Description | Status |
|------|-------------|--------|
| 1 | Boundary fidelity M3→M4 | Open — `DownloadedHandoffCandidate` introduced but integration fixture refactoring tasks remain open |
| 2 | Operator semantics + audit coherence | Open — `test_m3_m4_operator_semantics.py` exists; invariant assertions not yet complete |
| 3 | Containerized staging environment | Open — no `deploy/compose/` stack created |
| 4 | Module 5 Live Photo V1 | ✅ Complete — all roadmap checkboxes ticked; `live_photo.py`, `live_photo_pairs` migration, and tests present |

Note: The original gate ordering (1 → 2 → 3 → 4) was not followed strictly. Module 5 was
implemented before Gates 1–3 were formally closed. Gates 1–3 remain as hardening items before
production use.

---

## Objective

Close the highest-risk gaps before Module 5 so Module 3 and Module 4 are
production-trustworthy under both mocked and real-account conditions.

## Execution principles

- Keep changes commit-sized and reversible.
- Keep test fixtures authoritative at module boundaries (no test-side DTO synthesis).
- Prefer deterministic tests first, then environment-backed tests.
- Do not start Module 5 until gates 1-3 pass.

---

## Gate 1: Boundary fidelity between Module 3 and Module 4

### Problem statement

Current integration harness reconstructs boundary objects in test code, which can
hide drift between production output and ingest input.

### Deliverables

- Introduce a single production-owned handoff contract for M3 -> M4.
- Refactor integration fixtures to consume the contract directly.
- Remove positional assumptions between reduced candidates and downloaded paths.
- Add mismatch detection/assertions for candidate count and staged paths.

### Concrete tasks

- [ ] Add boundary DTO/schema module under `src/nightfall_photo_ingress/runtime/` or `src/nightfall_photo_ingress/domain/`.
- [ ] Update `tests/integration/conftest.py` to avoid reconstructing staged candidates.
- [ ] Add explicit test for ordering-agnostic candidate-path association.
- [ ] Add explicit ghost/tombstone + downloadable mixed-page scenario.

### Exit criteria

- [ ] No integration fixture synthesizes Module 4 input from raw page items.
- [ ] Boundary mapping is validated by contract tests.
- [ ] Compliance findings "synthetic handoff" and "positional zip coupling" are closed.

---

## Gate 2: Operator semantics and audit coherence tests

### Problem statement

Integration coverage currently under-asserts operator-facing summaries and terminal
audit coherence (actor/reason/remediation alignment).

### Deliverables

- Rich assertions for terminal outcomes: accepted/discarded/quarantined/replayed.
- Cross-surface coherence checks (summary output vs. audit rows vs. run ids).
- Stronger invariant tests for accepted queue, registry state, and journal evidence.

### Concrete tasks

- [ ] Extend `tests/integration/test_m3_m4_operator_semantics.py` with actor/reason/run-id assertions.
- [ ] Add invariant tests for "accepted without registry finalization" and inverse state.
- [ ] Assert replay vs. quarantine are distinguishable in operator-visible summaries.
- [ ] Add deterministic checks for batch digest totals.

### Exit criteria

- [ ] Invariant 1-6 from audit document are covered with explicit assertions.
- [ ] Cases 8, 17, 19, 23, 26 move from partial to full where feasible.
- [ ] Compliance audit addendum shows no High findings in operator/audit semantics.

---

## Gate 3: Containerized staging environment + first real-account integration run

### Problem statement

Mocked tests are strong but not sufficient for early production confidence on
Graph behavior, token lifecycle, and storage semantics.

### Deliverables

- Reproducible containerized staging stack for M3+M4 smoke tests.
- One Azure account wired for controlled, non-destructive integration runs.
- Baseline runbook and artifact capture for failures.

### Environment proposal

- `docker compose` with services:
  - `photo-ingress-runner` (Python 3.11, mounted config + state dirs)
  - `azurite` optional (for local artifact simulation only, not Graph)
  - `logs-collector` optional sidecar for JSON log snapshots
- Host-mounted volumes:
  - `/tmp/photo-ingress-staging`
  - `/tmp/photo-ingress-accepted`
  - `/tmp/photo-ingress-state`

### Concrete tasks

- [ ] Create `deploy/compose/staging-compose.yml`.
- [ ] Add staging config template under `conf/` for single account smoke runs.
- [ ] Add `scripts/staging/run-smoke.sh` to execute `auth-setup`, `poll`, and assertions.
- [ ] Add smoke test checklist (download success, dedupe, replay idempotency, redacted logs).

### Exit criteria

- [ ] First successful authenticated run against one Azure account completed.
- [ ] Evidence captured: run id, counters, audit rows, staging/accepted state snapshots.
- [ ] No secret leakage in logs.

---

## Gate 4: Module 5 implementation (Live Photo V1)

### Scope

Implement Live Photo pairing as defined in roadmap and decisions with V1 default
heuristics enforced and compatibility surface exposed.

### Concrete tasks

- [x] Add `live_photo_pairs` schema migration.
- [x] Implement pairing detector + deferred queue.
- [x] Enforce V1 default-only runtime values with explicit validation errors for others.
- [x] Ensure reject/accept propagation across pair members.
- [x] Add unit + integration tests from Module 5 roadmap section.

### Exit criteria

- [x] Module 5 unit/integration tests are green.
- [x] Pair provenance visible in registry and audit output.
- [x] Rejected pair re-upload block behavior confirmed.

---

## Additional recommended idea

### Deterministic time control for recovery/staleness tests

Introduce a clock abstraction used by stale-file classification, replay windows,
and drift thresholds.

- [ ] Add `Clock` protocol with default system implementation.
- [ ] Provide frozen clock fixture for integration tests.
- [ ] Remove wall-clock dependency from stale/replay assertions.

Expected benefit:
- Lower flakiness and clearer semantics for crash/recovery tests.

---

## Suggested order of work

1. Gate 1 (boundary fidelity)
2. Gate 2 (operator semantics + audit coherence)
3. Gate 3 (containerized real-account smoke)
4. Gate 4 (Module 5)
5. Optional deterministic clock hardening
