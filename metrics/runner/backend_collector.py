from __future__ import annotations

import argparse
import ast
import getpass
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.module1_init import _git_branch, _git_head_sha, _git_version
from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _iter_python_files(repo_root: Path, roots: list[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        start = repo_root / root
        if not start.exists():
            continue
        for file_path in start.rglob("*.py"):
            if file_path.is_file():
                files.append(file_path)
    return sorted(files)


def collect_loc(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    files = _iter_python_files(repo_root, roots)
    per_file: dict[str, dict[str, int]] = {}
    total_lines = 0
    total_code_lines = 0

    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_count = len(lines)
        code_count = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
        per_file[rel] = {
            "lines": line_count,
            "code_lines": code_count,
        }
        total_lines += line_count
        total_code_lines += code_count

    return {
        "status": "success",
        "roots": roots,
        "files": len(files),
        "total_lines": total_lines,
        "total_code_lines": total_code_lines,
        "per_file": per_file,
    }


def _detect_cycles(adj: dict[str, list[str]]) -> set[str]:
    """Return the set of node keys that participate in any cycle (DFS with gray-set tracking)."""
    in_cycle: set[str] = set()
    visited: set[str] = set()
    gray: set[str] = set()

    def _dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        gray.add(node)
        path.append(node)
        for neighbor in adj.get(node, []):
            if neighbor not in adj:
                continue
            if neighbor in gray:
                idx = path.index(neighbor)
                for cycle_node in path[idx:]:
                    in_cycle.add(cycle_node)
            elif neighbor not in visited:
                _dfs(neighbor, path)
        path.pop()
        gray.discard(node)

    for start_node in list(adj.keys()):
        if start_node not in visited:
            _dfs(start_node, [])
    return in_cycle


def collect_dependency_graph(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    all_files = _iter_python_files(repo_root, roots)
    nodes: list[str] = [str(f.relative_to(repo_root)) for f in all_files]

    def _path_to_module(p: str) -> str:
        mod = p.replace("/", ".").removesuffix(".py")
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        return mod

    module_to_path: dict[str, str] = {_path_to_module(p): p for p in nodes}

    edges: list[dict[str, str]] = []
    for file_path in all_files:
        rel = str(file_path.relative_to(repo_root))
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        for imported in sorted(imports):
            edges.append({"from": rel, "to": imported})

    fan_out: dict[str, int] = {n: 0 for n in nodes}
    fan_in: dict[str, int] = {n: 0 for n in nodes}
    local_adj: dict[str, list[str]] = {n: [] for n in nodes}
    for edge in edges:
        fan_out[edge["from"]] = fan_out.get(edge["from"], 0) + 1
        target_path = module_to_path.get(edge["to"])
        if target_path:
            fan_in[target_path] = fan_in.get(target_path, 0) + 1
            local_adj[edge["from"]].append(target_path)

    in_cycle = _detect_cycles(local_adj)

    node_details = sorted(
        [
            {
                "path": path,
                "fan_in": fan_in.get(path, 0),
                "fan_out": fan_out.get(path, 0),
                "kind": "local",
                "in_cycle": path in in_cycle,
            }
            for path in nodes
        ],
        key=lambda d: d["path"],
    )

    return {
        "status": "success",
        "nodes": sorted(nodes),
        "edges": edges,
        "node_details": node_details,
    }


def _tool_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _pytest_python(repo_root: Path) -> str:
    venv_python = repo_root / ".venv" / "bin" / "python"
    if os.name == "nt":
        venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def collect_complexity_and_maintainability(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    try:
        from radon.complexity import cc_visit  # type: ignore
        from radon.metrics import mi_visit  # type: ignore
    except Exception as exc:
        return {
            "status": "not_available",
            "reason": f"radon unavailable: {exc}",
        }

    files = _iter_python_files(repo_root, roots)
    complexity_values: list[float] = []
    mi_values: list[float] = []
    per_file: dict[str, dict[str, float]] = {}

    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        blocks = cc_visit(text)
        cc_scores = [float(block.complexity) for block in blocks]
        cc_avg = (sum(cc_scores) / len(cc_scores)) if cc_scores else 0.0
        mi = float(mi_visit(text, multi=True))

        complexity_values.extend(cc_scores)
        mi_values.append(mi)
        per_file[rel] = {
            "cyclomatic_avg": round(cc_avg, 4),
            "maintainability_index": round(mi, 4),
        }

    return {
        "status": "success",
        "radon_version": _tool_version("radon"),
        "cyclomatic": {
            "mean": round((sum(complexity_values) / len(complexity_values)), 4) if complexity_values else 0.0,
            "max": round(max(complexity_values), 4) if complexity_values else 0.0,
            "count": len(complexity_values),
        },
        "maintainability_index": {
            "mean": round((sum(mi_values) / len(mi_values)), 4) if mi_values else 0.0,
            "min": round(min(mi_values), 4) if mi_values else 0.0,
            "count": len(mi_values),
        },
        "per_file": per_file,
    }


def collect_pytest_coverage(repo_root: Path, pytest_target: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_json = output_dir / "coverage.json"
    log_path = output_dir / "pytest-coverage.log"

    cmd = [
        _pytest_python(repo_root),
        "-m",
        "pytest",
        pytest_target,
        "--cov=src",
        "--cov=api",
        f"--cov-report=json:{coverage_json}",
        "--maxfail=1",
    ]

    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    duration = time.time() - started
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")

    if not coverage_json.exists():
        reason = "coverage report not produced"
        if "unrecognized arguments: --cov" in (proc.stderr or ""):
            reason = "pytest-cov unavailable"
        return {
            "status": "not_available" if proc.returncode == 0 or "--cov" in (proc.stderr or "") else "failed",
            "reason": reason,
            "exit_code": proc.returncode,
            "duration_seconds": round(duration, 4),
            "pytest_log": str(log_path.relative_to(repo_root)),
        }

    coverage_payload = json.loads(coverage_json.read_text(encoding="utf-8"))
    totals = coverage_payload.get("totals", {})
    return {
        "status": "success" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 4),
        "coverage_percent": totals.get("percent_covered"),
        "covered_lines": totals.get("covered_lines"),
        "num_statements": totals.get("num_statements"),
        "missing_lines": totals.get("missing_lines"),
        "coverage_json": str(coverage_json.relative_to(repo_root)),
        "pytest_log": str(log_path.relative_to(repo_root)),
        "python_executable": _pytest_python(repo_root),
    }


def _build_manifest(
    repo_root: Path,
    run_id: str,
    branch: str,
    commit_sha: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    backend_status: str,
    warnings: list[str],
    failures: list[str],
) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
    exit_state = "success" if backend_status in {"success", "partial", "not_available"} else "failed"
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
            "pytest": _tool_version("pytest") or "unknown",
            "pytest_cov": _tool_version("pytest-cov") or "not_available",
            "radon": _tool_version("radon") or "not_available",
        },
        "steps": [
            {
                "name": "module2_backend_collect",
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


def _determine_collection_status(backend: dict[str, Any]) -> str:
    statuses = {
        backend.get("loc", {}).get("status"),
        backend.get("complexity", {}).get("status"),
        backend.get("dependency_graph", {}).get("status"),
        backend.get("coverage", {}).get("status"),
    }
    if "failed" in statuses:
        return "failed"
    if "not_available" in statuses:
        return "partial"
    return "success"


def run_backend_collection(repo_root: Path, run_id: str, pytest_target: str, skip_pytest: bool) -> dict[str, Any]:
    started = time.time()
    started_at = utc_now_iso()
    branch = _git_branch(repo_root)
    commit_sha = _git_head_sha(repo_root)

    roots = ["src", "api", "tests"]
    output_dir = repo_root / "metrics" / "output" / "backend" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    backend: dict[str, Any] = {
        "loc": collect_loc(repo_root, roots),
        "complexity": collect_complexity_and_maintainability(repo_root, roots),
        "dependency_graph": collect_dependency_graph(repo_root, roots),
    }

    if skip_pytest:
        backend["coverage"] = {
            "status": "not_available",
            "reason": "pytest execution skipped",
        }
    else:
        backend["coverage"] = collect_pytest_coverage(repo_root, pytest_target, output_dir)

    collection_status = _determine_collection_status(backend)
    warnings: list[str] = []
    failures: list[str] = []
    for key in ("complexity", "coverage"):
        status = backend.get(key, {}).get("status")
        if status == "not_available":
            warnings.append(f"backend.{key} not available")
        elif status == "failed":
            failures.append(f"backend.{key} failed")

    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    frontend = {
        "status": "not_available",
        "metrics": {},
    }
    if latest_metrics_path.exists():
        try:
            existing = json.loads(latest_metrics_path.read_text(encoding="utf-8"))
            frontend = existing.get("modules", {}).get("frontend", frontend)
        except Exception:
            frontend = {
                "status": "not_available",
                "metrics": {},
            }

    metrics_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": collection_status,
        "modules": {
            "backend": {
                "status": collection_status,
                "metrics": backend,
            },
            "frontend": frontend,
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
        backend_status=collection_status,
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
    _write_json(output_dir / "backend_metrics.json", backend)

    return {
        "manifest": manifest_payload,
        "metrics": metrics_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect backend metrics and host-side test coverage")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--run-id", default="module2-bootstrap")
    parser.add_argument("--pytest-target", default="tests/unit")
    parser.add_argument("--skip-pytest", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_backend_collection(
        repo_root=Path(args.repo_root).resolve(),
        run_id=args.run_id,
        pytest_target=args.pytest_target,
        skip_pytest=args.skip_pytest,
    )


if __name__ == "__main__":
    main()
