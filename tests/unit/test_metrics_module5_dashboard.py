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

    (tmp_path / "dashboard").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard" / "index.html").write_text("<html>static-frame</html>", encoding="utf-8")

    result = dashboard_generator.run_dashboard_generation(tmp_path, run_id="module5-bootstrap")

    dashboard_path = tmp_path / "dashboard" / "index.html"
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
    assert result["dashboard"] == "dashboard/index.html"
    assert result["report"] == "metrics/output/reports/latest.md"

    dashboard_html = dashboard_path.read_text(encoding="utf-8")
    dashboard_data = json.loads(dashboard_data_path.read_text(encoding="utf-8"))
    report_md = report_path.read_text(encoding="utf-8")

    assert "static-frame" in dashboard_html
    assert dashboard_data["runId"] == "module4-bootstrap"
    assert "Nightfall Metrics Executive Summary" in report_md
    assert "Artifact Links" in report_md
