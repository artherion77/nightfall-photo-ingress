from __future__ import annotations

import json
from pathlib import Path


def test_prepare_like_mappings_do_not_use_snapshot_create() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    mappings = model["mappings"]

    for mapping_name, commands in mappings.items():
        has_snapshot_create = "./dev/bin/devctl snapshot-create" in commands
        assert not has_snapshot_create, (
            f"{mapping_name} must not include snapshot-create; use update/setup/reset flows"
        )


def test_web_test_unit_mapping_uses_govctl_fast_loop() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    commands = model["mappings"]["web.test.unit"]
    direct_commands = model["mappings"]["web.test.unit.direct"]

    assert commands == ["./dev/bin/govctl web.test.unit --json"]

    assert "./dev/bin/devctl reset" in direct_commands
    assert "./dev/bin/devctl assert-cached-ready" in direct_commands
    assert "./dev/bin/devctl test-web-typecheck" in direct_commands
    assert "./dev/bin/devctl test-metrics-dashboard-typecheck" in direct_commands
    assert "./dev/bin/devctl snapshot-create" not in commands


def test_devctl_commands_include_update_and_check_and_drop_legacy_commands() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    commands = model["devctl"]["commands"]

    assert "update" in commands
    assert "check" in commands

    assert "create" not in commands
    assert "snapshot-create" not in commands
    assert "snapshot-refresh" not in commands


def test_devcontainer_mappings_include_check_and_update() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    model = json.loads((workspace_root / ".mcp" / "model.json").read_text(encoding="utf-8"))
    mappings = model["mappings"]

    assert mappings["devcontainer.check"] == ["./dev/bin/devctl check"]
    assert mappings["devcontainer.update"] == ["./dev/bin/devctl update"]


def test_devctl_does_not_install_web_deps_during_runtime_checks() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    devctl_text = (workspace_root / "dev" / "bin" / "devctl").read_text(encoding="utf-8")

    typecheck_block = devctl_text.split("cmd_test_web_typecheck()", 1)[1].split("cmd_test_web_e2e()", 1)[0]
    unit_block = devctl_text.split("cmd_test_web_unit()", 1)[1].split("cmd_test_web_typecheck()", 1)[0]

    assert "npm install --save-dev" not in typecheck_block
    assert "npm install --save-dev" not in unit_block


def test_setup_bootstraps_both_web_stacks_via_install_stack() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    devctl_text = (workspace_root / "dev" / "bin" / "devctl").read_text(encoding="utf-8")
    setup_block = devctl_text.split("cmd_setup()", 1)[1].split("cmd_destroy()", 1)[0]

    assert "_install_stack webui" in setup_block
    assert "_install_stack dashboard" in setup_block
