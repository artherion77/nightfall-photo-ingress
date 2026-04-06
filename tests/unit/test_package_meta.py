from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "dev" / "lib" / "package_meta.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "package_meta"

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
from package_meta import (  # noqa: E402
    ConsistencyResult,
    Mismatch,
    check_stack_consistency,
    dependency_version,
    extract_major,
    main,
    read_node_version,
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestReadNodeVersion:
    def test_prefers_node_version(self) -> None:
        assert read_node_version(FIXTURES / "with_both") == "22.1.0"

    def test_reads_nvmrc_when_node_version_missing(self) -> None:
        assert read_node_version(FIXTURES / "with_nvmrc") == "20.11.1"

    def test_reads_node_version(self) -> None:
        assert read_node_version(FIXTURES / "with_node_version") == "18.19.0"

    def test_missing_files_returns_empty(self, tmp_path: Path) -> None:
        assert read_node_version(tmp_path) == ""


class TestExtractMajor:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("5.3.1", 5),
            ("^5.3.1", 5),
            ("~5.3.1", 5),
            (">=5.3.1", 5),
            ("<=5.3.1", 5),
            (">5", 5),
            ("<5", 5),
        ],
    )
    def test_supported_formats(self, value: str, expected: int) -> None:
        assert extract_major(value) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            extract_major("latest")


class TestDependencyVersion:
    def test_returns_dev_dependency(self) -> None:
        path = FIXTURES / "web.package.json"
        assert dependency_version(path, "vite") == "~5.3.1"

    def test_returns_empty_when_missing(self) -> None:
        path = FIXTURES / "web.package.json"
        assert dependency_version(path, "eslint") == ""


class TestCheckStackConsistency:
    def test_ok_when_majors_match(self) -> None:
        result = check_stack_consistency(
            FIXTURES / "web.package.json",
            FIXTURES / "dashboard.package.json",
            ["@sveltejs/kit", "vite"],
        )
        assert result == ConsistencyResult(ok=True, mismatches=[])

    def test_detects_mismatch(self) -> None:
        result = check_stack_consistency(
            FIXTURES / "web.package.json",
            FIXTURES / "dashboard_mismatch.package.json",
            ["@sveltejs/kit", "vite"],
        )
        assert result.ok is False
        assert result.mismatches == [
            Mismatch("@sveltejs/kit", "2", "3"),
            Mismatch("vite", "5", "4"),
        ]

    def test_unparseable_dependency_reports_empty_major(self, tmp_path: Path) -> None:
        left = tmp_path / "left.package.json"
        right = tmp_path / "right.package.json"
        left.write_text('{"devDependencies": {"vite": "latest"}}', encoding="utf-8")
        right.write_text('{"devDependencies": {"vite": "^5.0.0"}}', encoding="utf-8")

        result = check_stack_consistency(left, right, ["vite"])
        assert result == ConsistencyResult(ok=False, mismatches=[Mismatch("vite", "", "")])


class TestCliSubcommands:
    def test_node_version_cli(self) -> None:
        r = _run_cli("node-version", str(FIXTURES / "with_both"))
        assert r.returncode == 0
        assert r.stdout.strip() == "22.1.0"

    def test_dep_version_cli(self) -> None:
        r = _run_cli("dep-version", str(FIXTURES / "web.package.json"), "@sveltejs/kit")
        assert r.returncode == 0
        assert r.stdout.strip() == "^2.5.0"

    def test_check_consistency_ok_cli(self) -> None:
        r = _run_cli(
            "check-consistency",
            str(FIXTURES / "web.package.json"),
            str(FIXTURES / "dashboard.package.json"),
            "--packages",
            "@sveltejs/kit",
            "vite",
        )
        assert r.returncode == 0
        assert r.stdout.strip() == "ok"

    def test_check_consistency_mismatch_cli(self) -> None:
        r = _run_cli(
            "check-consistency",
            str(FIXTURES / "web.package.json"),
            str(FIXTURES / "dashboard_mismatch.package.json"),
            "--packages",
            "@sveltejs/kit",
            "vite",
        )
        assert r.returncode == 1
        assert "mismatch" in r.stderr.lower()


class TestMainInProcess:
    def test_node_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["node-version", str(FIXTURES / "with_node_version")])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "18.19.0"

    def test_dep_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["dep-version", str(FIXTURES / "web.package.json"), "vite"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "~5.3.1"

    def test_check_consistency_mismatch(self) -> None:
        rc = main(
            [
                "check-consistency",
                str(FIXTURES / "web.package.json"),
                str(FIXTURES / "dashboard_mismatch.package.json"),
                "--packages",
                "@sveltejs/kit",
                "vite",
            ]
        )
        assert rc == 1

    def test_bad_args(self) -> None:
        with pytest.raises(SystemExit):
            main([])
