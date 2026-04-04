from __future__ import annotations

import fcntl
import json
from pathlib import Path

from metrics.runner import poller_runner


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_module6_install_writes_systemd_and_runtime(tmp_path: Path) -> None:
    payload = poller_runner.install_poller(tmp_path, frequency_minutes=45)

    assert payload["installed"] is True
    assert payload["enabled"] is True
    assert payload["frequency_minutes"] == 45

    service_path = tmp_path / "metrics" / "systemd" / "nightfall-metrics-poller.service"
    timer_path = tmp_path / "metrics" / "systemd" / "nightfall-metrics-poller.timer"
    runtime_path = tmp_path / "metrics" / "state" / "runtime.json"

    assert service_path.exists()
    assert timer_path.exists()
    assert runtime_path.exists()
    assert "ExecStart=" in service_path.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=45m" in timer_path.read_text(encoding="utf-8")


def test_module6_run_now_skips_when_commit_unchanged(tmp_path: Path, monkeypatch) -> None:
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "a" * 40)
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))

    monkeypatch.setattr(poller_runner, "_git_head_sha", lambda _: "a" * 40)
    monkeypatch.setattr(poller_runner, "_git_branch", lambda _: "main")

    called = {"backend": False}

    def _backend_should_not_run(**_: object) -> None:
        called["backend"] = True

    monkeypatch.setattr(poller_runner, "run_backend_collection", _backend_should_not_run)

    result = poller_runner.run_now(tmp_path, max_retries=0, timeout_seconds=60)
    assert result["status"] == "skipped_unchanged"
    assert called["backend"] is False


def test_module6_run_now_writes_failure_manifest(tmp_path: Path, monkeypatch) -> None:
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "0" * 40)
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))

    monkeypatch.setattr(poller_runner, "_git_head_sha", lambda _: "b" * 40)
    monkeypatch.setattr(poller_runner, "_git_branch", lambda _: "main")

    def _raise_backend(**_: object) -> None:
        raise RuntimeError("backend failed intentionally")

    monkeypatch.setattr(poller_runner, "run_backend_collection", _raise_backend)

    result = poller_runner.run_now(tmp_path, max_retries=0, timeout_seconds=60)
    assert result["status"] == "failed"
    run_id = result["run_id"]
    assert isinstance(run_id, str)

    latest_manifest = tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json"
    history_manifest = tmp_path / "artifacts" / "metrics" / "history" / str(run_id) / "manifest.json"
    assert latest_manifest.exists()
    assert history_manifest.exists()

    payload = json.loads(latest_manifest.read_text(encoding="utf-8"))
    assert payload["execution"]["exit_state"] == "failed"
    assert payload["run_id"] == run_id
    assert any("backend failed intentionally" in item for item in payload["failures"])


def test_module6_run_now_respects_lock(tmp_path: Path, monkeypatch) -> None:
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "0" * 40)
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))

    monkeypatch.setattr(poller_runner, "_git_head_sha", lambda _: "c" * 40)
    monkeypatch.setattr(poller_runner, "_git_branch", lambda _: "main")

    lock_path = tmp_path / "metrics" / "state" / "poller.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = poller_runner.run_now(tmp_path, max_retries=0, timeout_seconds=60)
        assert result["status"] == "concurrent_run"


def test_module6_run_now_enables_backend_coverage(tmp_path: Path, monkeypatch) -> None:
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "0" * 40)
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))

    monkeypatch.setattr(poller_runner, "_git_head_sha", lambda _: "d" * 40)
    monkeypatch.setattr(poller_runner, "_git_branch", lambda _: "main")

    captured: dict[str, object] = {}

    def _backend(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(poller_runner, "run_backend_collection", _backend)
    monkeypatch.setattr(poller_runner, "run_frontend_collection", lambda **_: None)
    monkeypatch.setattr(poller_runner, "run_optional_collectors", lambda **_: None)
    monkeypatch.setattr(poller_runner, "run_aggregation", lambda **_: None)
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", lambda **_: None)
    monkeypatch.setattr(poller_runner, "apply_retention_policy", lambda **_: {"kept": 0, "pruned": []})

    result = poller_runner.run_now(tmp_path, max_retries=0, timeout_seconds=60)

    assert result["status"] == "success"
    assert captured["skip_pytest"] is False


def test_module6_cleanup_runtime_artifacts_removes_ephemeral_files(tmp_path: Path) -> None:
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "x" * 40)
    _write_text(tmp_path / "metrics" / "state" / "poller_status.json", "{}")
    _write_text(tmp_path / "metrics" / "state" / "last_publication.json", "{}")
    _write_text(tmp_path / "metrics" / "state" / "poller.lock", "")
    _write_text(tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json", "{}")
    _write_text(tmp_path / "metrics" / "output" / "reports" / "latest.md", "# latest")

    result = poller_runner.cleanup_runtime_artifacts(tmp_path)

    assert result["status"] == "cleaned"
    assert not (tmp_path / "metrics" / "state" / "last_processed_commit").exists()
    assert not (tmp_path / "metrics" / "state" / "poller_status.json").exists()
    assert not (tmp_path / "metrics" / "state" / "last_publication.json").exists()
    assert not (tmp_path / "metrics" / "state" / "poller.lock").exists()
    assert not (tmp_path / "artifacts" / "metrics" / "latest").exists()
    assert not (tmp_path / "metrics" / "output").exists()
    assert (tmp_path / "metrics" / "state" / "runtime.json").exists()
