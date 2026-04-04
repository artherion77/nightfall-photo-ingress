from __future__ import annotations

import argparse
import html
import json
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


def _render_html_dashboard(
    run_id: str,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    summary: dict[str, Any],
    trends: list[dict[str, Any]],
) -> str:
    backend = metrics.get("modules", {}).get("backend", {})
    frontend = metrics.get("modules", {}).get("frontend", {})
    delta = metrics.get("delta", {})
    comparisons = delta.get("comparisons", {})

    warning_list = summary.get("warnings", [])
    failure_list = summary.get("failures", [])

    trend_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(str(item.get('run_id', '')))}</td>"
            f"<td>{html.escape(str(item.get('severity', '')))}</td>"
            f"<td>{html.escape(str(item.get('collection_status', '')))}</td>"
            f"<td>{html.escape(str(item.get('warning_checks', 0)))}</td>"
            f"<td>{html.escape(str(item.get('failed_checks', 0)))}</td>"
            f"<td>{html.escape(str(item.get('delta_items', 0)))}</td>"
            "</tr>"
        )
        for item in trends
    )
    if not trend_rows:
        trend_rows = "<tr><td colspan=\"6\">No historical trend data available yet.</td></tr>"

    delta_rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(path)}</td>"
            f"<td>{html.escape(str(value.get('previous')))}</td>"
            f"<td>{html.escape(str(value.get('current')))}</td>"
            f"<td>{html.escape(str(value.get('change')))}</td>"
            "</tr>"
        )
        for path, value in comparisons.items()
    )
    if not delta_rows:
        delta_rows = "<tr><td colspan=\"4\">No delta comparisons available.</td></tr>"

    def list_items(values: list[str]) -> str:
        if not values:
            return "<li>None</li>"
        return "\n".join(f"<li>{html.escape(str(value))}</li>" for value in values)

    backend_blob = html.escape(json.dumps(backend.get("metrics", {}), indent=2))
    frontend_blob = html.escape(json.dumps(frontend.get("metrics", {}), indent=2))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Nightfall Metrics Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f8fb;
      --panel: #ffffff;
      --text: #16202a;
      --muted: #5d6b7a;
      --accent: #0c7a6f;
      --warn: #b7791f;
      --fail: #b91c1c;
      --border: #d4dee8;
    }}
    body {{ margin: 0; background: linear-gradient(180deg, #edf5ff 0%, var(--bg) 40%, #f7fafc 100%); color: var(--text); font-family: "IBM Plex Sans", "Segoe UI", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    section {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 10px; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 13px; font-weight: 600; background: #d9efe9; color: #07534c; }}
    .warning {{ background: #fff1db; color: var(--warn); }}
    .critical {{ background: #ffe0e0; color: var(--fail); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--border); vertical-align: top; }}
    pre {{ background: #0f172a; color: #d8e7ff; border-radius: 8px; padding: 12px; overflow-x: auto; }}
    a {{ color: #1453a2; }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Nightfall Metrics Dashboard</h1>
      <p class=\"meta\">Run {html.escape(run_id)} generated at {html.escape(str(summary.get('generated_at')))}</p>
      <p>
        <span class=\"badge {'critical' if summary.get('severity') == 'critical' else ('warning' if summary.get('severity') == 'warning' else '')}\">Severity: {html.escape(str(summary.get('severity')))}</span>
      </p>
    </section>

    <section>
      <h2>Repository and Commit Context</h2>
      <p><strong>Branch:</strong> {html.escape(str(summary.get('source', {}).get('branch')))}</p>
      <p><strong>Commit:</strong> {html.escape(str(summary.get('source', {}).get('commit_sha')))}</p>
      <p><strong>Collection Status:</strong> {html.escape(str(summary.get('collection_status')))}</p>
      <p><strong>Manifest Exit State:</strong> {html.escape(str(manifest.get('execution', {}).get('exit_state')))}</p>
      <p>
        <a href=\"../artifacts/metrics/latest/manifest.json\">Manifest JSON</a> |
        <a href=\"../artifacts/metrics/latest/metrics.json\">Metrics JSON</a> |
        <a href=\"../artifacts/metrics/latest/summary.json\">Summary JSON</a>
      </p>
    </section>

    <section>
      <h2>Backend Metrics</h2>
      <p><strong>Status:</strong> {html.escape(str(backend.get('status')))}</p>
      <pre>{backend_blob}</pre>
    </section>

    <section>
      <h2>Frontend Metrics</h2>
      <p><strong>Status:</strong> {html.escape(str(frontend.get('status')))}</p>
      <pre>{frontend_blob}</pre>
    </section>

    <section>
      <h2>Coverage Summary</h2>
    <p><strong>Backend coverage status:</strong> {html.escape(str(backend.get('metrics', {}).get('coverage', {}).get('status', 'not_available')))}</p>
    <p><strong>Frontend coverage status:</strong> {html.escape(str(frontend.get('metrics', {}).get('test_coverage', {}).get('status', 'not_available')))}</p>
    </section>

    <section>
      <h2>Dependency Graph References</h2>
      <p>Dependency graph artifacts are represented inside the raw metrics payloads linked above.</p>
    </section>

    <section>
      <h2>Trend Delta</h2>
      <p><strong>Previous successful run:</strong> {html.escape(str(summary.get('previous_successful_run_id')))}</p>
      <table>
        <thead><tr><th>Metric Path</th><th>Previous</th><th>Current</th><th>Change</th></tr></thead>
        <tbody>{delta_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Warnings and Unavailable Metrics</h2>
      <h3>Warnings</h3>
      <ul>{list_items([str(v) for v in warning_list])}</ul>
      <h3>Failures</h3>
      <ul>{list_items([str(v) for v in failure_list])}</ul>
    </section>

    <section>
      <h2>Trend Snippets From History</h2>
      <table>
        <thead><tr><th>Run</th><th>Severity</th><th>Status</th><th>Warnings</th><th>Failures</th><th>Delta Items</th></tr></thead>
        <tbody>{trend_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


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


def run_dashboard_generation(repo_root: Path, run_id: str) -> dict[str, Any]:
    latest_root = repo_root / "artifacts" / "metrics" / "latest"
    manifest = _read_json(latest_root / "manifest.json")
    metrics = _read_json(latest_root / "metrics.json")
    summary = _read_json(latest_root / "summary.json")

    trends = _history_trend(repo_root=repo_root, current_run_id=run_id)

    dashboard_html = _render_html_dashboard(
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        summary=summary,
        trends=trends,
    )
    executive_md = _render_markdown_summary(run_id=run_id, summary=summary, trends=trends)

    dashboard_path = repo_root / "dashboard" / "index.html"
    report_path = repo_root / "reports" / "latest.md"
    staged_dashboard = repo_root / "metrics" / "output" / "dashboard" / run_id / "index.html"
    staged_report = repo_root / "metrics" / "output" / "reports" / run_id / "latest.md"

    _write_text(dashboard_path, dashboard_html)
    _write_text(report_path, executive_md)
    _write_text(staged_dashboard, dashboard_html)
    _write_text(staged_report, executive_md)

    return {
        "run_id": run_id,
        "generated_at": _as_utc_now(),
        "dashboard": str(dashboard_path.relative_to(repo_root)),
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
