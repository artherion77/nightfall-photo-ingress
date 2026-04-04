from __future__ import annotations

from pathlib import Path

from tests.integration.system_demo.harness import (
    DemoBrowserHarness,
    run_variant_b_demo,
    variant_b_browser_contracts,
)


def test_variant_b_contracts_are_layered_and_rationale_complete() -> None:
    contracts = variant_b_browser_contracts()

    assert len(contracts) == 3
    for contract in contracts:
        assert contract.rationale.selected_layer == "playwright"
        assert contract.rationale.candidate_layers_considered == ("pytest", "vitest", "playwright")
        assert contract.rationale.why_lower_layers_are_insufficient
        assert "artifact-path-output" in contract.rationale.flake_risk_controls


def test_demo_harness_executes_all_browser_scenarios(tmp_path: Path) -> None:
    harness = DemoBrowserHarness(artifact_root=tmp_path / "artifacts")
    results = run_variant_b_demo(harness)

    assert [result.scenario_id for result in results] == [
        "staging.keyboard-triage.spec.ts",
        "blocklist.delete-confirm.spec.ts",
        "blocklist.delete-error-feedback.spec.ts",
    ]
    assert all(result.passed for result in results)
    assert all(Path(result.artifact_path).exists() for result in results)

    # Demonstrates browser-only value points from Variant B gap analysis.
    assert "keydown:ArrowRight" in harness.events
    assert "dialog:open" in harness.events
    assert "error-feedback:visible" in harness.events
