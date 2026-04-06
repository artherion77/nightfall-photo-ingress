from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLVER = REPO_ROOT / "dev" / "lib" / "govctl_resolve.py"


def _write_manifest_json(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _run_resolver(manifest_json_path: Path, *requested: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RESOLVER),
            "--manifest-json",
            str(manifest_json_path),
            *requested,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_resolve_group_to_expected_order(tmp_path: Path) -> None:
    manifest_json = _write_manifest_json(
        tmp_path,
        {
            "version": 1,
            "defaults": {"lock": False, "timeout_seconds": 300},
            "targets": {
                "dev.ensure": {"requires_expanded": []},
                "web.typecheck": {"requires_expanded": ["dev.ensure"]},
                "web.unit": {"requires_expanded": ["web.typecheck"]},
            },
            "groups": {"test.web": {"targets": ["web.typecheck", "web.unit"]}},
            "groups_expanded": {"test.web": ["web.typecheck", "web.unit"]},
        },
    )

    result = _run_resolver(manifest_json, "test.web")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["dev.ensure", "web.typecheck", "web.unit"]


def test_resolve_diamond_dependency_order_is_deterministic(tmp_path: Path) -> None:
    manifest_json = _write_manifest_json(
        tmp_path,
        {
            "version": 1,
            "defaults": {"lock": False, "timeout_seconds": 300},
            "targets": {
                "a": {"requires_expanded": ["b", "c"]},
                "b": {"requires_expanded": ["d"]},
                "c": {"requires_expanded": ["d"]},
                "d": {"requires_expanded": []},
            },
            "groups": {},
            "groups_expanded": {},
        },
    )

    result = _run_resolver(manifest_json, "a")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["d", "b", "c", "a"]


def test_resolve_unknown_name_fails(tmp_path: Path) -> None:
    manifest_json = _write_manifest_json(
        tmp_path,
        {
            "version": 1,
            "defaults": {"lock": False, "timeout_seconds": 300},
            "targets": {"only": {"requires_expanded": []}},
            "groups": {},
            "groups_expanded": {},
        },
    )

    result = _run_resolver(manifest_json, "missing.target")

    assert result.returncode == 1
    assert "unknown target/group" in result.stderr


def test_resolve_target_with_no_dependencies_returns_itself(tmp_path: Path) -> None:
    manifest_json = _write_manifest_json(
        tmp_path,
        {
            "version": 1,
            "defaults": {"lock": False, "timeout_seconds": 300},
            "targets": {"solo": {"requires_expanded": []}},
            "groups": {},
            "groups_expanded": {},
        },
    )

    result = _run_resolver(manifest_json, "solo")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["solo"]


def test_resolve_multiple_requests_deduplicates_targets(tmp_path: Path) -> None:
    manifest_json = _write_manifest_json(
        tmp_path,
        {
            "version": 1,
            "defaults": {"lock": False, "timeout_seconds": 300},
            "targets": {
                "base": {"requires_expanded": []},
                "web.typecheck": {"requires_expanded": ["base"]},
                "web.unit": {"requires_expanded": ["web.typecheck"]},
            },
            "groups": {"test.web": {"targets": ["web.typecheck", "web.unit"]}},
            "groups_expanded": {"test.web": ["web.typecheck", "web.unit"]},
        },
    )

    result = _run_resolver(manifest_json, "test.web", "web.unit")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["base", "web.typecheck", "web.unit"]