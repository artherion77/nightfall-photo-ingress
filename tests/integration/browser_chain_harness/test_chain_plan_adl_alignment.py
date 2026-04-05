from __future__ import annotations

import json
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_adl_variant_b_matches_plan_and_consolidation() -> None:
    root = Path(__file__).resolve().parents[3]

    adl = _read(root / "design" / "rationale" / "architecture-decision-log.md")
    plan = _read(root / "planning" / "implemented" / "e2e-test-architecture-migration-plan.md")
    consolidation = _read(root / "design" / "rationale" / "e2e-test-architecture-consolidation.md")

    assert "Variant B" in adl
    assert "Status: accepted" in adl

    for chunk_id in range(1, 8):
        assert f"## Chunk {chunk_id}:" in plan
        assert "Status: Completed (2026-04-04)" in plan

    assert "Recommendation: Variant B" in consolidation
    assert "Chunk 7 delivery note" in consolidation


def test_variant_b_contract_is_backed_by_real_devctl_and_mcp_mappings() -> None:
    root = Path(__file__).resolve().parents[3]

    devctl = _read(root / "dev" / "bin" / "devctl")
    model = json.loads(_read(root / ".mcp" / "model.json"))

    assert "cmd_test_web_unit" in devctl
    assert "cmd_test_web_e2e" in devctl
    assert "E2E_ARTIFACT_PATH=" in devctl

    assert model["mappings"]["web.test.e2e"][-1] == "./dev/bin/devctl test-web-e2e"
    assert model["mappings"]["web.test.integration"][-1] == "./dev/bin/devctl test-web-e2e"
