from __future__ import annotations

import json
from pathlib import Path

from metrics.runner.aggregator import run_aggregation


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_history_run(root: Path, run_id: str, finished_at: str, backend_lines: int, frontend_lines: int) -> None:
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "repository_path": str(root),
            "branch": "main",
            "commit_sha": "0" * 40,
        },
        "trigger": {"mode": "bootstrap", "polled_at": finished_at},
        "execution": {
            "started_at": finished_at,
            "finished_at": finished_at,
            "duration_seconds": 0.1,
            "hostname": "test-host",
            "executor_identity": "tester",
            "exit_state": "success",
        },
        "tools": {"python": "3.12", "git": "git version test"},
        "steps": [],
        "artifacts": {
            "latest_manifest": "artifacts/metrics/latest/manifest.json",
            "latest_metrics": "artifacts/metrics/latest/metrics.json",
            "history_manifest": f"artifacts/metrics/history/{run_id}/manifest.json",
            "history_metrics": f"artifacts/metrics/history/{run_id}/metrics.json",
        },
        "publication": {
            "status": "not_published",
            "metrics_branch": "metrics",
            "dashboard_relative_path": "/dashboard/",
            "published_at": None,
        },
        "warnings": [],
        "failures": [],
    }
    metrics = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {"commit_sha": "0" * 40, "branch": "main"},
        "collection_status": "partial",
        "modules": {
            "backend": {
                "status": "partial",
                "metrics": {
                    "loc": {"files": 10, "total_lines": backend_lines, "total_code_lines": backend_lines - 10},
                },
            },
            "frontend": {
                "status": "partial",
                "metrics": {
                    "loc": {
                        "files": 5,
                        "total_lines": frontend_lines,
                        "total_code_lines": frontend_lines - 5,
                        "js_ts_files": 4,
                        "svelte_files": 1,
                    },
                    "cognitive_complexity": {"mean": 4.0, "max": 8, "count": 5},
                    "test_coverage": {"status": "not_available", "reason": "deferred"},
                },
            },
        },
        "delta": {},
    }
    _write_json(root / "artifacts" / "metrics" / "history" / run_id / "manifest.json", manifest)
    _write_json(root / "artifacts" / "metrics" / "history" / run_id / "metrics.json", metrics)


def test_module4_aggregate_writes_summary_and_delta(tmp_path: Path) -> None:
    _seed_history_run(tmp_path, "older", "2026-04-04T00:00:00+00:00", backend_lines=100, frontend_lines=40)
    _seed_history_run(tmp_path, "newer", "2026-04-04T01:00:00+00:00", backend_lines=120, frontend_lines=50)

    latest_metrics = {
        "schema_version": 1,
        "run_id": "module3-bootstrap",
        "source": {"commit_sha": "0" * 40, "branch": "main"},
        "collection_status": "partial",
        "modules": {
            "backend": {
                "status": "partial",
                "metrics": {
                    "loc": {"files": 11, "total_lines": 140, "total_code_lines": 125},
                    "coverage": {"status": "not_available", "reason": "deferred"},
                },
            },
            "frontend": {
                "status": "partial",
                "metrics": {
                    "loc": {
                        "files": 6,
                        "total_lines": 60,
                        "total_code_lines": 52,
                        "js_ts_files": 5,
                        "svelte_files": 1,
                    },
                    "cognitive_complexity": {"mean": 6.0, "max": 12, "count": 6},
                    "test_coverage": {"status": "not_available", "reason": "deferred"},
                },
            },
        },
        "delta": {},
    }
    _write_json(tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json", latest_metrics)

    result = run_aggregation(tmp_path, run_id="module4-test")

    latest_summary = tmp_path / "artifacts" / "metrics" / "latest" / "summary.json"
    history_summary = tmp_path / "artifacts" / "metrics" / "history" / "module4-test" / "summary.json"
    assert latest_summary.exists()
    assert history_summary.exists()

    merged = result["metrics"]
    summary = result["summary"]
    assert merged["run_id"] == "module4-test"
    assert summary["run_id"] == "module4-test"
    assert merged["delta"]["previous_run_id"] == "newer"
    assert "modules.backend.metrics.loc.total_lines" in merged["delta"]["comparisons"]
    assert summary["severity"] in {"warning", "critical", "ok"}
