from __future__ import annotations

import argparse
import json
import shutil
import subprocess
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


def _run_command(command: list[str], cwd: Path) -> None:
    subprocess.run(
        command,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _build_svelte_dashboard_via_devcontainer(repo_root: Path) -> None:
    if shutil.which("lxc") is None:
        raise FileNotFoundError("npm is unavailable and lxc fallback is not installed")

    command = (
        "set -euo pipefail && "
        "lxc exec dev-photo-ingress -- rm -rf /opt/nightfall-metrics && "
        "lxc exec dev-photo-ingress -- mkdir -p /opt/nightfall-metrics && "
        "tar -czf - metrics/dashboard artifacts/metrics/latest artifacts/metrics/history "
        "| lxc exec dev-photo-ingress -- tar -xzf - -C /opt/nightfall-metrics && "
        "lxc exec dev-photo-ingress -- bash -lc 'cd /opt/nightfall-metrics/metrics/dashboard && npm install --no-fund --no-audit && npm run build' && "
        "rm -rf dashboard && mkdir -p dashboard && "
        "lxc exec dev-photo-ingress -- tar -czf - -C /opt/nightfall-metrics dashboard "
        "| tar -xzf - -C ."
    )
    subprocess.run(
        ["bash", "-lc", command],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )


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


def _build_svelte_dashboard(repo_root: Path) -> None:
    app_root = repo_root / "metrics" / "dashboard"
    if not app_root.exists():
        raise FileNotFoundError("metrics/dashboard SvelteKit project is missing")

    if shutil.which("npm") is None:
        _build_svelte_dashboard_via_devcontainer(repo_root)
        return

    node_modules = app_root / "node_modules"
    if not node_modules.exists():
        _run_command(["npm", "install", "--no-fund", "--no-audit"], cwd=app_root)

    _run_command(["npm", "run", "build"], cwd=app_root)


def run_dashboard_generation(repo_root: Path, run_id: str) -> dict[str, Any]:
    latest_root = repo_root / "artifacts" / "metrics" / "latest"
    manifest = _read_json(latest_root / "manifest.json")
    metrics = _read_json(latest_root / "metrics.json")
    summary = _read_json(latest_root / "summary.json")

    trends = _history_trend(repo_root=repo_root, current_run_id=run_id)

    executive_md = _render_markdown_summary(run_id=run_id, summary=summary, trends=trends)

    _build_svelte_dashboard(repo_root)

    dashboard_dir = repo_root / "dashboard"
    report_path = repo_root / "reports" / "latest.md"
    staged_dashboard_dir = repo_root / "metrics" / "output" / "dashboard" / run_id
    staged_report = repo_root / "metrics" / "output" / "reports" / run_id / "latest.md"

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
