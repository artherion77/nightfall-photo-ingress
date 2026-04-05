from __future__ import annotations

import json
from pathlib import Path

from metrics.runner import dashboard_generator


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_module5_dashboard_generation_from_artifacts_only(tmp_path: Path) -> None:
    latest = tmp_path / "artifacts" / "metrics" / "latest"
    history = tmp_path / "artifacts" / "metrics" / "history" / "module4-bootstrap"

    _write_json(
        latest / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "module4-bootstrap",
            "execution": {"exit_state": "success", "finished_at": "2026-04-04T01:00:00+00:00"},
        },
    )
    _write_json(
        latest / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "module4-bootstrap",
            "modules": {
                "backend": {"status": "partial", "metrics": {"loc": {"total_lines": 100}}},
                "frontend": {"status": "partial", "metrics": {"loc": {"total_lines": 50}}},
            },
            "delta": {
                "previous_run_id": "module3-bootstrap",
                "comparisons": {
                    "modules.backend.metrics.loc.total_lines": {
                        "previous": 90,
                        "current": 100,
                        "change": 10,
                    }
                },
            },
        },
    )
    _write_json(
        latest / "summary.json",
        {
            "schema_version": 1,
            "run_id": "module4-bootstrap",
            "generated_at": "2026-04-04T01:00:00+00:00",
            "source": {"branch": "main", "commit_sha": "a" * 40},
            "collection_status": "partial",
            "severity": "warning",
            "indicators": {"failed_checks": 0, "warning_checks": 1, "delta_items": 1},
            "previous_successful_run_id": "module3-bootstrap",
            "warnings": ["modules.backend.metrics.coverage not available"],
            "failures": [],
        },
    )

    _write_json(
        history / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "module4-bootstrap",
            "execution": {"exit_state": "success", "finished_at": "2026-04-04T00:30:00+00:00"},
        },
    )
    _write_json(
        history / "summary.json",
        {
            "run_id": "module4-bootstrap",
            "generated_at": "2026-04-04T00:30:00+00:00",
            "severity": "warning",
            "collection_status": "partial",
            "indicators": {"warning_checks": 2, "failed_checks": 0, "delta_items": 5},
        },
    )

    (tmp_path / "metrics" / "output" / "dashboard" / "static").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics" / "output" / "dashboard" / "static" / "index.html").write_text("<html>static-frame</html>", encoding="utf-8")

    result = dashboard_generator.run_dashboard_generation(tmp_path, run_id="module5-bootstrap")

    dashboard_path = tmp_path / "metrics" / "output" / "dashboard" / "static" / "index.html"
    dashboard_data_path = tmp_path / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    report_path = tmp_path / "metrics" / "output" / "reports" / "latest.md"
    staged_dashboard = tmp_path / "metrics" / "output" / "dashboard" / "module5-bootstrap" / "index.html"
    staged_dashboard_data = tmp_path / "metrics" / "output" / "dashboard" / "module5-bootstrap" / "__data.json"
    staged_report = tmp_path / "metrics" / "output" / "reports" / "module5-bootstrap" / "latest.md"

    assert dashboard_path.exists()
    assert dashboard_data_path.exists()
    assert report_path.exists()
    assert staged_dashboard.exists()
    assert staged_dashboard_data.exists()
    assert staged_report.exists()
    assert result["dashboard"] == "metrics/output/dashboard/static/index.html"
    assert result["report"] == "metrics/output/reports/latest.md"

    dashboard_html = dashboard_path.read_text(encoding="utf-8")
    dashboard_data = json.loads(dashboard_data_path.read_text(encoding="utf-8"))
    report_md = report_path.read_text(encoding="utf-8")

    assert "static-frame" in dashboard_html
    assert dashboard_data["runId"] == "module4-bootstrap"
    assert "Nightfall Metrics Executive Summary" in report_md
    assert "Artifact Links" in report_md

    # Chunk 0 payload contract assertions for required dashboard fields.
    assert isinstance(dashboard_data.get("runId"), str)
    assert isinstance(dashboard_data.get("lastRunAt"), str)

    assert "repoUrl" in dashboard_data
    assert "repoHeadUrl" in dashboard_data
    assert "repoCommitUrl" in dashboard_data
    assert dashboard_data["repoUrl"] is None or isinstance(dashboard_data["repoUrl"], str)
    assert dashboard_data["repoHeadUrl"] is None or isinstance(dashboard_data["repoHeadUrl"], str)
    assert dashboard_data["repoCommitUrl"] is None or isinstance(dashboard_data["repoCommitUrl"], str)

    assert "versions" in dashboard_data
    assert isinstance(dashboard_data["versions"], dict)
    assert "python" in dashboard_data["versions"]
    assert "typescript" in dashboard_data["versions"]
    assert dashboard_data["versions"]["python"] is None or isinstance(dashboard_data["versions"]["python"], str)
    assert dashboard_data["versions"]["typescript"] is None or isinstance(dashboard_data["versions"]["typescript"], str)

    assert "runMeta" in dashboard_data
    assert isinstance(dashboard_data["runMeta"], dict)
    assert "startedAt" in dashboard_data["runMeta"]
    assert "finishedAt" in dashboard_data["runMeta"]
    assert "durationSeconds" in dashboard_data["runMeta"]
    assert isinstance(dashboard_data["runMeta"]["startedAt"], str)
    assert isinstance(dashboard_data["runMeta"]["finishedAt"], str)
    assert dashboard_data["runMeta"]["durationSeconds"] is None or isinstance(
        dashboard_data["runMeta"]["durationSeconds"],
        (int, float),
    )

    # Chunk 1: Sparkline correctness assertions
    assert "sparklinePoints" in dashboard_data
    assert "coverageTrendSource" in dashboard_data
    # If measured history is available, sparkline should reflect it and provenance should be 'measured_history'
    # In this test, no measured coverage is present, so fallback should be used
    if dashboard_data["coverageTrendSource"] == "measured_history":
        # Should not use warning_checks for sparkline
        assert all(
            pt != 100.0 - idx * 3.0 - float(1)  # warning_checks=1 in this test
            for idx, pt in enumerate([float(x.split(",")[1]) for x in dashboard_data["sparklinePoints"].split()])
        )
    else:
        # Fallback: flat line (SVG height is 42.0)
        assert dashboard_data["sparklinePoints"] == "0.00,42.00 180.00,42.00"

    # Chunk 4: bundleSizeDetail must be null when no optional collector data is present.
    assert "system" in dashboard_data
    assert "bundleSizeDetail" in dashboard_data["system"]
    assert dashboard_data["system"]["bundleSizeDetail"] is None
    assert dashboard_data["system"]["bundleSizeKb"] is None

    # Chunk 5: nodeDetails must be present in both graph payload sections.
    assert "backendGraph" in dashboard_data
    assert "frontendGraph" in dashboard_data
    assert isinstance(dashboard_data["backendGraph"]["nodeDetails"], list)
    assert isinstance(dashboard_data["frontendGraph"]["nodeDetails"], list)


def test_module5_lastRunAt_uses_finished_at(tmp_path: Path) -> None:
    """lastRunAt should prefer manifest execution.finished_at over summary.generated_at."""
    latest = tmp_path / "artifacts" / "metrics" / "latest"

    _write_json(
        latest / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "ts-test",
            "execution": {
                "exit_state": "success",
                "finished_at": "2026-05-01T12:00:00+00:00",
            },
        },
    )
    _write_json(
        latest / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "ts-test",
            "modules": {
                "backend": {"status": "partial", "metrics": {"loc": {"total_lines": 10}}},
                "frontend": {"status": "partial", "metrics": {"loc": {"total_lines": 5}}},
            },
            "delta": {"previous_run_id": None, "comparisons": {}},
        },
    )
    _write_json(
        latest / "summary.json",
        {
            "schema_version": 1,
            "run_id": "ts-test",
            "generated_at": "2026-04-01T00:00:00+00:00",
            "source": {"branch": "main", "commit_sha": "b" * 40},
            "collection_status": "partial",
            "severity": "info",
            "indicators": {"failed_checks": 0, "warning_checks": 0, "delta_items": 0},
            "warnings": [],
            "failures": [],
        },
    )

    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("<html></html>", encoding="utf-8")

    dashboard_generator.run_dashboard_generation(tmp_path, run_id="ts-test")
    data_path = tmp_path / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    # Should use finished_at, NOT generated_at
    assert data["lastRunAt"] == "2026-05-01T12:00:00+00:00"


def test_module5_collectorStatuses_present(tmp_path: Path) -> None:
    """Dashboard payload must contain collectorStatuses for all four collectors."""
    latest = tmp_path / "artifacts" / "metrics" / "latest"

    _write_json(
        latest / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "cs-test",
            "execution": {"exit_state": "success", "finished_at": "2026-05-01T12:00:00+00:00"},
        },
    )
    _write_json(
        latest / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "cs-test",
            "modules": {
                "backend": {
                    "status": "success",
                    "metrics": {
                        "loc": {"total_lines": 10},
                        "complexity": {"status": "available", "reason": None},
                        "coverage": {"status": "not_available", "reason": "pytest not found"},
                    },
                },
                "frontend": {
                    "status": "success",
                    "metrics": {
                        "loc": {"total_lines": 5},
                        "cognitive_complexity": {"status": "error", "reason": "tree-sitter missing"},
                    },
                },
            },
            "delta": {"previous_run_id": None, "comparisons": {}},
        },
    )
    _write_json(
        latest / "summary.json",
        {
            "schema_version": 1,
            "run_id": "cs-test",
            "generated_at": "2026-05-01T12:00:00+00:00",
            "source": {"branch": "main", "commit_sha": "c" * 40},
            "collection_status": "success",
            "severity": "info",
            "indicators": {"failed_checks": 0, "warning_checks": 0, "delta_items": 0},
            "warnings": [],
            "failures": [],
        },
    )

    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("<html></html>", encoding="utf-8")

    dashboard_generator.run_dashboard_generation(tmp_path, run_id="cs-test")
    data_path = tmp_path / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    assert "collectorStatuses" in data
    cs = data["collectorStatuses"]
    assert set(cs.keys()) == {"backendComplexity", "frontendCognitive", "coverage", "bundleSize"}
    for key, entry in cs.items():
        assert "status" in entry
        assert "reason" in entry


def test_module5_buildStamp_present(tmp_path: Path) -> None:
    """Dashboard payload must contain buildStamp with generatedAt, commitSha, runId."""
    latest = tmp_path / "artifacts" / "metrics" / "latest"

    _write_json(
        latest / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "bs-test",
            "execution": {"exit_state": "success", "finished_at": "2026-05-01T12:00:00+00:00"},
        },
    )
    _write_json(
        latest / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "bs-test",
            "modules": {
                "backend": {"status": "partial", "metrics": {"loc": {"total_lines": 10}}},
                "frontend": {"status": "partial", "metrics": {"loc": {"total_lines": 5}}},
            },
            "delta": {"previous_run_id": None, "comparisons": {}},
        },
    )
    _write_json(
        latest / "summary.json",
        {
            "schema_version": 1,
            "run_id": "bs-test",
            "generated_at": "2026-05-01T12:00:00+00:00",
            "source": {"branch": "main", "commit_sha": "d" * 40},
            "collection_status": "partial",
            "severity": "info",
            "indicators": {"failed_checks": 0, "warning_checks": 0, "delta_items": 0},
            "warnings": [],
            "failures": [],
        },
    )

    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("<html></html>", encoding="utf-8")

    dashboard_generator.run_dashboard_generation(tmp_path, run_id="bs-test")
    data_path = tmp_path / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    assert "buildStamp" in data
    bs = data["buildStamp"]
    assert "generatedAt" in bs
    assert "commitSha" in bs
    assert "runId" in bs
    assert isinstance(bs["generatedAt"], str)
    assert bs["runId"] == "bs-test"


def test_module5_complexity_mix_matches_breakdown_totals(tmp_path: Path) -> None:
    """Donut mix must use the same category totals as complexityBreakdownDetail."""
    latest = tmp_path / "artifacts" / "metrics" / "latest"

    _write_json(
        latest / "manifest.json",
        {
            "schema_version": 1,
            "run_id": "mix-test",
            "execution": {"exit_state": "success", "finished_at": "2026-05-01T12:00:00+00:00"},
        },
    )
    _write_json(
        latest / "metrics.json",
        {
            "schema_version": 1,
            "run_id": "mix-test",
            "modules": {
                "backend": {
                    "status": "success",
                    "metrics": {
                        "loc": {"total_lines": 10},
                        "complexity": {
                            "status": "success",
                            "cyclomatic": {"mean": 3.2, "max": 12.0},
                            "per_file": {
                                "api/a.py": {"cyclomatic_avg": 12.0},
                                "api/b.py": {"cyclomatic_avg": 11.0},
                                "api/c.py": {"cyclomatic_avg": 10.0},
                                "api/d.py": {"cyclomatic_avg": 7.0},
                                "api/e.py": {"cyclomatic_avg": 6.0},
                                "api/f.py": {"cyclomatic_avg": 3.0},
                            },
                        },
                    },
                },
                "frontend": {
                    "status": "success",
                    "metrics": {
                        "loc": {"total_lines": 5},
                        "cognitive_complexity": {
                            "status": "available",
                            "mean": 1.2,
                            "per_file": {
                                "webui/src/a.ts": 1.0,
                                "webui/src/b.ts": 2.0,
                                "webui/src/c.ts": 3.0,
                                "webui/src/d.ts": 4.0,
                            },
                        },
                    },
                },
            },
            "delta": {"previous_run_id": None, "comparisons": {}},
        },
    )
    _write_json(
        latest / "summary.json",
        {
            "schema_version": 1,
            "run_id": "mix-test",
            "generated_at": "2026-05-01T12:00:00+00:00",
            "source": {"branch": "main", "commit_sha": "e" * 40},
            "collection_status": "success",
            "severity": "info",
            "indicators": {"failed_checks": 0, "warning_checks": 0, "delta_items": 0},
            "warnings": [],
            "failures": [],
        },
    )

    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("<html></html>", encoding="utf-8")

    dashboard_generator.run_dashboard_generation(tmp_path, run_id="mix-test")
    data_path = tmp_path / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    detail = data["complexityBreakdownDetail"]
    mix = data["complexityMix"]
    assert mix["low"] == detail["low"]["totalModules"]
    assert mix["moderate"] == detail["moderate"]["totalModules"]
    assert mix["high"] == detail["high"]["totalModules"]


def test_module5_complexity_tooltip_header_not_hardcoded() -> None:
    """Tooltip header must use dynamic top count instead of hardcoded Top 10."""
    root = Path(__file__).resolve().parents[2]
    svelte_path = root / "metrics" / "dashboard" / "src" / "routes" / "+page.svelte"
    source = svelte_path.read_text(encoding="utf-8")

    assert "Top 10 / {detail.totalModules} modules contributing to" not in source
    assert "Top {detail.topModules.length} / {detail.totalModules} modules contributing to" in source
