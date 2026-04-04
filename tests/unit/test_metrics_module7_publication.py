from __future__ import annotations

import json
from pathlib import Path

from metrics.runner import poller_runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_runtime_and_latest(repo_root: Path, run_id: str = "module6-run") -> None:
    _write_json(
        repo_root / "metrics" / "state" / "runtime.json",
        {
            "schema_version": 1,
            "frequency_minutes": 60,
            "metrics_branch": "metrics",
            "dashboard_relative_path": "/dashboard/",
            "installed": True,
            "enabled": True,
            "retry_max_retries": 1,
            "timeout_seconds": 1800,
            "configured_at": "2026-04-04T00:00:00+00:00",
        },
    )
    _write_json(
        repo_root / "artifacts" / "metrics" / "latest" / "manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "source": {"commit_sha": "a" * 40},
            "execution": {"exit_state": "success"},
        },
    )
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "metrics.json", {"schema_version": 1})
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "summary.json", {"schema_version": 1, "run_id": run_id})

    _write_json(repo_root / "artifacts" / "metrics" / "history" / run_id / "manifest.json", {"schema_version": 1, "run_id": run_id})
    _write_json(repo_root / "artifacts" / "metrics" / "history" / run_id / "summary.json", {"schema_version": 1, "run_id": run_id})
    _write_json(repo_root / "artifacts" / "metrics" / "history" / run_id / "metrics.json", {"schema_version": 1, "run_id": run_id})

    (repo_root / "dashboard").mkdir(parents=True, exist_ok=True)
    (repo_root / "dashboard" / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    (repo_root / "reports").mkdir(parents=True, exist_ok=True)
    (repo_root / "reports" / "latest.md").write_text("# report", encoding="utf-8")


def test_module7_publish_writes_publication_state_and_syncs_worktree(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-success")

    worktree = tmp_path / "worktree"

    monkeypatch.setattr(poller_runner, "_ensure_publication_worktree", lambda _root, _branch: worktree)
    monkeypatch.setattr(poller_runner, "_commit_if_needed", lambda _root, _worktree, _message: (True, "c" * 40))

    payload = poller_runner.publish_metrics(tmp_path)

    assert payload["status"] == "published"
    assert payload["metrics_branch"] == "metrics"
    assert payload["run_id"] == "module6-success"
    assert payload["publication_commit"] == "c" * 40
    assert (worktree / "dashboard" / "index.html").exists()
    assert (worktree / "reports" / "latest.md").exists()
    assert (worktree / "artifacts" / "metrics" / "latest" / "manifest.json").exists()
    assert (worktree / "artifacts" / "metrics" / "history" / "module6-success" / "manifest.json").exists()

    publication_state = tmp_path / "metrics" / "state" / "last_publication.json"
    assert publication_state.exists()
    state = json.loads(publication_state.read_text(encoding="utf-8"))
    assert state["status"] == "published"


def test_module7_publish_skips_when_last_run_not_success(tmp_path: Path) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-failed")
    _write_json(
        tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "module6-failed",
            "source": {"commit_sha": "d" * 40},
            "execution": {"exit_state": "failed"},
        },
    )

    payload = poller_runner.publish_metrics(tmp_path)
    assert payload["status"] == "skipped_last_run_not_successful"
    assert payload["run_id"] == "module6-failed"
