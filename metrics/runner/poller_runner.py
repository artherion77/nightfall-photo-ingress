from __future__ import annotations

import argparse
import fcntl
import getpass
import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.aggregator import run_aggregation
from metrics.runner.backend_collector import run_backend_collection
from metrics.runner.dashboard_generator import run_dashboard_generation
from metrics.runner.frontend_collector import run_frontend_collection
from metrics.runner.module8_ops import (
    append_event_log,
    apply_retention_policy,
    classify_failure,
    ensure_ops_state,
    run_optional_collectors,
)
from metrics.runner.module1_init import _git_branch, _git_head_sha, _git_version
from metrics.runner.schema_contract import validate_manifest_payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class RuntimePaths:
    runtime_json: Path
    last_processed_commit: Path
    lock_file: Path
    status_json: Path
    publication_json: Path
    publication_worktree: Path
    systemd_service: Path
    systemd_timer: Path


def _paths(repo_root: Path) -> RuntimePaths:
    state = repo_root / "metrics" / "state"
    systemd = repo_root / "metrics" / "systemd"
    return RuntimePaths(
        runtime_json=state / "runtime.json",
        last_processed_commit=state / "last_processed_commit",
        lock_file=state / "poller.lock",
        status_json=state / "poller_status.json",
        publication_json=state / "last_publication.json",
        publication_worktree=repo_root / "metrics" / "output" / "publication" / "metrics-branch-worktree",
        systemd_service=systemd / "nightfall-metrics-poller.service",
        systemd_timer=systemd / "nightfall-metrics-poller.timer",
    )


def _runtime_defaults() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "frequency_minutes": 60,
        "metrics_branch": "metrics",
        "dashboard_relative_path": "/dashboard/",
        "max_history_runs": 120,
        "installed": False,
        "enabled": False,
        "retry_max_retries": 1,
        "timeout_seconds": 1800,
        "configured_at": _utc_now_iso(),
    }


def _load_runtime_config(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    payload = _read_json(paths.runtime_json, fallback=_runtime_defaults())
    if not payload:
        payload = _runtime_defaults()
    # Merge forward-compatible defaults without removing existing keys.
    defaults = _runtime_defaults()
    for key, value in defaults.items():
        payload.setdefault(key, value)
    return payload


def _save_runtime_config(repo_root: Path, payload: dict[str, Any]) -> None:
    _write_json(_paths(repo_root).runtime_json, payload)


def _service_unit_content(repo_root: Path) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Nightfall Metrics Poller (oneshot)",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={repo_root}",
            f"ExecStart={repo_root}/metricsctl run-now",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def _timer_unit_content(frequency_minutes: int) -> str:
    return "\n".join(
        [
            "[Unit]",
            "Description=Nightfall Metrics Poller Timer",
            "",
            "[Timer]",
            f"OnUnitActiveSec={int(frequency_minutes)}m",
            "Persistent=true",
            "Unit=nightfall-metrics-poller.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )


def install_poller(repo_root: Path, frequency_minutes: int = 60, max_history_runs: int = 120) -> dict[str, Any]:
    if frequency_minutes <= 0:
        raise ValueError("frequency_minutes must be > 0")
    if max_history_runs <= 0:
        raise ValueError("max_history_runs must be > 0")
    paths = _paths(repo_root)
    config = _load_runtime_config(repo_root)
    config.update(
        {
            "frequency_minutes": int(frequency_minutes),
            "max_history_runs": int(max_history_runs),
            "installed": True,
            "enabled": True,
            "configured_at": _utc_now_iso(),
        }
    )
    _save_runtime_config(repo_root, config)
    paths.systemd_service.parent.mkdir(parents=True, exist_ok=True)
    paths.systemd_service.write_text(_service_unit_content(repo_root), encoding="utf-8")
    paths.systemd_timer.write_text(_timer_unit_content(int(frequency_minutes)), encoding="utf-8")
    return config


def reconfigure_poller(repo_root: Path, frequency_minutes: int, max_history_runs: int = 120) -> dict[str, Any]:
    return install_poller(repo_root=repo_root, frequency_minutes=frequency_minutes, max_history_runs=max_history_runs)


def start_poller(repo_root: Path) -> dict[str, Any]:
    config = _load_runtime_config(repo_root)
    config["enabled"] = True
    config["installed"] = bool(config.get("installed", False))
    config["configured_at"] = _utc_now_iso()
    _save_runtime_config(repo_root, config)
    return config


def stop_poller(repo_root: Path) -> dict[str, Any]:
    config = _load_runtime_config(repo_root)
    config["enabled"] = False
    config["configured_at"] = _utc_now_iso()
    _save_runtime_config(repo_root, config)
    return config


def uninstall_poller(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    config = _load_runtime_config(repo_root)
    config["installed"] = False
    config["enabled"] = False
    config["configured_at"] = _utc_now_iso()
    _save_runtime_config(repo_root, config)
    if paths.systemd_service.exists():
        paths.systemd_service.unlink()
    if paths.systemd_timer.exists():
        paths.systemd_timer.unlink()
    return config


def _is_locked(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False


def _write_failure_manifest(
    repo_root: Path,
    run_id: str,
    commit_sha: str,
    branch: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    failure_message: str,
) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "repository_path": str(repo_root),
            "branch": branch,
            "commit_sha": commit_sha,
        },
        "trigger": {
            "mode": "poller",
            "polled_at": started_at,
        },
        "execution": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": round(duration_seconds, 4),
            "hostname": socket.gethostname(),
            "executor_identity": getpass.getuser(),
            "exit_state": "failed",
        },
        "tools": {
            "python": "unknown",
            "git": _git_version(repo_root),
            "poller": "module6-v1",
        },
        "steps": [
            {
                "name": "module6_run_now",
                "status": "failed",
                "exit_code": 1,
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
        "warnings": [],
        "failures": [failure_message],
    }
    validate_manifest_payload(manifest)
    history_dir = repo_root / "artifacts" / "metrics" / "history" / run_id
    history_dir.mkdir(parents=True, exist_ok=True)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "manifest.json", manifest)
    _write_json(history_dir / "manifest.json", manifest)
    return manifest


def _write_status(repo_root: Path, payload: dict[str, Any]) -> None:
    _write_json(_paths(repo_root).status_json, payload)


def _enforce_timeout(deadline: float, step_name: str) -> None:
    if time.time() > deadline:
        raise TimeoutError(f"poller timeout exceeded before step: {step_name}")


def _run_git(repo_root: Path, args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd or repo_root),
        check=check,
        capture_output=True,
        text=True,
    )


def _branch_exists(repo_root: Path, branch: str) -> bool:
    result = _run_git(repo_root, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False)
    return result.returncode == 0


def _ensure_publication_worktree(repo_root: Path, branch: str) -> Path:
    paths = _paths(repo_root)
    worktree = paths.publication_worktree
    worktree.parent.mkdir(parents=True, exist_ok=True)

    if (worktree / ".git").exists():
        _run_git(repo_root, ["-C", str(worktree), "checkout", branch], check=False)
        return worktree

    if worktree.exists():
        shutil.rmtree(worktree)

    if _branch_exists(repo_root, branch):
        _run_git(repo_root, ["worktree", "add", "--force", str(worktree), branch])
    else:
        _run_git(repo_root, ["worktree", "add", "--force", "-b", branch, str(worktree)])
    return worktree


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _commit_if_needed(repo_root: Path, worktree: Path, message: str) -> tuple[bool, str | None]:
    _run_git(
        repo_root,
        [
            "-C",
            str(worktree),
            "add",
            "dashboard",
            "reports",
            "artifacts/metrics/latest",
            "artifacts/metrics/history",
            ".github/workflows/static.yml",
        ],
    )
    status = _run_git(repo_root, ["-C", str(worktree), "status", "--porcelain"], check=False)
    if not status.stdout.strip():
        return False, None
    _run_git(repo_root, ["-C", str(worktree), "commit", "-m", message])
    commit = _run_git(repo_root, ["-C", str(worktree), "rev-parse", "HEAD"])
    return True, commit.stdout.strip()


def _push_publication_branch(repo_root: Path, worktree: Path, branch: str) -> tuple[bool, str | None]:
    push = _run_git(repo_root, ["-C", str(worktree), "push", "origin", branch], check=False)
    if push.returncode == 0:
        return True, None
    detail = (push.stderr or push.stdout or "git push failed").strip()
    return False, detail


def run_now(repo_root: Path, max_retries: int = 1, timeout_seconds: int = 1800) -> dict[str, Any]:
    paths = _paths(repo_root)
    config = _load_runtime_config(repo_root)
    ensure_ops_state(repo_root)
    commit_sha = _git_head_sha(repo_root)
    branch = _git_branch(repo_root)
    last_processed = _read_text(paths.last_processed_commit)

    if commit_sha == last_processed:
        status = {
            "status": "skipped_unchanged",
            "run_id": None,
            "head_commit": commit_sha,
            "last_processed_commit": last_processed,
            "branch": branch,
            "updated_at": _utc_now_iso(),
        }
        _write_status(repo_root, status)
        append_event_log(
            repo_root,
            {
                "event": "run_now",
                "timestamp": _utc_now_iso(),
                "status": "skipped_unchanged",
                "branch": branch,
                "commit_sha": commit_sha,
                "run_id": None,
            },
        )
        return status

    paths.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with paths.lock_file.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            status = {
                "status": "concurrent_run",
                "run_id": None,
                "head_commit": commit_sha,
                "last_processed_commit": last_processed,
                "branch": branch,
                "updated_at": _utc_now_iso(),
            }
            _write_status(repo_root, status)
            append_event_log(
                repo_root,
                {
                    "event": "run_now",
                    "timestamp": _utc_now_iso(),
                    "status": "concurrent_run",
                    "branch": branch,
                    "commit_sha": commit_sha,
                    "run_id": None,
                },
            )
            return status

        attempts = int(max_retries) + 1
        for attempt in range(1, attempts + 1):
            run_id = f"module6-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{attempt}"
            started = time.time()
            started_at = _utc_now_iso()
            deadline = started + int(timeout_seconds)
            try:
                _write_status(
                    repo_root,
                    {
                        "status": "running",
                        "run_id": run_id,
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "head_commit": commit_sha,
                        "branch": branch,
                        "updated_at": _utc_now_iso(),
                    },
                )
                _enforce_timeout(deadline, "collect_backend")
                run_backend_collection(repo_root=repo_root, run_id=run_id, pytest_target="tests/unit", skip_pytest=False)

                _enforce_timeout(deadline, "collect_frontend")
                run_frontend_collection(repo_root=repo_root, run_id=run_id)

                _enforce_timeout(deadline, "collect_optional")
                run_optional_collectors(repo_root=repo_root, run_id=run_id)

                _enforce_timeout(deadline, "aggregate")
                run_aggregation(repo_root=repo_root, run_id=run_id)

                _enforce_timeout(deadline, "generate_dashboard")
                run_dashboard_generation(repo_root=repo_root, run_id=run_id)

                retention_result = apply_retention_policy(
                    repo_root=repo_root,
                    max_history_runs=int(config.get("max_history_runs", 120)),
                )

                paths.last_processed_commit.write_text(commit_sha, encoding="utf-8")
                result = {
                    "status": "success",
                    "run_id": run_id,
                    "attempt": attempt,
                    "head_commit": commit_sha,
                    "last_processed_commit": commit_sha,
                    "branch": branch,
                    "frequency_minutes": config.get("frequency_minutes", 60),
                    "retention": retention_result,
                    "updated_at": _utc_now_iso(),
                }
                _write_status(repo_root, result)
                append_event_log(
                    repo_root,
                    {
                        "event": "run_now",
                        "timestamp": _utc_now_iso(),
                        "status": "success",
                        "branch": branch,
                        "commit_sha": commit_sha,
                        "run_id": run_id,
                    },
                )
                return result
            except Exception as exc:
                finished_at = _utc_now_iso()
                duration = time.time() - started
                classification = classify_failure(repo_root=repo_root, error_message=str(exc))
                _write_failure_manifest(
                    repo_root=repo_root,
                    run_id=run_id,
                    commit_sha=commit_sha,
                    branch=branch,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_seconds=duration,
                    failure_message=f"[{classification['code']}] {exc}",
                )
                if attempt >= attempts:
                    result = {
                        "status": "failed",
                        "run_id": run_id,
                        "attempt": attempt,
                        "head_commit": commit_sha,
                        "last_processed_commit": last_processed,
                        "branch": branch,
                        "error": str(exc),
                        "failure_code": classification["code"],
                        "updated_at": _utc_now_iso(),
                    }
                    _write_status(repo_root, result)
                    append_event_log(
                        repo_root,
                        {
                            "event": "run_now",
                            "timestamp": _utc_now_iso(),
                            "status": "failed",
                            "branch": branch,
                            "commit_sha": commit_sha,
                            "run_id": run_id,
                            "failure_code": classification["code"],
                            "message": str(exc),
                        },
                    )
                    return result
        return {
            "status": "failed",
            "run_id": None,
            "head_commit": commit_sha,
            "last_processed_commit": last_processed,
            "branch": branch,
            "updated_at": _utc_now_iso(),
        }


def publish_metrics(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    runtime = _load_runtime_config(repo_root)
    ensure_ops_state(repo_root)
    branch = str(runtime.get("metrics_branch", "metrics"))

    latest_manifest_path = repo_root / "artifacts" / "metrics" / "latest" / "manifest.json"
    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    latest_summary_path = repo_root / "artifacts" / "metrics" / "latest" / "summary.json"

    if not latest_manifest_path.exists() or not latest_metrics_path.exists() or not latest_summary_path.exists():
        payload = {
            "status": "skipped_missing_artifacts",
            "published_at": _utc_now_iso(),
            "metrics_branch": branch,
        }
        _write_json(paths.publication_json, payload)
        append_event_log(repo_root, {"event": "publish", "timestamp": _utc_now_iso(), "status": payload["status"]})
        return payload

    manifest = _read_json(latest_manifest_path)
    run_id = str(manifest.get("run_id", "unknown"))
    exit_state = str(manifest.get("execution", {}).get("exit_state", "unknown"))
    if exit_state != "success":
        payload = {
            "status": "skipped_last_run_not_successful",
            "published_at": _utc_now_iso(),
            "metrics_branch": branch,
            "run_id": run_id,
            "last_exit_state": exit_state,
        }
        _write_json(paths.publication_json, payload)
        append_event_log(repo_root, {"event": "publish", "timestamp": _utc_now_iso(), "status": payload["status"], "run_id": run_id})
        return payload

    commit_sha = str(manifest.get("source", {}).get("commit_sha", ""))
    history_run_dir = repo_root / "artifacts" / "metrics" / "history" / run_id
    if not history_run_dir.exists():
        payload = {
            "status": "skipped_missing_history_run",
            "published_at": _utc_now_iso(),
            "metrics_branch": branch,
            "run_id": run_id,
        }
        _write_json(paths.publication_json, payload)
        append_event_log(repo_root, {"event": "publish", "timestamp": _utc_now_iso(), "status": payload["status"], "run_id": run_id})
        return payload

    # Rebuild static dashboard from latest artifacts before publication sync.
    run_dashboard_generation(repo_root=repo_root, run_id=run_id)

    worktree = _ensure_publication_worktree(repo_root, branch)
    _copy_tree(repo_root / "dashboard", worktree / "dashboard")
    _copy_tree(repo_root / "reports", worktree / "reports")
    _copy_tree(repo_root / "artifacts" / "metrics" / "latest", worktree / "artifacts" / "metrics" / "latest")
    _copy_tree(history_run_dir, worktree / "artifacts" / "metrics" / "history" / run_id)
    # Keep the Pages workflow present on the publication branch so metrics pushes can deploy.
    _copy_tree(repo_root / ".github" / "workflows" / "static.yml", worktree / ".github" / "workflows" / "static.yml")

    commit_message = f"metrics publish: {run_id} {commit_sha[:12]}"
    committed, publication_commit = _commit_if_needed(repo_root, worktree, commit_message)
    pushed = False
    push_error: str | None = None
    if committed:
        pushed, push_error = _push_publication_branch(repo_root, worktree, branch)

    payload = {
        "status": "published" if (committed and pushed) else ("published_commit_only" if committed else "no_changes"),
        "published_at": _utc_now_iso(),
        "metrics_branch": branch,
        "run_id": run_id,
        "source_commit": commit_sha,
        "publication_commit": publication_commit,
        "push_performed": committed,
        "push_succeeded": pushed,
        "push_error": push_error,
        "dashboard_url_path": str(runtime.get("dashboard_relative_path", "/dashboard/")),
        "worktree_path": str(worktree.relative_to(repo_root)),
    }
    _write_json(paths.publication_json, payload)
    append_event_log(
        repo_root,
        {
            "event": "publish",
            "timestamp": _utc_now_iso(),
            "status": payload["status"],
            "run_id": run_id,
            "commit_sha": commit_sha,
        },
    )
    return payload


def poller_status(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    runtime = _load_runtime_config(repo_root)
    ops_paths = ensure_ops_state(repo_root)
    last_processed = _read_text(paths.last_processed_commit)
    latest_manifest = repo_root / "artifacts" / "metrics" / "latest" / "manifest.json"
    latest_summary = repo_root / "artifacts" / "metrics" / "latest" / "summary.json"
    run_state = _read_json(paths.status_json, fallback={})
    publication = _read_json(paths.publication_json, fallback={})

    last_successful_run_id = None
    if latest_summary.exists():
        try:
            last_successful_run_id = _read_json(latest_summary).get("run_id")
        except Exception:
            last_successful_run_id = None

    return {
        "installed": bool(runtime.get("installed", False)),
        "enabled": bool(runtime.get("enabled", False)),
        "frequency_minutes": int(runtime.get("frequency_minutes", 60)),
        "lock_active": _is_locked(paths.lock_file),
        "last_processed_commit": last_processed,
        "last_successful_run_id": last_successful_run_id,
        "latest_manifest_path": str(latest_manifest.relative_to(repo_root)),
        "latest_summary_path": str(latest_summary.relative_to(repo_root)),
        "last_publication_result": publication,
        "ops": ops_paths,
        "runtime": run_state,
        "updated_at": _utc_now_iso(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Module 6 metrics poller operations")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument(
        "command",
        choices=["install", "reconfigure", "start", "stop", "status", "run-now", "uninstall", "publish"],
    )
    parser.add_argument("--frequency-minutes", type=int, default=60)
    parser.add_argument("--max-history-runs", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.command == "install":
        print(json.dumps(install_poller(repo_root, args.frequency_minutes, args.max_history_runs), indent=2))
    elif args.command == "reconfigure":
        print(json.dumps(reconfigure_poller(repo_root, args.frequency_minutes, args.max_history_runs), indent=2))
    elif args.command == "start":
        print(json.dumps(start_poller(repo_root), indent=2))
    elif args.command == "stop":
        print(json.dumps(stop_poller(repo_root), indent=2))
    elif args.command == "status":
        print(json.dumps(poller_status(repo_root), indent=2))
    elif args.command == "run-now":
        print(json.dumps(run_now(repo_root, max_retries=args.max_retries, timeout_seconds=args.timeout_seconds), indent=2))
    elif args.command == "uninstall":
        print(json.dumps(uninstall_poller(repo_root), indent=2))
    elif args.command == "publish":
        print(json.dumps(publish_metrics(repo_root), indent=2))


if __name__ == "__main__":
    main()
