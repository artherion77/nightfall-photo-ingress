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
    (repo_root / "metrics" / "dashboard" / "src" / "routes").mkdir(parents=True, exist_ok=True)
    (repo_root / "metrics" / "dashboard" / "src" / "routes" / "+page.svelte").write_text(
        "<h1>dashboard source</h1>\n",
        encoding="utf-8",
    )
    (repo_root / "metrics" / "output" / "dashboard" / "latest").mkdir(parents=True, exist_ok=True)
    (repo_root / "metrics" / "output" / "dashboard" / "latest" / "__data.json").write_text("{}", encoding="utf-8")
    (repo_root / "metrics" / "output" / "reports").mkdir(parents=True, exist_ok=True)
    (repo_root / "metrics" / "output" / "reports" / "latest.md").write_text("# report", encoding="utf-8")


def test_module7_publish_writes_publication_state_and_syncs_worktree(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-success")

    worktree = tmp_path / "worktree"

    def _fake_dashboard_gen(repo_root, run_id):
        # Write a valid __data.json matching the run/commit so validation passes.
        data_dir = repo_root / "metrics" / "output" / "dashboard" / "latest"
        data_dir.mkdir(parents=True, exist_ok=True)
        _write_json(data_dir / "__data.json", {"runId": "module6-success", "commitFull": "a" * 40})
        return {"run_id": run_id}

    monkeypatch.setattr(poller_runner, "_ensure_publication_worktree", lambda _root, _branch: worktree)
    monkeypatch.setattr(poller_runner, "_commit_if_needed", lambda _root, _worktree, _message: (True, "c" * 40))
    monkeypatch.setattr(poller_runner, "_push_publication_branch", lambda _root, _worktree, _branch: (True, None))
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", _fake_dashboard_gen)
    monkeypatch.setattr(poller_runner, "_build_static_dashboard", lambda repo_root: None)

    payload = poller_runner.publish_metrics(tmp_path)

    assert payload["status"] == "published"
    assert payload["metrics_branch"] == "metrics"
    assert payload["run_id"] == "module6-success"
    assert payload["publication_commit"] == "c" * 40
    assert payload["push_succeeded"] is True
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


def test_module7_publish_reports_push_failure(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-push-fail")
    worktree = tmp_path / "worktree"

    def _fake_dashboard_gen(repo_root, run_id):
        data_dir = repo_root / "metrics" / "output" / "dashboard" / "latest"
        data_dir.mkdir(parents=True, exist_ok=True)
        _write_json(data_dir / "__data.json", {"runId": "module6-push-fail", "commitFull": "a" * 40})
        return {"run_id": run_id}

    monkeypatch.setattr(poller_runner, "_ensure_publication_worktree", lambda _root, _branch: worktree)
    monkeypatch.setattr(poller_runner, "_commit_if_needed", lambda _root, _worktree, _message: (True, "d" * 40))
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", _fake_dashboard_gen)
    monkeypatch.setattr(poller_runner, "_build_static_dashboard", lambda repo_root: None)
    monkeypatch.setattr(
        poller_runner,
        "_push_publication_branch",
        lambda _root, _worktree, _branch: (False, "remote rejected"),
    )

    payload = poller_runner.publish_metrics(tmp_path)
    assert payload["status"] == "published_commit_only"
    assert payload["push_succeeded"] is False
    assert payload["push_error"] == "remote rejected"


def test_module7_publish_reuses_published_dashboard_when_fingerprint_matches(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-reuse")
    worktree = tmp_path / "worktree"
    (worktree / "dashboard").mkdir(parents=True, exist_ok=True)
    (worktree / "dashboard" / "index.html").write_text("<html>published</html>", encoding="utf-8")

    source_fp = poller_runner._compute_dashboard_source_fingerprint(tmp_path)
    (worktree / "dashboard" / ".build-stamp").write_text(
        json.dumps({"source_fingerprint": source_fp, "built_at": "2026-04-05T00:00:00+00:00"}),
        encoding="utf-8",
    )

    def _fake_dashboard_gen(repo_root, run_id):
        data_dir = repo_root / "metrics" / "output" / "dashboard" / "latest"
        data_dir.mkdir(parents=True, exist_ok=True)
        _write_json(data_dir / "__data.json", {"runId": "module6-reuse", "commitFull": "a" * 40})
        return {"run_id": run_id}

    monkeypatch.setattr(poller_runner, "_ensure_publication_worktree", lambda _root, _branch: worktree)
    monkeypatch.setattr(poller_runner, "_commit_if_needed", lambda _root, _worktree, _message: (True, "e" * 40))
    monkeypatch.setattr(poller_runner, "_push_publication_branch", lambda _root, _worktree, _branch: (True, None))
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", _fake_dashboard_gen)
    monkeypatch.setattr(
        poller_runner,
        "_build_static_dashboard",
        lambda _repo_root: (_ for _ in ()).throw(AssertionError("build should not run when published fingerprint matches")),
    )

    payload = poller_runner.publish_metrics(tmp_path)
    assert payload["status"] == "published"
    assert payload["dashboard_sync_mode"] == "reuse_published"
    assert payload["dashboard_source_fingerprint"] == source_fp


def test_module7_publish_builds_when_published_dashboard_fingerprint_differs(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_and_latest(tmp_path, run_id="module6-rebuild")
    worktree = tmp_path / "worktree"
    (worktree / "dashboard").mkdir(parents=True, exist_ok=True)
    (worktree / "dashboard" / "index.html").write_text("<html>published old</html>", encoding="utf-8")
    (worktree / "dashboard" / ".build-stamp").write_text(
        json.dumps({"source_fingerprint": "old-fingerprint", "built_at": "2026-04-04T00:00:00+00:00"}),
        encoding="utf-8",
    )
    # Force local drift so publish needs a local rebuild before syncing.
    (tmp_path / "dashboard" / ".build-stamp").write_text(
        json.dumps({"source_fingerprint": "stale-local-fingerprint", "built_at": "2026-04-04T00:00:00+00:00"}),
        encoding="utf-8",
    )

    def _fake_dashboard_gen(repo_root, run_id):
        data_dir = repo_root / "metrics" / "output" / "dashboard" / "latest"
        data_dir.mkdir(parents=True, exist_ok=True)
        _write_json(data_dir / "__data.json", {"runId": "module6-rebuild", "commitFull": "a" * 40})
        return {"run_id": run_id}

    built = {"count": 0}

    def _fake_build(repo_root):
        built["count"] += 1
        (repo_root / "dashboard").mkdir(parents=True, exist_ok=True)
        (repo_root / "dashboard" / "index.html").write_text("<html>new local build</html>", encoding="utf-8")
        poller_runner._write_dashboard_build_stamp(repo_root)

    monkeypatch.setattr(poller_runner, "_ensure_publication_worktree", lambda _root, _branch: worktree)
    monkeypatch.setattr(poller_runner, "_commit_if_needed", lambda _root, _worktree, _message: (True, "f" * 40))
    monkeypatch.setattr(poller_runner, "_push_publication_branch", lambda _root, _worktree, _branch: (True, None))
    monkeypatch.setattr(poller_runner, "run_dashboard_generation", _fake_dashboard_gen)
    monkeypatch.setattr(poller_runner, "_build_static_dashboard", _fake_build)

    payload = poller_runner.publish_metrics(tmp_path)
    assert payload["status"] == "published"
    assert payload["dashboard_sync_mode"] == "sync_local"
    assert built["count"] == 1
