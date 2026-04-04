from __future__ import annotations

import json
from pathlib import Path

from metrics.runner.aggregator import run_aggregation
from metrics.runner.module8_ops import (
    apply_retention_policy,
    classify_failure,
    ensure_ops_state,
    run_optional_collectors,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_latest_metrics(repo_root: Path) -> None:
    _write_json(
        repo_root / "artifacts" / "metrics" / "latest" / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "seed",
            "source": {"commit_sha": "a" * 40, "branch": "main"},
            "collection_status": "partial",
            "modules": {
                "backend": {"status": "partial", "metrics": {"loc": {"total_lines": 10, "files": 1, "total_code_lines": 8}}},
                "frontend": {
                    "status": "partial",
                    "metrics": {
                        "loc": {"total_lines": 5, "files": 1, "total_code_lines": 4, "js_ts_files": 1, "svelte_files": 0},
                        "cognitive_complexity": {"mean": 1.0, "max": 1, "count": 1},
                    },
                },
            },
            "delta": {},
        },
    )


def test_module8_ops_state_files_are_created(tmp_path: Path) -> None:
    paths = ensure_ops_state(tmp_path)
    assert (tmp_path / paths["failure_taxonomy_path"]).exists()
    assert (tmp_path / paths["log_policy_path"]).exists()
    assert (tmp_path / paths["extensions_path"]).exists()


def test_module8_failure_taxonomy_classifies_timeout(tmp_path: Path) -> None:
    ensure_ops_state(tmp_path)
    classified = classify_failure(tmp_path, "collector timeout while running")
    assert classified["code"] == "timeout"


def test_module8_optional_collectors_record_disabled_state(tmp_path: Path) -> None:
    ensure_ops_state(tmp_path)
    _seed_latest_metrics(tmp_path)
    payload = run_optional_collectors(tmp_path, run_id="module8-disabled")
    assert payload["status"] == "not_available"
    assert "bundle_size" in payload["collectors"]
    assert payload["collectors"]["bundle_size"]["reason"] == "disabled"


def test_module8_optional_bundle_size_success_when_enabled(tmp_path: Path) -> None:
    ensure_ops_state(tmp_path)
    _seed_latest_metrics(tmp_path)
    _write_json(
        tmp_path / "metrics" / "state" / "extensions.json",
        {
            "schema_version": 1,
            "collectors": [
                {"name": "bundle_size", "enabled": True, "optional": True},
            ],
        },
    )
    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports" / "latest.md").write_text("x", encoding="utf-8")
    _write_json(tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json", {"schema_version": 1})
    _write_json(tmp_path / "artifacts" / "metrics" / "latest" / "summary.json", {"schema_version": 1})

    payload = run_optional_collectors(tmp_path, run_id="module8-enabled")
    assert payload["status"] == "partial"
    assert payload["collectors"]["bundle_size"]["status"] == "success"


def test_module8_retention_prunes_old_history_runs(tmp_path: Path) -> None:
    history = tmp_path / "artifacts" / "metrics" / "history"
    for run in ["run-a", "run-b", "run-c", "run-d"]:
        (history / run).mkdir(parents=True, exist_ok=True)
        (history / run / "manifest.json").write_text("{}", encoding="utf-8")
    result = apply_retention_policy(tmp_path, max_history_runs=2)
    assert result["kept"] == 2
    assert set(result["pruned"]) == {"run-a", "run-b"}


def test_module8_aggregation_preserves_optional_module_payload(tmp_path: Path) -> None:
    _seed_latest_metrics(tmp_path)
    latest_metrics = json.loads((tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json").read_text(encoding="utf-8"))
    latest_metrics["modules"]["optional_collectors"] = {
        "status": "not_available",
        "collectors": {
            "bundle_size": {"status": "not_available", "reason": "disabled"}
        },
    }
    _write_json(tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json", latest_metrics)

    _write_json(
        tmp_path / "artifacts" / "metrics" / "history" / "prev" / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "prev",
            "source": {"repository_path": str(tmp_path), "branch": "main", "commit_sha": "b" * 40},
            "trigger": {"mode": "poller", "polled_at": "2026-04-04T00:00:00+00:00"},
            "execution": {
                "started_at": "2026-04-04T00:00:00+00:00",
                "finished_at": "2026-04-04T00:00:00+00:00",
                "duration_seconds": 0.1,
                "hostname": "h",
                "executor_identity": "u",
                "exit_state": "success",
            },
            "tools": {"python": "3.12", "git": "git version test"},
            "steps": [],
            "artifacts": {
                "latest_manifest": "artifacts/metrics/latest/manifest.json",
                "latest_metrics": "artifacts/metrics/latest/metrics.json",
                "history_manifest": "artifacts/metrics/history/prev/manifest.json",
                "history_metrics": "artifacts/metrics/history/prev/metrics.json",
            },
            "publication": {
                "status": "not_published",
                "metrics_branch": "metrics",
                "dashboard_relative_path": "/dashboard/",
                "published_at": None,
            },
            "warnings": [],
            "failures": [],
        },
    )
    _write_json(tmp_path / "artifacts" / "metrics" / "history" / "prev" / "metrics.json", latest_metrics)

    result = run_aggregation(tmp_path, run_id="module8-agg")
    assert "optional_collectors" in result["metrics"]["modules"]
