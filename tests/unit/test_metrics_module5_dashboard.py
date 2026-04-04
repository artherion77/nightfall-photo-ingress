from __future__ import annotations

import json
from pathlib import Path

from metrics.runner import dashboard_generator


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_module5_dashboard_generation_from_artifacts_only(tmp_path: Path, monkeypatch) -> None:
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

    (tmp_path / "metrics" / "dashboard").mkdir(parents=True, exist_ok=True)

    def _fake_build(repo_root: Path) -> None:
        (repo_root / "dashboard").mkdir(parents=True, exist_ok=True)
        (repo_root / "dashboard" / "index.html").write_text("<html>svelte-build</html>", encoding="utf-8")

    monkeypatch.setattr(dashboard_generator, "_build_svelte_dashboard", _fake_build)

    result = dashboard_generator.run_dashboard_generation(tmp_path, run_id="module5-bootstrap")

    dashboard_path = tmp_path / "dashboard" / "index.html"
    report_path = tmp_path / "reports" / "latest.md"
    staged_dashboard = tmp_path / "metrics" / "output" / "dashboard" / "module5-bootstrap" / "index.html"
    staged_report = tmp_path / "metrics" / "output" / "reports" / "module5-bootstrap" / "latest.md"

    assert dashboard_path.exists()
    assert report_path.exists()
    assert staged_dashboard.exists()
    assert staged_report.exists()
    assert result["dashboard"] == "dashboard/index.html"
    assert result["report"] == "reports/latest.md"

    dashboard_html = dashboard_path.read_text(encoding="utf-8")
    report_md = report_path.read_text(encoding="utf-8")

    assert "svelte-build" in dashboard_html
    assert "Nightfall Metrics Executive Summary" in report_md
    assert "Artifact Links" in report_md
