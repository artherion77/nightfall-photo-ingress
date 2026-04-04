from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


DEVCTL = Path(__file__).resolve().parents[2] / "dev" / "devctl"


def _make_web_root(tmp_path: Path) -> Path:
    web_root = tmp_path / "webui"
    web_root.mkdir(parents=True, exist_ok=True)
    (web_root / "package.json").write_text(
        json.dumps({"name": "contract-web", "private": True}),
        encoding="utf-8",
    )
    return web_root


def _run_devctl(command: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [str(DEVCTL), command],
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def test_test_web_unit_fails_when_no_component_tests(tmp_path: Path) -> None:
    web_root = _make_web_root(tmp_path)
    (web_root / "tests" / "component").mkdir(parents=True, exist_ok=True)

    result = _run_devctl(
        "test-web-unit",
        {
            "DEVCTL_CONTRACT_TEST_ROOT": str(web_root),
            "DEVCTL_TEST_WEB_UNIT_RUNNER": "true",
        },
    )

    assert result.returncode != 0
    assert "No tests/component test files found" in (result.stdout + result.stderr)


def test_test_web_unit_passes_with_dummy_component_test(tmp_path: Path) -> None:
    web_root = _make_web_root(tmp_path)
    tests_dir = web_root / "tests" / "component"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "dummy.test.ts").write_text("export {};\n", encoding="utf-8")

    result = _run_devctl(
        "test-web-unit",
        {
            "DEVCTL_CONTRACT_TEST_ROOT": str(web_root),
            "DEVCTL_TEST_WEB_UNIT_RUNNER": "true",
        },
    )

    assert result.returncode == 0
    assert "Discovered 1 tests/component test file(s)." in result.stdout
    assert "test-web-unit completed successfully." in result.stdout


def test_test_web_e2e_runs_and_reports_artifact_path(tmp_path: Path) -> None:
    web_root = _make_web_root(tmp_path)
    tests_dir = web_root / "tests" / "e2e"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "smoke.spec.ts").write_text("export {};\n", encoding="utf-8")

    result = _run_devctl(
        "test-web-e2e",
        {
            "DEVCTL_CONTRACT_TEST_ROOT": str(web_root),
            "DEVCTL_TEST_WEB_E2E_RUNNER": "true",
            "DEVCTL_E2E_ARTIFACT_DIR": "artifacts/e2e",
        },
    )

    assert result.returncode == 0
    expected_path = web_root / "artifacts" / "e2e"
    assert expected_path.exists()
    assert f"E2E_ARTIFACT_PATH={expected_path}" in result.stdout
    assert "test-web-e2e completed successfully." in result.stdout
