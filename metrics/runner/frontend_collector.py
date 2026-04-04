from __future__ import annotations

import argparse
import getpass
import importlib.metadata
import json
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.module1_init import _git_branch, _git_head_sha, _git_version
from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


IMPORT_RE = re.compile(
    r"(?:import\s+(?:.+?)\s+from\s+|import\(\s*|require\(\s*)(['\"])(?P<module>[^'\"]+)\1"
)
COGNITIVE_TOKENS = ("if", "for", "while", "switch", "case", "catch", "&&", "||", "?", "=>")


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


def _iter_frontend_files(repo_root: Path, roots: list[str]) -> list[Path]:
    files: list[Path] = []
    suffixes = {".js", ".ts", ".svelte", ".jsx", ".tsx"}
    for root in roots:
        start = repo_root / root
        if not start.exists():
            continue
        for file_path in start.rglob("*"):
            if file_path.is_file() and file_path.suffix in suffixes:
                files.append(file_path)
    return sorted(files)


def collect_loc(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    files = _iter_frontend_files(repo_root, roots)
    totals = {
        "files": 0,
        "total_lines": 0,
        "total_code_lines": 0,
        "js_ts_files": 0,
        "svelte_files": 0,
    }
    per_file: dict[str, dict[str, int | str]] = {}

    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("//"))

        file_type = "svelte" if file_path.suffix == ".svelte" else "js_ts"
        if file_type == "svelte":
            totals["svelte_files"] += 1
        else:
            totals["js_ts_files"] += 1

        totals["files"] += 1
        totals["total_lines"] += total_lines
        totals["total_code_lines"] += code_lines
        per_file[rel] = {
            "type": file_type,
            "lines": total_lines,
            "code_lines": code_lines,
        }

    return {
        "status": "success",
        "roots": roots,
        **totals,
        "per_file": per_file,
    }


def _estimate_cognitive_complexity(text: str) -> int:
    complexity = 0
    nesting = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        close_braces = stripped.count("}")
        nesting = max(0, nesting - close_braces)

        token_hits = sum(stripped.count(token) for token in COGNITIVE_TOKENS)
        if token_hits:
            complexity += token_hits * (1 + nesting)

        open_braces = stripped.count("{")
        nesting += open_braces
    return complexity


def collect_cognitive_complexity(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    files = _iter_frontend_files(repo_root, roots)
    per_file: dict[str, int] = {}
    values: list[int] = []
    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        score = _estimate_cognitive_complexity(text)
        per_file[rel] = score
        values.append(score)

    return {
        "status": "success",
        "count": len(values),
        "mean": round((sum(values) / len(values)), 4) if values else 0.0,
        "max": max(values) if values else 0,
        "per_file": per_file,
    }


def collect_dependency_graph(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    files = _iter_frontend_files(repo_root, roots)
    nodes: list[str] = []
    edges: list[dict[str, str]] = []
    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        nodes.append(rel)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        modules = {match.group("module") for match in IMPORT_RE.finditer(text)}
        for module in sorted(modules):
            edges.append({"from": rel, "to": module})
    return {
        "status": "success",
        "nodes": sorted(nodes),
        "edges": edges,
    }


def frontend_test_coverage_status(reason: str = "deferred_until_vitest_playwright_maturity") -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": reason,
    }


def _determine_collection_status(frontend: dict[str, Any]) -> str:
    statuses = {
        frontend.get("loc", {}).get("status"),
        frontend.get("cognitive_complexity", {}).get("status"),
        frontend.get("dependency_graph", {}).get("status"),
        frontend.get("test_coverage", {}).get("status"),
    }
    if "failed" in statuses:
        return "failed"
    if "not_available" in statuses:
        return "partial"
    return "success"


def _build_manifest(
    repo_root: Path,
    run_id: str,
    branch: str,
    commit_sha: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    frontend_status: str,
    warnings: list[str],
    failures: list[str],
) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
    exit_state = "success" if frontend_status in {"success", "partial", "not_available"} else "failed"
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
            "python": sys.version.split()[0],
            "git": _git_version(repo_root),
            "eslint": _tool_version("eslint") or "not_available",
        },
        "steps": [
            {
                "name": "module3_frontend_collect",
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


def run_frontend_collection(repo_root: Path, run_id: str) -> dict[str, Any]:
    started = time.time()
    started_at = utc_now_iso()
    branch = _git_branch(repo_root)
    commit_sha = _git_head_sha(repo_root)

    roots = ["webui/src", "webui/tests"]
    frontend_output_dir = repo_root / "metrics" / "output" / "frontend" / run_id
    frontend_output_dir.mkdir(parents=True, exist_ok=True)

    frontend_metrics = {
        "loc": collect_loc(repo_root, roots),
        "cognitive_complexity": collect_cognitive_complexity(repo_root, roots),
        "dependency_graph": collect_dependency_graph(repo_root, roots),
        "test_coverage": frontend_test_coverage_status(),
    }
    frontend_status = _determine_collection_status(frontend_metrics)

    warnings: list[str] = []
    failures: list[str] = []
    for key in ("cognitive_complexity", "dependency_graph", "test_coverage"):
        status = frontend_metrics.get(key, {}).get("status")
        if status == "not_available":
            warnings.append(f"frontend.{key} not available")
        elif status == "failed":
            failures.append(f"frontend.{key} failed")

    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    backend = {
        "status": "not_available",
        "metrics": {},
    }
    if latest_metrics_path.exists():
        try:
            existing = json.loads(latest_metrics_path.read_text(encoding="utf-8"))
            backend = existing.get("modules", {}).get("backend", backend)
        except Exception:
            backend = {
                "status": "not_available",
                "metrics": {},
            }

    module_statuses = {backend.get("status"), frontend_status}
    if "failed" in module_statuses:
        collection_status = "failed"
    elif "partial" in module_statuses or "not_available" in module_statuses:
        collection_status = "partial"
    else:
        collection_status = "success"

    metrics_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": collection_status,
        "modules": {
            "backend": backend,
            "frontend": {
                "status": frontend_status,
                "metrics": frontend_metrics,
            },
        },
        "delta": {},
    }

    finished_at = utc_now_iso()
    duration = time.time() - started
    manifest_payload = _build_manifest(
        repo_root=repo_root,
        run_id=run_id,
        branch=branch,
        commit_sha=commit_sha,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        frontend_status=frontend_status,
        warnings=warnings,
        failures=failures,
    )

    validate_metrics_payload(metrics_payload)
    validate_manifest_payload(manifest_payload)

    history_dir = repo_root / "artifacts" / "metrics" / "history" / run_id
    history_dir.mkdir(parents=True, exist_ok=True)

    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "metrics.json", metrics_payload)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "manifest.json", manifest_payload)
    _write_json(history_dir / "metrics.json", metrics_payload)
    _write_json(history_dir / "manifest.json", manifest_payload)
    _write_json(frontend_output_dir / "frontend_metrics.json", frontend_metrics)

    return {
        "manifest": manifest_payload,
        "metrics": metrics_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect frontend metrics (LOC/complexity/dependency graph)")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--run-id", default="module3-bootstrap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_frontend_collection(
        repo_root=Path(args.repo_root).resolve(),
        run_id=args.run_id,
    )


if __name__ == "__main__":
    main()
