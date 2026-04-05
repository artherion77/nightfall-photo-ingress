from __future__ import annotations

import argparse
import fcntl
import getpass
import hashlib
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


# ── Dashboard source fingerprint / drift-check ────────────────────────────────

def _compute_dashboard_source_fingerprint(repo_root: Path) -> str:
    """SHA-256 of all dashboard source files that affect the Vite/Rollup output.

    Deterministic: files are sorted by their repo-relative path before hashing,
    so directory-listing order doesn't affect the result.
    """
    dashboard_src = repo_root / "metrics" / "dashboard"
    hasher = hashlib.sha256()
    paths: list[Path] = []
    # Svelte/TS/JS/CSS source files
    for pattern in ("**/*.svelte", "**/*.ts", "**/*.js", "**/*.css"):
        paths.extend(dashboard_src.glob(pattern))
    # Config files that directly influence the build
    for name in ("svelte.config.js", "vite.config.js", "package.json", "package-lock.json"):
        candidate = dashboard_src / name
        if candidate.exists():
            paths.append(candidate)
    # Exclude node_modules and .svelte-kit from the fingerprint
    paths = [
        p for p in paths
        if "node_modules" not in p.parts and ".svelte-kit" not in p.parts and p.is_file()
    ]
    for path in sorted(set(paths), key=lambda p: str(p.relative_to(repo_root))):
        hasher.update(str(path.relative_to(repo_root)).encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


_BUILD_STAMP_FILE = ".build-stamp"


def _read_dashboard_build_stamp(repo_root: Path) -> dict[str, Any] | None:
    """Return the stored build stamp, or None if absent/corrupt."""
    stamp_path = repo_root / "dashboard" / _BUILD_STAMP_FILE
    if not stamp_path.exists():
        return None
    try:
        return json.loads(stamp_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_dashboard_build_stamp(repo_root: Path) -> str:
    """Compute and persist the source fingerprint alongside the built dashboard.

    Returns the fingerprint string so callers can log or validate it.
    """
    fingerprint = _compute_dashboard_source_fingerprint(repo_root)
    stamp: dict[str, Any] = {
        "source_fingerprint": fingerprint,
        "built_at": _utc_now_iso(),
    }
    stamp_path = repo_root / "dashboard" / _BUILD_STAMP_FILE
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return fingerprint


def _dashboard_needs_rebuild(repo_root: Path) -> bool:
    """True when the static dashboard is absent or stale w.r.t. source files.

    Decision logic:
    - Missing dashboard/index.html → definitely needs build.
    - Missing .build-stamp → dashboard existed before stamp tracking was added;
      assume it is fresh to avoid spurious rebuilds on first upgrade.
    - Stamp fingerprint mismatch → source changed since last build → rebuild.
    """
    dist_index = repo_root / "dashboard" / "index.html"
    if not dist_index.exists():
        return True
    stamp = _read_dashboard_build_stamp(repo_root)
    if stamp is None:
        # No stamp file: pre-existing build present; treat as fresh (safe default).
        return False
    current_fp = _compute_dashboard_source_fingerprint(repo_root)
    return stamp.get("source_fingerprint") != current_fp


def _require_prebuilt_dashboard(repo_root: Path) -> None:
    """Hard-fail if dashboard/index.html is absent (build prerequisite)."""
    dist_index = repo_root / "dashboard" / "index.html"
    if not dist_index.exists():
        raise RuntimeError(
            "publish aborted: dashboard/index.html not found. "
            "Build the static dashboard first: ./dev/bin/build-metrics-dashboard"
        )


# ── Post-collection output validation ─────────────────────────────────────────

def _validate_post_collection_outputs(repo_root: Path, run_id: str) -> None:
    """Raise explicitly when critical collector dependencies were unavailable.

    Prevents writing last_processed_commit when the pipeline ran without
    essential tools (radon, tree-sitter), which would produce zeroed metrics
    while appearing successful.  Called after aggregation, before dashboard gen.
    """
    metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    if not metrics_path.exists():
        raise RuntimeError(
            f"[MISSING_ARTIFACTS] aggregate metrics.json absent after collection "
            f"(run_id={run_id}); pipeline may not have run in the correct Python "
            "environment — ensure .venv is active and radon>=6.0.1 is installed"
        )
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"[CORRUPT_ARTIFACTS] metrics.json unreadable: {exc}") from exc

    modules = metrics.get("modules", {})
    backend = modules.get("backend", {}) if isinstance(modules, dict) else {}
    backend_metrics = backend.get("metrics", {}) if isinstance(backend, dict) else {}
    complexity = backend_metrics.get("complexity") if isinstance(backend_metrics, dict) else None
    if isinstance(complexity, dict) and complexity.get("status") == "not_available":
        reason = complexity.get("reason", "radon not importable")
        raise RuntimeError(
            f"[TOOL_UNAVAILABLE] Backend complexity tool unavailable: {reason}. "
            "Ensure .venv/bin/python has radon>=6.0.1 installed."
        )

    frontend = modules.get("frontend", {}) if isinstance(modules, dict) else {}
    frontend_metrics = frontend.get("metrics", {}) if isinstance(frontend, dict) else {}
    frontend_cognitive = (
        frontend_metrics.get("cognitive_complexity") if isinstance(frontend_metrics, dict) else None
    )
    if isinstance(frontend_cognitive, dict) and frontend_cognitive.get("status") == "not_available":
        reason = frontend_cognitive.get("reason", "tree-sitter not importable")
        raise RuntimeError(
            f"[TOOL_UNAVAILABLE] Frontend complexity tool unavailable: {reason}. "
            "Ensure .venv/bin/python has tree-sitter installed."
        )


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


def _validate_publish_payload(data_path: Path, expected_run_id: str, expected_commit: str) -> None:
    """Validate that __data.json matches the expected run before publishing."""
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    actual_run_id = payload.get("runId", "")
    actual_commit = payload.get("commitFull", "")
    errors = []
    if actual_run_id != expected_run_id:
        errors.append(f"runId mismatch: payload={actual_run_id!r} expected={expected_run_id!r}")
    if expected_commit and actual_commit != expected_commit:
        errors.append(f"commitSha mismatch: payload={actual_commit!r} expected={expected_commit!r}")
    if errors:
        raise RuntimeError(f"publish aborted: stale __data.json — {'; '.join(errors)}")


def _validate_publish_dashboard_static(dashboard_root: Path) -> None:
    """Validate static dashboard prerequisites before sync/commit."""
    index_path = dashboard_root / "index.html"
    if not index_path.exists():
        raise RuntimeError(f"publish aborted: dashboard static index missing at {index_path}")
    stamp_path = dashboard_root / _BUILD_STAMP_FILE
    if not stamp_path.exists():
        raise RuntimeError(
            f"publish aborted: dashboard build stamp missing at {stamp_path}; "
            "run ./dev/bin/build-metrics-dashboard to produce deterministic statics"
        )
    try:
        stamp_payload = json.loads(stamp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"publish aborted: unreadable dashboard build stamp: {exc}") from exc
    fingerprint = stamp_payload.get("source_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) < 16:
        raise RuntimeError("publish aborted: dashboard build stamp missing source_fingerprint")


def _build_static_dashboard(repo_root: Path) -> None:
    """Run the SvelteKit production build and write a source fingerprint stamp.

    The build stamp written here lets _dashboard_needs_rebuild() detect whether a
    subsequent publish can skip the build (source unchanged) or must trigger a
    new one.  Callers should prefer _dashboard_needs_rebuild() before calling
    this function.
    """
    build_script = repo_root / "dev" / "bin" / "build-metrics-dashboard"
    devctl_script = repo_root / "dev" / "bin" / "devctl"
    if not build_script.exists():
        raise RuntimeError(f"missing dashboard build script: {build_script}")

    result = subprocess.run(
        [str(build_script)],
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        _write_dashboard_build_stamp(repo_root)
        return

    if "is not running" in result.stderr and devctl_script.exists():
        subprocess.run(
            [str(devctl_script), "setup"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
        )
        retry = subprocess.run(
            [str(build_script)],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
        )
        if retry.returncode == 0:
            _write_dashboard_build_stamp(repo_root)
            return
        raise RuntimeError(retry.stderr.strip() or retry.stdout.strip() or "dashboard build failed after devctl setup")

    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "dashboard build failed")


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


def cleanup_runtime_artifacts(repo_root: Path, include_history: bool = False) -> dict[str, Any]:
    paths = _paths(repo_root)
    removed: list[str] = []

    def _remove(path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path.relative_to(repo_root)))

    # Ephemeral state files that should not be required for the next run.
    _remove(paths.last_processed_commit)
    _remove(paths.publication_json)
    _remove(paths.status_json)
    _remove(paths.lock_file)

    # Generated runtime artifacts.
    _remove(repo_root / "metrics" / "output")
    _remove(repo_root / "artifacts" / "metrics" / "latest")

    if include_history:
        _remove(repo_root / "artifacts" / "metrics" / "history")

    return {
        "status": "cleaned",
        "removed": sorted(removed),
        "include_history": bool(include_history),
        "updated_at": _utc_now_iso(),
    }


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

                # Ensure critical collector outputs exist and are usable before
                # generating dashboard artifacts or writing last_processed_commit.
                _validate_post_collection_outputs(repo_root=repo_root, run_id=run_id)

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

    # Regenerate dashboard payload for the latest successful run.
    run_dashboard_generation(repo_root=repo_root, run_id=run_id)

    worktree = _ensure_publication_worktree(repo_root, branch)
    current_source_fingerprint = _compute_dashboard_source_fingerprint(repo_root)
    published_stamp = _read_dashboard_build_stamp(worktree)
    published_fingerprint = None
    if isinstance(published_stamp, dict):
        value = published_stamp.get("source_fingerprint")
        if isinstance(value, str):
            published_fingerprint = value

    # Drift check compares source fingerprint against the published dashboard
    # version in the worktree, not against local hashed dist filenames.
    reused_published_dashboard = published_fingerprint == current_source_fingerprint

    if not reused_published_dashboard:
        if _dashboard_needs_rebuild(repo_root):
            _build_static_dashboard(repo_root)
        else:
            # Legacy dashboard build without stamp: preserve current output and
            # stamp it instead of rebuilding and churning hashed bundles.
            _require_prebuilt_dashboard(repo_root)
            _write_dashboard_build_stamp(repo_root)

        # Ensure the locally staged static build is publish-safe.
        _validate_publish_dashboard_static(repo_root / "dashboard")

    generated_dashboard_data = repo_root / "metrics" / "output" / "dashboard" / "latest" / "__data.json"
    generated_report = repo_root / "metrics" / "output" / "reports" / "latest.md"

    # Validate freshly generated payload before publishing
    if not generated_dashboard_data.exists():
        raise RuntimeError(f"publish aborted: generated __data.json not found at {generated_dashboard_data}")
    _validate_publish_payload(generated_dashboard_data, run_id, commit_sha)

    if not reused_published_dashboard:
        _copy_tree(repo_root / "dashboard", worktree / "dashboard")
    _copy_tree(generated_dashboard_data, worktree / "dashboard" / "__data.json")

    if generated_report.exists():
        _copy_tree(generated_report, worktree / "reports" / "latest.md")
    else:
        (worktree / "reports").mkdir(parents=True, exist_ok=True)

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
        "dashboard_sync_mode": "reuse_published" if reused_published_dashboard else "sync_local",
        "dashboard_source_fingerprint": current_source_fingerprint,
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
        choices=["install", "reconfigure", "start", "stop", "status", "run-now", "uninstall", "publish", "cleanup-runtime"],
    )
    parser.add_argument("--frequency-minutes", type=int, default=60)
    parser.add_argument("--max-history-runs", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--include-history", action="store_true")
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
    elif args.command == "cleanup-runtime":
        print(json.dumps(cleanup_runtime_artifacts(repo_root, include_history=args.include_history), indent=2))


if __name__ == "__main__":
    main()
