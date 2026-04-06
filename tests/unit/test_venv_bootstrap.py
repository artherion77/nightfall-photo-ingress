from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
import venv_bootstrap  # noqa: E402
from venv_bootstrap import ensure_venv, is_running_in_venv  # noqa: E402


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_is_running_in_venv_true_by_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "prefix", "/tmp/work/.venv")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    assert is_running_in_venv() is True


def test_is_running_in_venv_true_by_executable_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "executable", "/tmp/work/.venv/bin/python")
    assert is_running_in_venv() is True


def test_is_running_in_venv_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    assert is_running_in_venv() is False


def test_ensure_venv_noop_when_venv_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "metricsctl"
    _touch(script)

    called = {"execve": False}

    def _fake_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        called["execve"] = True

    monkeypatch.setattr(os, "execve", _fake_execve)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")

    ensure_venv(script)
    assert called["execve"] is False


def test_ensure_venv_noop_when_guard_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "metricsctl"
    _touch(script)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    _touch(venv_python)

    guard = "NIGHTFALL_TEST_GUARD"
    monkeypatch.setenv(guard, "1")
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")

    called = {"execve": False}

    def _fake_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        called["execve"] = True

    monkeypatch.setattr(os, "execve", _fake_execve)

    ensure_venv(script, guard_var=guard)
    assert called["execve"] is False


def test_ensure_venv_noop_when_current_is_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "metricsctl"
    _touch(script)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    _touch(venv_python)

    monkeypatch.setattr(sys, "executable", str(venv_python))

    called = {"execve": False}

    def _fake_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        called["execve"] = True

    monkeypatch.setattr(os, "execve", _fake_execve)

    ensure_venv(script)
    assert called["execve"] is False


def test_ensure_venv_execve_on_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "metricsctl"
    _touch(script)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    _touch(venv_python)

    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(sys, "argv", [str(script), "status", "--json"])

    captured: dict[str, object] = {}

    def _fake_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        captured["path"] = path
        captured["argv"] = argv
        captured["env"] = env

    monkeypatch.setattr(os, "execve", _fake_execve)

    ensure_venv(script)

    assert captured["path"] == str(venv_python.resolve())
    assert captured["argv"] == [str(venv_python.resolve()), str(script.resolve()), "status", "--json"]

    env = captured["env"]
    assert isinstance(env, dict)
    guard = "NIGHTFALL_METRICSCTL_VENV_REEXEC"
    assert env.get(guard) == "1"


def test_ensure_venv_uses_custom_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "tool.py"
    _touch(script)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    _touch(venv_python)

    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(sys, "argv", [str(script)])

    captured: dict[str, object] = {}

    def _fake_execve(path: str, argv: list[str], env: dict[str, str]) -> None:
        captured["env"] = env

    monkeypatch.setattr(os, "execve", _fake_execve)

    ensure_venv(script, guard_var="CUSTOM_GUARD")
    env = captured["env"]
    assert isinstance(env, dict)
    assert env.get("CUSTOM_GUARD") == "1"


def test_no_cli_entrypoint_behavior() -> None:
    assert not hasattr(venv_bootstrap, "main")
