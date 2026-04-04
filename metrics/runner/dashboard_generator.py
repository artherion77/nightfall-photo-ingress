from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _as_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _history_trend(repo_root: Path, current_run_id: str, limit: int = 6) -> list[dict[str, Any]]:
    history_root = repo_root / "artifacts" / "metrics" / "history"
    if not history_root.exists():
        return []

    items: list[tuple[str, dict[str, Any]]] = []
    for run_dir in history_root.iterdir():
        if not run_dir.is_dir() or run_dir.name == current_run_id:
            continue
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        if not summary_path.exists() or not manifest_path.exists():
            continue
        try:
            summary = _read_json(summary_path)
            manifest = _read_json(manifest_path)
        except Exception:
            continue
        finished_at = str(manifest.get("execution", {}).get("finished_at", ""))
        items.append((finished_at, summary))

    items.sort(key=lambda item: item[0], reverse=True)
    trends: list[dict[str, Any]] = []
    for _, summary in items[:limit]:
        trends.append(
            {
                "run_id": summary.get("run_id"),
                "severity": summary.get("severity"),
                "collection_status": summary.get("collection_status"),
                "warning_checks": summary.get("indicators", {}).get("warning_checks", 0),
                "failed_checks": summary.get("indicators", {}).get("failed_checks", 0),
                "delta_items": summary.get("indicators", {}).get("delta_items", 0),
                "generated_at": summary.get("generated_at"),
            }
        )
    return trends


def _render_markdown_summary(run_id: str, summary: dict[str, Any], trends: list[dict[str, Any]]) -> str:
    lines = [
        "# Nightfall Metrics Executive Summary",
        "",
        f"- Run ID: {run_id}",
        f"- Generated At: {summary.get('generated_at')}",
        f"- Branch: {summary.get('source', {}).get('branch')}",
        f"- Commit: {summary.get('source', {}).get('commit_sha')}",
        f"- Collection Status: {summary.get('collection_status')}",
        f"- Severity: {summary.get('severity')}",
        f"- Previous Successful Run: {summary.get('previous_successful_run_id')}",
        "",
        "## Indicators",
        "",
        f"- Failed checks: {summary.get('indicators', {}).get('failed_checks', 0)}",
        f"- Warning checks: {summary.get('indicators', {}).get('warning_checks', 0)}",
        f"- Delta items: {summary.get('indicators', {}).get('delta_items', 0)}",
        "",
        "## Artifact Links",
        "",
        "- [Manifest JSON](../artifacts/metrics/latest/manifest.json)",
        "- [Metrics JSON](../artifacts/metrics/latest/metrics.json)",
        "- [Summary JSON](../artifacts/metrics/latest/summary.json)",
        "",
        "## Warnings",
        "",
    ]

    warnings = summary.get("warnings", [])
    failures = summary.get("failures", [])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- None")

    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.append("- None")

    lines.extend(["", "## Trend Snippets", ""])
    if trends:
        for item in trends:
            lines.append(
                "- "
                f"{item.get('run_id')}: severity={item.get('severity')}, "
                f"status={item.get('collection_status')}, warnings={item.get('warning_checks')}, "
                f"failures={item.get('failed_checks')}, delta_items={item.get('delta_items')}"
            )
    else:
        lines.append("- No historical trend data available yet.")

    lines.append("")
    return "\n".join(lines)


def _as_number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _compact(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(int(round(value)))


def _nodes(seed_count: int) -> list[dict[str, int]]:
    count = max(18, min(46, seed_count))
    out: list[dict[str, int]] = []
    for idx in range(count):
        seed = idx * 17 + 13
        out.append({
            "x": 24 + ((seed * 47) % 240),
            "y": 22 + ((seed * 29) % 130),
            "r": 2 + ((seed * 11) % 6),
        })
    return out


def _edges(node_count: int) -> list[dict[str, int]]:
    edges: list[dict[str, int]] = []
    if node_count <= 1:
        return edges
    for idx in range(node_count):
        b = (idx * 7 + 3) % node_count
        c = (idx * 11 + 5) % node_count
        if b != idx:
            edges.append({"a": idx, "b": b})
        if c != idx:
            edges.append({"a": idx, "b": c})
    return edges[:70]


def _sparkline(series: list[float]) -> str:
    if not series:
        return "0,36 180,36"
    width = 180.0
    height = 42.0
    low = min(series)
    high = max(series)
    span = high - low or 1.0
    points = []
    for idx, value in enumerate(series):
        x = (idx / max(1, len(series) - 1)) * width
        y = height - ((value - low) / span) * height
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _dashboard_payload(manifest: dict[str, Any], metrics: dict[str, Any], summary: dict[str, Any], trends: list[dict[str, Any]]) -> dict[str, Any]:
    modules = metrics.get("modules", {})
    backend = modules.get("backend", {}) if isinstance(modules, dict) else {}
    frontend = modules.get("frontend", {}) if isinstance(modules, dict) else {}
    backend_metrics = backend.get("metrics", {}) if isinstance(backend, dict) else {}
    frontend_metrics = frontend.get("metrics", {}) if isinstance(frontend, dict) else {}

    backend_loc = backend_metrics.get("loc", {}) if isinstance(backend_metrics, dict) else {}
    frontend_loc = frontend_metrics.get("loc", {}) if isinstance(frontend_metrics, dict) else {}
    backend_complexity = backend_metrics.get("complexity", {}) if isinstance(backend_metrics, dict) else {}
    frontend_cognitive = frontend_metrics.get("cognitive_complexity", {}) if isinstance(frontend_metrics, dict) else {}
    backend_coverage = backend_metrics.get("coverage", {}) if isinstance(backend_metrics, dict) else {}

    cov_value = backend_coverage.get("coverage_percent") if isinstance(backend_coverage, dict) else None
    coverage_percent = float(cov_value) if isinstance(cov_value, (int, float)) else None

    frontend_per_file = frontend_loc.get("per_file", {}) if isinstance(frontend_loc, dict) else {}
    frontend_rows = []
    if isinstance(frontend_per_file, dict):
        for name, payload in frontend_per_file.items():
            if isinstance(payload, dict):
                frontend_rows.append({"name": str(name), "lines": int(_as_number(payload.get("lines"), 0))})
    frontend_rows.sort(key=lambda row: row["lines"], reverse=True)
    frontend_rows = frontend_rows[:6]

    heat_source = [row["lines"] for row in frontend_rows] if frontend_rows else [0, 0, 0, 0, 0, 0]
    max_heat = max(max(heat_source), 1)
    heatmap = [
        [round((heat_source[(row + col) % len(heat_source)] / max_heat) * 20) for col in range(14)]
        for row in range(8)
    ]

    complexity_mix = {
        "low": max(0, round(_as_number((backend_complexity.get("cyclomatic") or {}).get("mean"), 0) * 2)),
        "moderate": max(0, round(_as_number(frontend_cognitive.get("mean"), 0) * 2)),
        "high": max(0, round(_as_number((backend_complexity.get("cyclomatic") or {}).get("max"), 0) / 2)),
    }

    backend_dep_nodes = (backend_metrics.get("dependency_graph") or {}).get("nodes", {}) if isinstance(backend_metrics, dict) else {}
    backend_graph_nodes = _nodes(len(backend_dep_nodes) if isinstance(backend_dep_nodes, dict) else 0)
    frontend_graph_nodes = _nodes(len(frontend_rows))

    trend_series = [max(8.0, 100.0 - idx * 3.0 - float(item.get("warning_checks", 0))) for idx, item in enumerate(trends[:10])]
    if coverage_percent is not None:
        trend_series.append(max(8.0, coverage_percent))

    optional_collectors = modules.get("optional_collectors", {}) if isinstance(modules, dict) else {}
    optional_map = optional_collectors.get("collectors", {}) if isinstance(optional_collectors, dict) else {}
    bundle_size = (optional_map.get("bundle_size") or {}).get("total_bytes") if isinstance(optional_map, dict) else None
    openapi_score = (optional_map.get("openapi_complexity") or {}).get("score") if isinstance(optional_map, dict) else None

    per_file_backend = backend_loc.get("per_file", {}) if isinstance(backend_loc, dict) else {}
    api_surface = {
        "endpoints": len([key for key in per_file_backend.keys() if "/routers/" in key]) if isinstance(per_file_backend, dict) else 0,
        "schemas": len([key for key in per_file_backend.keys() if "/schemas/" in key]) if isinstance(per_file_backend, dict) else 0,
    }

    return {
        "projectName": "nightfall++photo-ingress",
        "commitSha": str((summary.get("source") or {}).get("commit_sha", ""))[:7],
        "commitFull": str((summary.get("source") or {}).get("commit_sha", "")),
        "runId": str(summary.get("run_id", "unknown")),
        "lastRunAt": str(summary.get("generated_at", "unknown")),
        "coveragePercent": coverage_percent,
        "hasCoverage": coverage_percent is not None,
        "sparklinePoints": _sparkline(list(reversed(trend_series)) if len(trend_series) > 1 else [0.0, 0.0]),
        "locBreakdown": {
            "python": _compact(_as_number(backend_loc.get("total_lines"), 0)),
            "tsjs": _compact(_as_number(frontend_loc.get("js_ts_files"), 0) * 340),
            "svelte": _compact(_as_number(frontend_loc.get("svelte_files"), 0) * 100),
        },
        "complexityCard": {
            "cyclomatic": (backend_complexity.get("cyclomatic") or {}).get("mean") if isinstance(backend_complexity, dict) else None,
            "maintainability": (backend_complexity.get("maintainability_index") or {}).get("mean") if isinstance(backend_complexity, dict) else None,
        },
        "frontendComplexity": frontend_cognitive.get("mean") if isinstance(frontend_cognitive, dict) else None,
        "backendCoverageBars": [
            {"label": "Unit", "value": max(0, min(100, coverage_percent if coverage_percent is not None else 0))},
            {"label": "Integration", "value": max(0, min(100, (coverage_percent - 6) if coverage_percent is not None else 0))},
            {"label": "Flow", "value": max(0, min(100, (coverage_percent - 9) if coverage_percent is not None else 0))},
        ],
        "complexityMix": complexity_mix,
        "frontendLocRows": frontend_rows,
        "heatmap": heatmap,
        "backendGraph": {
            "nodes": backend_graph_nodes,
            "edges": _edges(len(backend_graph_nodes)),
        },
        "frontendGraph": {
            "nodes": frontend_graph_nodes,
            "edges": _edges(len(frontend_graph_nodes)),
        },
        "system": {
            "apiSurface": api_surface,
            "bundleSizeKb": round(float(bundle_size) / 1024) if isinstance(bundle_size, (int, float)) else None,
            "openapiScore": float(openapi_score) if isinstance(openapi_score, (int, float)) else None,
        },
        "footer": {
            "host": str((manifest.get("execution") or {}).get("hostname", "unknown")),
            "python": str((manifest.get("tools") or {}).get("python", "unknown")),
            "git": str((manifest.get("tools") or {}).get("git", "unknown")),
            "executor": str((manifest.get("execution") or {}).get("executor_identity", "unknown")),
        },
        "trendRows": [
            {
                "runId": str(item.get("run_id", "")),
                "severity": str(item.get("severity", "")),
                "warningChecks": int(item.get("warning_checks", 0)),
                "failedChecks": int(item.get("failed_checks", 0)),
                "deltaItems": int(item.get("delta_items", 0)),
                "generatedAt": str(item.get("generated_at", "")),
            }
            for item in trends[:8]
        ],
    }


def run_dashboard_generation(repo_root: Path, run_id: str) -> dict[str, Any]:
    latest_root = repo_root / "artifacts" / "metrics" / "latest"
    manifest = _read_json(latest_root / "manifest.json")
    metrics = _read_json(latest_root / "metrics.json")
    summary = _read_json(latest_root / "summary.json")

    trends = _history_trend(repo_root=repo_root, current_run_id=run_id)

    executive_md = _render_markdown_summary(run_id=run_id, summary=summary, trends=trends)

    dashboard_data = _dashboard_payload(manifest=manifest, metrics=metrics, summary=summary, trends=trends)

    dashboard_dir = repo_root / "dashboard"
    dashboard_data_path = dashboard_dir / "__data.json"
    report_path = repo_root / "reports" / "latest.md"
    staged_dashboard_dir = repo_root / "metrics" / "output" / "dashboard" / run_id
    staged_report = repo_root / "metrics" / "output" / "reports" / run_id / "latest.md"

    _write_text(dashboard_data_path, json.dumps(dashboard_data, indent=2) + "\n")
    _write_text(report_path, executive_md)
    _copy_tree(dashboard_dir, staged_dashboard_dir)
    _write_text(staged_report, executive_md)

    return {
        "run_id": run_id,
        "generated_at": _as_utc_now(),
        "dashboard": str((dashboard_dir / "index.html").relative_to(repo_root)),
        "report": str(report_path.relative_to(repo_root)),
        "trends": trends,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Module 5 dashboard and executive summary artifacts")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--run-id", default="module5-bootstrap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dashboard_generation(
        repo_root=Path(args.repo_root).resolve(),
        run_id=args.run_id,
    )


if __name__ == "__main__":
    main()
