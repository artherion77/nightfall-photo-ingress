from __future__ import annotations

import json
from pathlib import Path

import pytest

from metrics.runner.aggregator import run_aggregation
from metrics.runner.module8_ops import (
    apply_retention_policy,
    classify_failure,
    ensure_ops_state,
    run_optional_collectors,
    _parse_bundle_stats,
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

    # Provide a valid bundle-stats.json so the collector can parse it.
    bundle_stats = {
        "schema_version": 1,
        "chunks": [
            {
                "name": "index.js",
                "type": "js",
                "raw_bytes": 51200,
                "gzip_bytes": 17408,
                "brotli_bytes": 14336,
                "modules": [{"id": "src/main.ts", "rendered_bytes": 51200}],
            }
        ],
    }
    (tmp_path / "webui" / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "webui" / "dist" / "bundle-stats.json").write_text(
        json.dumps(bundle_stats), encoding="utf-8"
    )

    payload = run_optional_collectors(tmp_path, run_id="module8-enabled")
    assert payload["status"] == "partial"
    assert payload["collectors"]["bundle_size"]["status"] == "available"
    assert payload["collectors"]["bundle_size"]["total_kb"] == 50.0
    assert payload["collectors"]["bundle_size"]["chunk_count"] == 1


def test_module8_bundle_size_ignores_metrics_dashboard_build_output(tmp_path: Path) -> None:
    """Bundle size collector must only use WebUI build artifacts."""
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

    # Provide stats only for metrics/dashboard and ensure collector does not use it.
    dashboard_only_stats = {
        "schema_version": 1,
        "chunks": [
            {
                "name": "dashboard.js",
                "type": "js",
                "raw_bytes": 20480,
                "gzip_bytes": 8192,
                "brotli_bytes": 7168,
                "modules": [{"id": "metrics/dashboard/src/routes/+page.svelte", "rendered_bytes": 20480}],
            }
        ],
    }
    (tmp_path / "metrics" / "dashboard" / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics" / "dashboard" / "dist" / "bundle-stats.json").write_text(
        json.dumps(dashboard_only_stats), encoding="utf-8"
    )

    payload = run_optional_collectors(tmp_path, run_id="module8-scope-check")
    assert payload["collectors"]["bundle_size"]["status"] == "not_available"
    assert "webui/dist/bundle-stats.json not found" in payload["collectors"]["bundle_size"]["reason"]


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


# ── Chunk 4: Bundle analysis collector ────────────────────────────────────────

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def test_bundle_stats_parser_against_fixture() -> None:
    """Unit test: parser produces correct aggregated bundle payload from saved fixture."""
    stats_path = _FIXTURE_DIR / "bundle_stats_fixture.json"
    result = _parse_bundle_stats(stats_path)

    assert result["status"] == "available"
    assert result["source"] == "bundle_stats_json"
    assert result["chunk_count"] == 3

    # Total raw = 51200 + 30720 + 8192 = 90112 bytes = 88.0 KB
    assert result["total_kb"] == pytest.approx(88.0, abs=0.1)

    # Gzip total = 17408 + 10752 + 2048 = 30208 bytes = 29.5 KB
    assert result["gzip_kb"] == pytest.approx(29.5, abs=0.1)

    # Brotli total = 14336 + 9216 + 1638 = 25190 bytes = 24.6 KB
    assert result["brotli_kb"] == pytest.approx(24.6, abs=0.2)

    # Largest chunk is index-Dt3Pl3Gi.js at 51200 bytes
    largest = result["largest_chunk"]
    assert largest["name"] == "index-Dt3Pl3Gi.js"
    assert largest["raw_bytes"] == 51200

    # Top contributors: should have 5 entries, sorted descending by rendered_bytes
    top = result["top_contributors"]
    assert len(top) == 5
    assert top[0]["id"] == "src/routes/+page.svelte"
    assert top[0]["rendered_kb"] == pytest.approx(22000 / 1024, abs=0.1)


def test_bundle_stats_parser_not_available_on_missing_stats_file(tmp_path: Path) -> None:
    """Collector returns not_available when no bundle-stats.json exists."""
    ensure_ops_state(tmp_path)
    _seed_latest_metrics(tmp_path)
    _write_json(
        tmp_path / "metrics" / "state" / "extensions.json",
        {
            "schema_version": 1,
            "collectors": [{"name": "bundle_size", "enabled": True, "optional": True}],
        },
    )
    payload = run_optional_collectors(tmp_path, run_id="module8-no-build")
    assert payload["collectors"]["bundle_size"]["status"] == "not_available"
    assert "webui/dist/bundle-stats.json not found" in payload["collectors"]["bundle_size"]["reason"]
