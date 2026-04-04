from __future__ import annotations

import json
from pathlib import Path


def test_snapshot_create_only_in_prepare_like_mappings() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    mappings = model["mappings"]

    allowed_with_snapshot_create = {
        "devcontainer.prepare",
    }

    for mapping_name, commands in mappings.items():
        has_snapshot_create = "./dev/devctl snapshot-create" in commands
        if mapping_name in allowed_with_snapshot_create:
            assert has_snapshot_create, f"{mapping_name} must include snapshot-create"
        else:
            assert not has_snapshot_create, (
                f"{mapping_name} must not include snapshot-create; use reset-based loops instead"
            )


def test_web_test_unit_mapping_uses_reset_fast_loop() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    commands = model["mappings"]["web.test.unit"]

    assert "./dev/devctl reset" in commands
    assert "./dev/devctl assert-cached-ready" in commands
    assert "./dev/devctl test-web-typecheck" in commands
    assert "./dev/devctl test-metrics-dashboard-typecheck" in commands
    assert "./dev/devctl snapshot-create" not in commands


def test_devctl_does_not_install_web_deps_during_runtime_checks() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    devctl_text = (workspace_root / "dev" / "devctl").read_text(encoding="utf-8")

    typecheck_block = devctl_text.split("cmd_test_web_typecheck()", 1)[1].split("cmd_test_web_e2e()", 1)[0]
    unit_block = devctl_text.split("cmd_test_web_unit()", 1)[1].split("cmd_test_web_typecheck()", 1)[0]

    assert "npm install --save-dev" not in typecheck_block
    assert "npm install --save-dev" not in unit_block


def test_bootstrap_webui_syncs_only_manifests() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    devctl_text = (workspace_root / "dev" / "devctl").read_text(encoding="utf-8")
    bootstrap_block = devctl_text.split("cmd_bootstrap_webui()", 1)[1].split("cmd_bootstrap_playwright()", 1)[0]

    assert "_sync_webui_manifests" in bootstrap_block
    assert "_sync_webui_sources" not in bootstrap_block
