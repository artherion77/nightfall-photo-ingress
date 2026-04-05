from __future__ import annotations

import fcntl
import json
from pathlib import Path

import pytest

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
    monkeypatch.setattr(poller_runner, "_validate_post_collection_outputs", lambda **_: None)
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


class TestValidatePublishPayload:
    """Test _validate_publish_payload rejects stale __data.json."""

    def test_matching_payload_passes(self, tmp_path: Path) -> None:
        data_path = tmp_path / "__data.json"
        data_path.write_text(
            json.dumps({"runId": "run-1", "commitFull": "a" * 40}),
            encoding="utf-8",
        )
        # Should not raise
        poller_runner._validate_publish_payload(data_path, "run-1", "a" * 40)

    def test_run_id_mismatch_raises(self, tmp_path: Path) -> None:
        data_path = tmp_path / "__data.json"
        data_path.write_text(
            json.dumps({"runId": "old-run", "commitFull": "a" * 40}),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="runId mismatch"):
            poller_runner._validate_publish_payload(data_path, "new-run", "a" * 40)

    def test_commit_mismatch_raises(self, tmp_path: Path) -> None:
        data_path = tmp_path / "__data.json"
        data_path.write_text(
            json.dumps({"runId": "run-1", "commitFull": "a" * 40}),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="commitSha mismatch"):
            poller_runner._validate_publish_payload(data_path, "run-1", "b" * 40)

    def test_empty_expected_commit_skips_commit_check(self, tmp_path: Path) -> None:
        data_path = tmp_path / "__data.json"
        data_path.write_text(
            json.dumps({"runId": "run-1", "commitFull": "a" * 40}),
            encoding="utf-8",
        )
        # Empty expected_commit → commit check skipped
        poller_runner._validate_publish_payload(data_path, "run-1", "")


def test_module6_dashboard_drift_check_ignores_hashed_dist_churn(tmp_path: Path) -> None:
    # Seed dashboard source and existing dist.
    src_file = tmp_path / "metrics" / "dashboard" / "src" / "routes" / "+page.svelte"
    _write_text(src_file, "<h1>metrics</h1>\n")
    _write_text(tmp_path / "dashboard" / "index.html", "<html>built</html>\n")

    # Write a valid stamp for current source.
    poller_runner._write_dashboard_build_stamp(tmp_path)

    # Simulate nondeterministic Vite hash churn in dist filenames.
    _write_text(tmp_path / "dashboard" / "_app" / "immutable" / "entry" / "app.AAAAAAAA.js", "a\n")
    _write_text(tmp_path / "dashboard" / "_app" / "immutable" / "entry" / "app.BBBBBBBB.js", "b\n")

    assert poller_runner._dashboard_needs_rebuild(tmp_path) is False


def test_module6_dashboard_drift_check_detects_real_source_change(tmp_path: Path) -> None:
    src_file = tmp_path / "metrics" / "dashboard" / "src" / "routes" / "+page.svelte"
    _write_text(src_file, "<h1>v1</h1>\n")
    _write_text(tmp_path / "dashboard" / "index.html", "<html>built</html>\n")

    poller_runner._write_dashboard_build_stamp(tmp_path)
    assert poller_runner._dashboard_needs_rebuild(tmp_path) is False

    # Real source change should trigger rebuild requirement.
    _write_text(src_file, "<h1>v2</h1>\n")
    assert poller_runner._dashboard_needs_rebuild(tmp_path) is True


def test_module6_run_now_fails_when_complexity_tool_unavailable(tmp_path: Path, monkeypatch) -> None:
    _write_text(tmp_path / "metrics" / "state" / "last_processed_commit", "0" * 40)
    _write_text(tmp_path / "metrics" / "state" / "runtime.json", json.dumps(poller_runner._runtime_defaults()))

    monkeypatch.setattr(poller_runner, "_git_head_sha", lambda _: "e" * 40)
    monkeypatch.setattr(poller_runner, "_git_branch", lambda _: "main")
    monkeypatch.setattr(poller_runner, "run_backend_collection", lambda **_: None)
    monkeypatch.setattr(poller_runner, "run_frontend_collection", lambda **_: None)
    monkeypatch.setattr(poller_runner, "run_optional_collectors", lambda **_: None)

    def _fake_aggregation(**_: object) -> None:
        payload = {
            "modules": {
                "backend": {
                    "metrics": {
                        "complexity": {
                            "status": "not_available",
                            "reason": "radon import failed",
                        }
                    }
                },
                "frontend": {
                    "metrics": {
                        "cognitive_complexity": {
                            "status": "success",
                            "mean": 10.0,
                        }
                    }
                },
            }
        }
        path = tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(poller_runner, "run_aggregation", _fake_aggregation)
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", lambda **_: None)
    monkeypatch.setattr(poller_runner, "apply_retention_policy", lambda **_: {"kept": 0, "pruned": []})

    result = poller_runner.run_now(tmp_path, max_retries=0, timeout_seconds=60)
    assert result["status"] == "failed"
    assert "Backend complexity tool unavailable" in result["error"]
    # last_processed_commit must remain unchanged when critical tool output is unavailable.
    assert (tmp_path / "metrics" / "state" / "last_processed_commit").read_text(encoding="utf-8") == "0" * 40
