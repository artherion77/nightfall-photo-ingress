from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PARSER = REPO_ROOT / "dev" / "lib" / "govctl_manifest.py"


def _write_manifest(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "govctl-targets.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _run_parser(manifest_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PARSER), str(manifest_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_manifest_normalizes_and_expands_groups(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
defaults:
  lock: false
  timeout_seconds: 300
targets:
  dev.ensure:
    description: "Ensure"
    command: "./dev/bin/devctl status"
  web.typecheck:
    description: "Typecheck"
    command: "./dev/bin/devctl test-web-typecheck"
    requires: [dev.ensure]
  web.unit:
    description: "Unit"
    command: "./dev/bin/devctl test-web-unit"
    requires: [web.typecheck]
groups:
  test.web:
    targets: [web.typecheck, web.unit]
  test.all:
    targets: [test.web]
""".strip()
        + "\n",
    )

    result = _run_parser(manifest_path)

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["version"] == 1
    assert parsed["groups_expanded"]["test.web"] == ["web.typecheck", "web.unit"]
    assert parsed["groups_expanded"]["test.all"] == ["web.typecheck", "web.unit"]
    assert parsed["targets"]["web.unit"]["requires_expanded"] == ["web.typecheck"]


def test_manifest_output_is_idempotent(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
targets:
  one:
    description: "One"
    command: "echo one"
  two:
    description: "Two"
    command: "echo two"
    requires: [one]
""".strip()
        + "\n",
    )

    run_a = _run_parser(manifest_path)
    run_b = _run_parser(manifest_path)

    assert run_a.returncode == 0, run_a.stderr
    assert run_b.returncode == 0, run_b.stderr
    assert run_a.stdout == run_b.stdout


def test_manifest_missing_required_field_fails(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
targets:
  backend.test.unit:
    command: "pytest tests/unit -q"
""".strip()
        + "\n",
    )

    result = _run_parser(manifest_path)

    assert result.returncode == 1
    assert "description" in result.stderr


def test_manifest_requires_cycle_fails(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
targets:
  a:
    description: "A"
    command: "echo a"
    requires: [b]
  b:
    description: "B"
    command: "echo b"
    requires: [a]
""".strip()
        + "\n",
    )

    result = _run_parser(manifest_path)

    assert result.returncode == 1
    assert "requires graph contains a cycle" in result.stderr


def test_manifest_group_cycle_fails(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
targets:
  t1:
    description: "T1"
    command: "echo t1"
groups:
  g1:
    targets: [g2]
  g2:
    targets: [g1]
""".strip()
        + "\n",
    )

    result = _run_parser(manifest_path)

    assert result.returncode == 1
    assert "groups contain a cycle" in result.stderr


def test_manifest_requires_unknown_ref_fails(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        """
version: 1
targets:
  t1:
    description: "T1"
    command: "echo t1"
    requires: [missing.target]
""".strip()
        + "\n",
    )

    result = _run_parser(manifest_path)

    assert result.returncode == 1
    assert "unknown requires reference" in result.stderr