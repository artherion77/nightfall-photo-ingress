from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "dev" / "lib" / "source_fingerprint.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "source_fingerprint" / "sample"

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
from source_fingerprint import (  # noqa: E402
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_INCLUDE_GLOBS,
    compute_fingerprint,
    main,
    write_build_stamp,
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _expected_hash() -> str:
    return (FIXTURE_ROOT / "expected.hash").read_text(encoding="utf-8").strip()


def test_compute_matches_expected_hash() -> None:
    result = compute_fingerprint(FIXTURE_ROOT, DEFAULT_INCLUDE_GLOBS, DEFAULT_EXCLUDE_DIRS)
    assert result == _expected_hash()


def test_compute_is_deterministic() -> None:
    a = compute_fingerprint(FIXTURE_ROOT, DEFAULT_INCLUDE_GLOBS, DEFAULT_EXCLUDE_DIRS)
    b = compute_fingerprint(FIXTURE_ROOT, DEFAULT_INCLUDE_GLOBS, DEFAULT_EXCLUDE_DIRS)
    assert a == b


def test_compute_excludes_node_modules_and_svelte_kit() -> None:
    include = ["**/*.js", "**/*.ts"]
    without_excludes = compute_fingerprint(FIXTURE_ROOT, include, [])
    with_excludes = compute_fingerprint(FIXTURE_ROOT, include, ["node_modules", ".svelte-kit"])
    assert without_excludes != with_excludes


def test_compute_with_empty_matches_returns_sha256_empty() -> None:
    result = compute_fingerprint(FIXTURE_ROOT, ["**/*.does-not-exist"], DEFAULT_EXCLUDE_DIRS)
    assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_write_build_stamp_fields_and_file(tmp_path: Path) -> None:
    stamp_path = tmp_path / ".build-stamp"
    stamp = write_build_stamp(FIXTURE_ROOT, stamp_path, DEFAULT_INCLUDE_GLOBS, DEFAULT_EXCLUDE_DIRS)

    assert stamp["fingerprint"] == _expected_hash()
    assert "timestamp" in stamp
    datetime.fromisoformat(stamp["timestamp"])

    on_disk = json.loads(stamp_path.read_text(encoding="utf-8"))
    assert on_disk["fingerprint"] == _expected_hash()
    assert "timestamp" in on_disk


def test_cli_compute_matches_expected() -> None:
    r = _run_cli("compute", str(FIXTURE_ROOT))
    assert r.returncode == 0
    assert r.stdout.strip() == _expected_hash()


def test_cli_stamp_writes_file(tmp_path: Path) -> None:
    stamp_path = tmp_path / "stamp.json"
    r = _run_cli("stamp", str(FIXTURE_ROOT), str(stamp_path))
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["fingerprint"] == _expected_hash()
    assert stamp_path.exists()


def test_main_compute_in_process(capsys) -> None:
    rc = main(["compute", str(FIXTURE_ROOT)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == _expected_hash()


def test_main_stamp_in_process(tmp_path: Path, capsys) -> None:
    stamp_path = tmp_path / "stamp.json"
    rc = main(["stamp", str(FIXTURE_ROOT), str(stamp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fingerprint"] == _expected_hash()


def test_cli_custom_include_and_exclude() -> None:
    r = _run_cli(
        "compute",
        str(FIXTURE_ROOT),
        "--include",
        "**/*.ts",
        "--exclude-dir",
        "node_modules",
        ".svelte-kit",
    )
    assert r.returncode == 0
    assert len(r.stdout.strip()) == 64


def test_main_bad_args_raises_system_exit() -> None:
    import pytest

    with pytest.raises(SystemExit):
        main([])
