"""Tests for dev/lib/manifest_hash.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "dev" / "lib" / "manifest_hash.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "manifest_hash"

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
from manifest_hash import CompareResult, compare, compute_hash, main, read_hash_file  # noqa: E402


# ---------------------------------------------------------------------------
# Ground-truth hashes computed via:
#   cat package.json package-lock.json | sha256sum | awk '{print $1}'
# ---------------------------------------------------------------------------

VALID_HASH = "fe54d00c09eea116dfe1244c63ad064a1bc86a5ff113754cff565dfaea6be1b5"
EMPTY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ---- compute_hash ---------------------------------------------------------


class TestComputeHash:
    def test_valid_fixture_matches_bash(self) -> None:
        result = compute_hash(FIXTURES / "valid")
        assert result == VALID_HASH

    def test_empty_files_matches_bash(self) -> None:
        result = compute_hash(FIXTURES / "empty_files")
        assert result == EMPTY_HASH

    def test_missing_lock_returns_empty(self) -> None:
        result = compute_hash(FIXTURES / "missing_lock")
        assert result == ""

    def test_missing_both_returns_empty(self) -> None:
        result = compute_hash(FIXTURES / "missing_both")
        assert result == ""

    def test_missing_directory_returns_empty(self) -> None:
        result = compute_hash(Path("/nonexistent/dir"))
        assert result == ""

    def test_deterministic(self) -> None:
        a = compute_hash(FIXTURES / "valid")
        b = compute_hash(FIXTURES / "valid")
        assert a == b


# ---- read_hash_file -------------------------------------------------------


class TestReadHashFile:
    def test_reads_and_strips(self, tmp_path: Path) -> None:
        f = tmp_path / "hash.txt"
        f.write_text("  abc123  \n", encoding="utf-8")
        assert read_hash_file(f) == "abc123"

    def test_reads_fixture_hash(self) -> None:
        result = read_hash_file(FIXTURES / "valid" / "expected.hash")
        assert result == VALID_HASH


# ---- compare --------------------------------------------------------------


class TestCompare:
    def test_match(self) -> None:
        result = compare(FIXTURES / "valid", FIXTURES / "valid" / "expected.hash")
        assert result == CompareResult(match=True, host_hash=VALID_HASH, stored_hash=VALID_HASH)

    def test_mismatch(self, tmp_path: Path) -> None:
        bad_hash = tmp_path / "bad.hash"
        bad_hash.write_text("0000000000000000000000000000000000000000000000000000000000000000\n")
        result = compare(FIXTURES / "valid", bad_hash)
        assert result.match is False
        assert result.host_hash == VALID_HASH
        assert result.stored_hash == "0000000000000000000000000000000000000000000000000000000000000000"

    def test_missing_files_mismatch(self, tmp_path: Path) -> None:
        hash_file = tmp_path / "stored.hash"
        hash_file.write_text(VALID_HASH)
        result = compare(FIXTURES / "missing_lock", hash_file)
        assert result.match is False
        assert result.host_hash == ""


# ---- CLI ------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCLICompute:
    def test_compute_valid(self) -> None:
        r = _run_cli("compute", str(FIXTURES / "valid"))
        assert r.returncode == 0
        assert r.stdout.strip() == VALID_HASH

    def test_compute_missing_files(self) -> None:
        r = _run_cli("compute", str(FIXTURES / "missing_lock"))
        assert r.returncode == 1
        assert "missing" in r.stderr.lower()

    def test_compute_no_args(self) -> None:
        r = _run_cli("compute")
        assert r.returncode == 2

    def test_compute_empty_files(self) -> None:
        r = _run_cli("compute", str(FIXTURES / "empty_files"))
        assert r.returncode == 0
        assert r.stdout.strip() == EMPTY_HASH


class TestCLICompare:
    def test_compare_match(self) -> None:
        r = _run_cli("compare", str(FIXTURES / "valid"), str(FIXTURES / "valid" / "expected.hash"))
        assert r.returncode == 0

    def test_compare_mismatch(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.hash"
        bad.write_text("0" * 64)
        r = _run_cli("compare", str(FIXTURES / "valid"), str(bad))
        assert r.returncode == 1
        assert "mismatch" in r.stderr.lower()

    def test_compare_no_args(self) -> None:
        r = _run_cli("compare")
        assert r.returncode == 2


class TestCLIMisc:
    def test_no_command(self) -> None:
        r = _run_cli()
        assert r.returncode == 2

    def test_unknown_command(self) -> None:
        r = _run_cli("bogus")
        assert r.returncode == 2


# ---- main() in-process (for coverage) ------------------------------------


class TestMainInProcess:
    def test_compute_valid(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["compute", str(FIXTURES / "valid")])
        assert rc == 0
        assert capsys.readouterr().out.strip() == VALID_HASH

    def test_compute_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["compute", str(FIXTURES / "missing_lock")])
        assert rc == 1

    def test_compute_no_args(self) -> None:
        assert main(["compute"]) == 2

    def test_compare_match(self) -> None:
        rc = main(["compare", str(FIXTURES / "valid"), str(FIXTURES / "valid" / "expected.hash")])
        assert rc == 0

    def test_compare_mismatch(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        bad = tmp_path / "bad.hash"
        bad.write_text("0" * 64)
        rc = main(["compare", str(FIXTURES / "valid"), str(bad)])
        assert rc == 1
        assert "mismatch" in capsys.readouterr().err.lower()

    def test_compare_no_args(self) -> None:
        assert main(["compare"]) == 2

    def test_no_args(self) -> None:
        assert main([]) == 2

    def test_unknown_command(self) -> None:
        assert main(["bogus"]) == 2
