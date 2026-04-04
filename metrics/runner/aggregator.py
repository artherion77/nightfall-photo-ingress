from __future__ import annotations

import argparse
import getpass
import importlib.metadata
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.module1_init import _git_branch, _git_head_sha, _git_version
from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


NUMERIC_DELTA_PATHS = [
    "modules.backend.metrics.loc.files",
    "modules.backend.metrics.loc.total_lines",
    "modules.backend.metrics.loc.total_code_lines",
    "modules.backend.metrics.coverage.coverage_percent",
    "modules.backend.metrics.coverage.covered_lines",
    "modules.backend.metrics.coverage.num_statements",
    "modules.backend.metrics.complexity.cyclomatic.mean",
    "modules.backend.metrics.complexity.cyclomatic.max",
    "modules.backend.metrics.complexity.maintainability_index.mean",
    "modules.frontend.metrics.loc.files",
    "modules.frontend.metrics.loc.total_lines",
    "modules.frontend.metrics.loc.total_code_lines",
    "modules.frontend.metrics.loc.js_ts_files",
    "modules.frontend.metrics.loc.svelte_files",
    "modules.frontend.metrics.cognitive_complexity.mean",
    "modules.frontend.metrics.cognitive_complexity.max",
    "modules.frontend.metrics.cognitive_complexity.count",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tool_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_nested_number(payload: dict[str, Any], path: str) -> float | int | None:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (int, float)):
        return current
    return None


def _collect_status_annotations(prefix: str, node: Any, warnings: list[str], failures: list[str]) -> None:
    if not isinstance(node, dict):
        return
    status = node.get("status")
    if status == "not_available":
        warnings.append(f"{prefix} not available")
    elif status == "failed":
        failures.append(f"{prefix} failed")
    for key, value in node.items():
        if isinstance(value, dict):
            _collect_status_annotations(f"{prefix}.{key}", value, warnings, failures)


def _find_previous_successful_run(repo_root: Path, current_run_id: str) -> tuple[str | None, dict[str, Any] | None]:
    history_root = repo_root / "artifacts" / "metrics" / "history"
    if not history_root.exists():
        return None, None

    candidates: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for run_dir in history_root.iterdir():
        if not run_dir.is_dir() or run_dir.name == current_run_id:
            continue
        manifest_path = run_dir / "manifest.json"
        metrics_path = run_dir / "metrics.json"
        if not manifest_path.exists() or not metrics_path.exists():
            continue
        try:
            manifest = _read_json(manifest_path)
            metrics = _read_json(metrics_path)
        except Exception:
            continue
        if manifest.get("execution", {}).get("exit_state") != "success":
            continue
        finished_at = str(manifest.get("execution", {}).get("finished_at", ""))
        candidates.append((finished_at, run_dir.name, manifest, metrics))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item[0])
    _, run_id, _, metrics = candidates[-1]
    return run_id, metrics


def _compute_delta(current_metrics: dict[str, Any], previous_metrics: dict[str, Any] | None, previous_run_id: str | None) -> dict[str, Any]:
    if previous_metrics is None:
        return {
            "previous_run_id": None,
            "comparisons": {},
        }

    comparisons: dict[str, dict[str, float | int | None]] = {}
    for path in NUMERIC_DELTA_PATHS:
        current = _get_nested_number(current_metrics, path)
        previous = _get_nested_number(previous_metrics, path)
        if current is None and previous is None:
            continue
        change: float | int | None
        if current is None or previous is None:
            change = None
        else:
            change = current - previous
        comparisons[path] = {
            "current": current,
            "previous": previous,
            "change": change,
        }

    return {
        "previous_run_id": previous_run_id,
        "comparisons": comparisons,
    }


def _summary_payload(
    run_id: str,
    commit_sha: str,
    branch: str,
    collection_status: str,
    warnings: list[str],
    failures: list[str],
    delta: dict[str, Any],
) -> dict[str, Any]:
    severity = "critical" if failures else ("warning" if warnings else "ok")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": collection_status,
        "severity": severity,
        "indicators": {
            "failed_checks": len(failures),
            "warning_checks": len(warnings),
            "delta_items": len(delta.get("comparisons", {})),
        },
        "previous_successful_run_id": delta.get("previous_run_id"),
        "warnings": warnings,
        "failures": failures,
    }


def _build_manifest(
    repo_root: Path,
    run_id: str,
    commit_sha: str,
    branch: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    collection_status: str,
    warnings: list[str],
    failures: list[str],
) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
    exit_state = "success" if collection_status in {"success", "partial", "initialized"} else "failed"
    return {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "repository_path": str(repo_root),
            "branch": branch,
            "commit_sha": commit_sha,
        },
        "trigger": {
            "mode": "bootstrap",
            "polled_at": started_at,
        },
        "execution": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": round(duration_seconds, 4),
            "hostname": socket.gethostname(),
            "executor_identity": getpass.getuser(),
            "exit_state": exit_state,
        },
        "tools": {
            "python": _tool_version("python") or "unknown",
            "git": _git_version(repo_root),
            "aggregator": "module4-v1",
        },
        "steps": [
            {
                "name": "module4_aggregate",
                "status": "success" if exit_state == "success" else "failed",
                "exit_code": 0 if exit_state == "success" else 1,
                "duration_seconds": round(duration_seconds, 4),
            }
        ],
        "artifacts": {
            "latest_manifest": "artifacts/metrics/latest/manifest.json",
            "latest_metrics": "artifacts/metrics/latest/metrics.json",
            "history_manifest": f"{history_base}/manifest.json",
            "history_metrics": f"{history_base}/metrics.json",
        },
        "publication": {
            "status": "not_published",
            "metrics_branch": "metrics",
            "dashboard_relative_path": "/dashboard/",
            "published_at": None,
        },
        "warnings": warnings,
        "failures": failures,
    }


def run_aggregation(repo_root: Path, run_id: str) -> dict[str, Any]:
    started = time.time()
    started_at = utc_now_iso()
    branch = _git_branch(repo_root)
    commit_sha = _git_head_sha(repo_root)

    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    if not latest_metrics_path.exists():
        raise FileNotFoundError("latest metrics.json missing; run collectors first")

    current_metrics = _read_json(latest_metrics_path)
    modules = dict(current_metrics.get("modules", {}))
    modules.setdefault("backend", {"status": "not_available", "metrics": {}})
    modules.setdefault("frontend", {"status": "not_available", "metrics": {}})

    statuses = {
        module.get("status")
        for module in modules.values()
        if isinstance(module, dict)
    }
    if "failed" in statuses:
        collection_status = "failed"
    elif "partial" in statuses or "not_available" in statuses:
        collection_status = "partial"
    else:
        collection_status = "success"

    warnings: list[str] = []
    failures: list[str] = []
    for name, module_payload in modules.items():
        if isinstance(module_payload, dict):
            _collect_status_annotations(f"modules.{name}", module_payload, warnings, failures)

    previous_run_id, previous_metrics = _find_previous_successful_run(repo_root, run_id)
    delta = _compute_delta(
        current_metrics={
            "modules": modules
        },
        previous_metrics=previous_metrics,
        previous_run_id=previous_run_id,
    )

    merged_metrics = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": collection_status,
        "modules": modules,
        "delta": delta,
    }

    summary = _summary_payload(
        run_id=run_id,
        commit_sha=commit_sha,
        branch=branch,
        collection_status=collection_status,
        warnings=warnings,
        failures=failures,
        delta=delta,
    )

    finished_at = utc_now_iso()
    duration = time.time() - started
    manifest = _build_manifest(
        repo_root=repo_root,
        run_id=run_id,
        commit_sha=commit_sha,
        branch=branch,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        collection_status=collection_status,
        warnings=warnings,
        failures=failures,
    )

    validate_metrics_payload(merged_metrics)
    validate_manifest_payload(manifest)

    history_dir = repo_root / "artifacts" / "metrics" / "history" / run_id
    history_dir.mkdir(parents=True, exist_ok=True)

    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "manifest.json", manifest)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "metrics.json", merged_metrics)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "summary.json", summary)
    _write_json(history_dir / "manifest.json", manifest)
    _write_json(history_dir / "metrics.json", merged_metrics)
    _write_json(history_dir / "summary.json", summary)
    _write_json(repo_root / "metrics" / "output" / "aggregator" / run_id / "summary.json", summary)

    return {
        "manifest": manifest,
        "metrics": merged_metrics,
        "summary": summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate backend/frontend metrics and compute deltas")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--run-id", default="module4-bootstrap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_aggregation(
        repo_root=Path(args.repo_root).resolve(),
        run_id=args.run_id,
    )


if __name__ == "__main__":
    main()
