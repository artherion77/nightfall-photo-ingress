from __future__ import annotations

import argparse
import getpass
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "0" * 40
    return result.stdout.strip()


def _git_branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip()


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_manifest(repo_root: Path, run_id: str, commit_sha: str, branch: str, now: str) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
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
            "polled_at": now,
        },
        "execution": {
            "started_at": now,
            "finished_at": now,
            "duration_seconds": 0.0,
            "hostname": socket.gethostname(),
            "executor_identity": getpass.getuser(),
            "exit_state": "initialized",
        },
        "tools": {
            "python": sys.version.split()[0],
            "git": _git_version(repo_root),
        },
        "steps": [
            {
                "name": "module1_init",
                "status": "success",
                "exit_code": 0,
                "duration_seconds": 0.0,
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
        "warnings": [],
        "failures": [],
    }


def _git_version(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "--version"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def build_metrics(run_id: str, commit_sha: str, branch: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": "initialized",
        "modules": {
            "backend": {
                "status": "not_available",
                "metrics": {},
            },
            "frontend": {
                "status": "not_available",
                "metrics": {},
            },
        },
        "delta": {},
    }


def initialize_module1(repo_root: Path, run_id: str) -> None:
    now = utc_now_iso()
    commit_sha = _git_head_sha(repo_root)
    branch = _git_branch(repo_root)

    _mkdir(repo_root / "metrics" / "runner")
    _mkdir(repo_root / "metrics" / "systemd")
    _mkdir(repo_root / "metrics" / "state")
    _mkdir(repo_root / "metrics" / "output")
    _mkdir(repo_root / "artifacts" / "metrics" / "latest")
    _mkdir(repo_root / "artifacts" / "metrics" / "history" / run_id)

    runtime_payload = {
        "schema_version": 1,
        "frequency_minutes": 60,
        "metrics_branch": "metrics",
        "dashboard_relative_path": "/dashboard/",
        "configured_at": now,
    }
    _write_json(repo_root / "metrics" / "state" / "runtime.json", runtime_payload)

    last_processed_commit_file = repo_root / "metrics" / "state" / "last_processed_commit"
    if not last_processed_commit_file.exists():
        last_processed_commit_file.write_text("", encoding="utf-8")

    manifest = build_manifest(repo_root, run_id, commit_sha, branch, now)
    metrics = build_metrics(run_id, commit_sha, branch)

    validate_manifest_payload(manifest)
    validate_metrics_payload(metrics)

    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "manifest.json", manifest)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "metrics.json", metrics)
    _write_json(repo_root / "artifacts" / "metrics" / "history" / run_id / "manifest.json", manifest)
    _write_json(repo_root / "artifacts" / "metrics" / "history" / run_id / "metrics.json", metrics)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Module 1 metrics schema/layout artifacts")
    parser.add_argument("--run-id", default="module1-bootstrap")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize_module1(Path(args.repo_root).resolve(), args.run_id)


if __name__ == "__main__":
    main()
