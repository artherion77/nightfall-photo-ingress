from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
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
    trend_items = []
    for run_dir in history_root.iterdir():
        if not run_dir.is_dir() or run_dir.name == current_run_id:
            continue
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        metrics_path = run_dir / "metrics.json"
        if not summary_path.exists() or not manifest_path.exists() or not metrics_path.exists():
            continue
        try:
            summary = _read_json(summary_path)
            manifest = _read_json(manifest_path)
            metrics = _read_json(metrics_path)
        except Exception:
            continue
        finished_at = str(manifest.get("execution", {}).get("finished_at", ""))
        # Extract measured coverage percent if available
        modules = metrics.get("modules", {})
        backend = modules.get("backend", {}) if isinstance(modules, dict) else {}
        backend_metrics = backend.get("metrics", {}) if isinstance(backend, dict) else {}
        backend_coverage = backend_metrics.get("coverage", {}) if isinstance(backend_metrics, dict) else {}
        cov_value = backend_coverage.get("coverage_percent") if isinstance(backend_coverage, dict) else None
        coverage_percent = float(cov_value) if isinstance(cov_value, (int, float)) else None
        trend_items.append(
            {
                "run_id": summary.get("run_id"),
                "severity": summary.get("severity"),
                "collection_status": summary.get("collection_status"),
                "warning_checks": summary.get("indicators", {}).get("warning_checks", 0),
                "failed_checks": summary.get("indicators", {}).get("failed_checks", 0),
                "delta_items": summary.get("indicators", {}).get("delta_items", 0),
                "generated_at": summary.get("generated_at"),
                "coverage_percent": coverage_percent,
            }
        )
    # Sort by generated_at descending
    trend_items.sort(key=lambda item: item["generated_at"] or "", reverse=True)
    return trend_items[:limit]


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


def _origin_repo_url(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    raw = (proc.stdout or "").strip()
    if not raw:
        return None

    if raw.startswith("git@") and ":" in raw:
        host_part, repo_part = raw.split(":", 1)
        host = host_part.split("@", 1)[1]
        normalized = f"https://{host}/{repo_part}"
    elif raw.startswith("ssh://git@"):
        normalized = "https://" + raw[len("ssh://git@"):]
    else:
        normalized = raw

    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    return normalized


def _strip_semver_prefix(raw: str) -> str:
    value = raw.strip()
    while value and value[0] in "^~<>= ":
        value = value[1:]
    return value


def _typescript_version(repo_root: Path) -> str | None:
    pkg = repo_root / "metrics" / "dashboard" / "package.json"
    if not pkg.exists():
        return None
    try:
        payload = _read_json(pkg)
    except Exception:
        return None
    deps = payload.get("devDependencies") if isinstance(payload, dict) else None
    if not isinstance(deps, dict):
        return None
    raw = deps.get("typescript")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _strip_semver_prefix(raw)


def _probe_python_version(executable: str | None) -> str | None:
    if not executable:
        return None
    try:
        proc = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    version_out = (proc.stdout or proc.stderr or "").strip()
    if not version_out:
        return None
    return version_out


def _footer_python_text(manifest: dict[str, Any], backend_coverage: dict[str, Any]) -> str:
    tools = manifest.get("tools") if isinstance(manifest, dict) else {}
    if isinstance(tools, dict):
        value = tools.get("python")
        if isinstance(value, str) and value and value != "unknown":
            return value

    exe = backend_coverage.get("python_executable") if isinstance(backend_coverage, dict) else None
    probed = _probe_python_version(str(exe)) if isinstance(exe, str) and exe else None
    if probed:
        return probed

    return f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _validate_dashboard_payload_contract(payload: dict[str, Any]) -> None:
    required_top_level = ["runId", "lastRunAt", "repoUrl", "repoHeadUrl", "repoCommitUrl", "versions", "runMeta"]
    for key in required_top_level:
        if key not in payload:
            raise ValueError(f"dashboard payload missing required key: {key}")

    run_id = payload.get("runId")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("dashboard payload runId must be a non-empty string")

    last_run_at = payload.get("lastRunAt")
    if not isinstance(last_run_at, str) or not last_run_at:
        raise ValueError("dashboard payload lastRunAt must be a non-empty string")

    for key in ("repoUrl", "repoHeadUrl", "repoCommitUrl"):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"dashboard payload {key} must be a string or null")

    versions = payload.get("versions")
    if not isinstance(versions, dict):
        raise ValueError("dashboard payload versions must be an object")
    for key in ("python", "typescript"):
        if key not in versions:
            raise ValueError(f"dashboard payload versions missing required key: {key}")
        value = versions.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"dashboard payload versions.{key} must be a string or null")

    run_meta = payload.get("runMeta")
    if not isinstance(run_meta, dict):
        raise ValueError("dashboard payload runMeta must be an object")
    for key in ("startedAt", "finishedAt", "durationSeconds"):
        if key not in run_meta:
            raise ValueError(f"dashboard payload runMeta missing required key: {key}")

    started_at = run_meta.get("startedAt")
    if not isinstance(started_at, str):
        raise ValueError("dashboard payload runMeta.startedAt must be a string")

    finished_at = run_meta.get("finishedAt")
    if not isinstance(finished_at, str):
        raise ValueError("dashboard payload runMeta.finishedAt must be a string")

    duration_seconds = run_meta.get("durationSeconds")
    if duration_seconds is not None and not isinstance(duration_seconds, (int, float)):
        raise ValueError("dashboard payload runMeta.durationSeconds must be numeric or null")


def _dashboard_payload(repo_root: Path, manifest: dict[str, Any], metrics: dict[str, Any], summary: dict[str, Any], trends: list[dict[str, Any]]) -> dict[str, Any]:
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

    # Build trend series from measured historical coverage if available
    measured_trend = [item["coverage_percent"] for item in trends if item.get("coverage_percent") is not None]
    if coverage_percent is not None:
        measured_trend.append(coverage_percent)
    # Fallback: flat line if fewer than 2 measured points
    if len(measured_trend) < 2:
        trend_series = [0.0, 0.0]
        coverage_trend_source = "fallback_flat"
    else:
        trend_series = measured_trend[-7:]  # last 6 history + current
        coverage_trend_source = "measured_history"

    optional_collectors = modules.get("optional_collectors", {}) if isinstance(modules, dict) else {}
    optional_map = optional_collectors.get("collectors", {}) if isinstance(optional_collectors, dict) else {}
    bundle_entry = (optional_map.get("bundle_size") or {}) if isinstance(optional_map, dict) else {}
    bundle_status = bundle_entry.get("status")
    bundle_total_kb = bundle_entry.get("total_kb") if bundle_status == "available" else None
    bundle_gzip_kb = bundle_entry.get("gzip_kb") if bundle_status == "available" else None
    bundle_brotli_kb = bundle_entry.get("brotli_kb") if bundle_status == "available" else None
    bundle_largest_chunk = bundle_entry.get("largest_chunk") if bundle_status == "available" else None
    bundle_top_contributors = bundle_entry.get("top_contributors") if bundle_status == "available" else None
    openapi_score = (optional_map.get("openapi_complexity") or {}).get("score") if isinstance(optional_map, dict) else None

    per_file_backend = backend_loc.get("per_file", {}) if isinstance(backend_loc, dict) else {}
    source_branch = str((summary.get("source") or {}).get("branch", "main"))
    commit_full = str((summary.get("source") or {}).get("commit_sha", ""))
    repo_url = _origin_repo_url(repo_root)
    repo_head_url = f"{repo_url}/tree/{source_branch}" if repo_url else None
    repo_commit_url = f"{repo_url}/commit/{commit_full}" if repo_url and commit_full else None
    execution = manifest.get("execution") if isinstance(manifest, dict) else {}
    started_at = str((execution or {}).get("started_at", "")) if isinstance(execution, dict) else ""
    finished_at = str((execution or {}).get("finished_at", "")) if isinstance(execution, dict) else ""
    duration_seconds = (execution or {}).get("duration_seconds") if isinstance(execution, dict) else None
    typescript_version = _typescript_version(repo_root)
    python_version = _footer_python_text(manifest, backend_coverage)
    api_surface = {
        "endpoints": len([key for key in per_file_backend.keys() if "/routers/" in key]) if isinstance(per_file_backend, dict) else 0,
        "schemas": len([key for key in per_file_backend.keys() if "/schemas/" in key]) if isinstance(per_file_backend, dict) else 0,
    }

    return {
        "projectName": "nightfall++photo-ingress",
        "commitSha": commit_full[:7],
        "commitFull": commit_full,
        "runId": str(summary.get("run_id", "unknown")),
        "lastRunAt": str(summary.get("generated_at", "unknown")),
        "sourceBranch": source_branch,
        "repoUrl": repo_url,
        "repoHeadUrl": repo_head_url,
        "repoCommitUrl": repo_commit_url,
        "runMeta": {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationSeconds": float(duration_seconds) if isinstance(duration_seconds, (int, float)) else None,
            "runId": str(summary.get("run_id", "unknown")),
            "branch": source_branch,
        },
        "versions": {
            "python": python_version,
            "typescript": typescript_version,
        },
        "coveragePercent": coverage_percent,
        "hasCoverage": coverage_percent is not None,
        "sparklinePoints": _sparkline(list(reversed(trend_series)) if len(trend_series) > 1 else [0.0, 0.0]),
        "coverageTrendSource": coverage_trend_source,
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
            "bundleSizeKb": round(float(bundle_total_kb)) if isinstance(bundle_total_kb, (int, float)) else None,
            "bundleSizeDetail": {
                "totalKb": bundle_total_kb,
                "gzipKb": bundle_gzip_kb,
                "brotliKb": bundle_brotli_kb,
                "largestChunk": bundle_largest_chunk,
                "topContributors": bundle_top_contributors,
            } if bundle_status == "available" else None,
            "openapiScore": float(openapi_score) if isinstance(openapi_score, (int, float)) else None,
        },
        "footer": {
            "host": str((manifest.get("execution") or {}).get("hostname", "unknown")),
            "python": python_version,
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

    dashboard_data = _dashboard_payload(repo_root=repo_root, manifest=manifest, metrics=metrics, summary=summary, trends=trends)
    _validate_dashboard_payload_contract(dashboard_data)

    dashboard_dir = repo_root / "dashboard"
    output_dashboard_latest = repo_root / "metrics" / "output" / "dashboard" / "latest"
    output_reports_latest = repo_root / "metrics" / "output" / "reports"
    dashboard_data_path = output_dashboard_latest / "__data.json"
    report_path = output_reports_latest / "latest.md"
    staged_dashboard_dir = repo_root / "metrics" / "output" / "dashboard" / run_id
    staged_report = repo_root / "metrics" / "output" / "reports" / run_id / "latest.md"

    _write_text(dashboard_data_path, json.dumps(dashboard_data, indent=2) + "\n")
    _write_text(report_path, executive_md)
    _copy_tree(dashboard_dir, staged_dashboard_dir)
    _write_text(staged_dashboard_dir / "__data.json", json.dumps(dashboard_data, indent=2) + "\n")
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
