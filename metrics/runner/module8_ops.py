from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {} if fallback is None else fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _state_path(repo_root: Path, name: str) -> Path:
    return repo_root / "metrics" / "state" / name


def default_failure_taxonomy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "rules": [
            {"match": "timeout", "code": "timeout", "severity": "high"},
            {"match": "lock", "code": "concurrency", "severity": "medium"},
            {"match": "coverage", "code": "collector_coverage", "severity": "medium"},
            {"match": "pytest", "code": "collector_test", "severity": "medium"},
            {"match": "git", "code": "publication_git", "severity": "high"},
        ],
        "default": {"code": "unknown", "severity": "medium"},
        "updated_at": _utc_now_iso(),
    }


def default_log_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_log_path": "metrics/output/logs/metrics-events.ndjson",
        "retain_message_chars": 600,
        "include_fields": [
            "event",
            "timestamp",
            "run_id",
            "status",
            "failure_code",
            "branch",
            "commit_sha",
        ],
        "updated_at": _utc_now_iso(),
    }


def default_extensions_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "collectors": [
            {
                "name": "bundle_size",
                "enabled": False,
                "optional": True,
            },
            {
                "name": "openapi_complexity",
                "enabled": False,
                "optional": True,
            },
            {
                "name": "api_surface_diff",
                "enabled": False,
                "optional": True,
            },
            {
                "name": "vitest_coverage",
                "enabled": False,
                "optional": True,
            },
            {
                "name": "playwright_coverage",
                "enabled": False,
                "optional": True,
            },
        ],
        "updated_at": _utc_now_iso(),
    }


def ensure_ops_state(repo_root: Path) -> dict[str, Any]:
    failure_taxonomy = _state_path(repo_root, "failure_taxonomy.json")
    log_policy = _state_path(repo_root, "log_policy.json")
    extensions = _state_path(repo_root, "extensions.json")

    if not failure_taxonomy.exists():
        _write_json(failure_taxonomy, default_failure_taxonomy())
    if not log_policy.exists():
        _write_json(log_policy, default_log_policy())
    if not extensions.exists():
        _write_json(extensions, default_extensions_config())

    return {
        "failure_taxonomy_path": str(failure_taxonomy.relative_to(repo_root)),
        "log_policy_path": str(log_policy.relative_to(repo_root)),
        "extensions_path": str(extensions.relative_to(repo_root)),
    }


def classify_failure(repo_root: Path, error_message: str) -> dict[str, Any]:
    taxonomy = _read_json(_state_path(repo_root, "failure_taxonomy.json"), fallback=default_failure_taxonomy())
    message = error_message.lower()
    for rule in taxonomy.get("rules", []):
        term = str(rule.get("match", "")).lower()
        if term and term in message:
            return {
                "code": rule.get("code", "unknown"),
                "severity": rule.get("severity", "medium"),
            }
    default = taxonomy.get("default", {})
    return {
        "code": default.get("code", "unknown"),
        "severity": default.get("severity", "medium"),
    }


def append_event_log(repo_root: Path, payload: dict[str, Any]) -> None:
    policy = _read_json(_state_path(repo_root, "log_policy.json"), fallback=default_log_policy())
    include_fields = [str(field) for field in policy.get("include_fields", [])]
    trimmed: dict[str, Any] = {}
    for key in include_fields:
        if key in payload:
            trimmed[key] = payload[key]
    if "message" in payload:
        limit = int(policy.get("retain_message_chars", 600))
        trimmed["message"] = str(payload["message"])[:limit]
    path = repo_root / str(policy.get("event_log_path", "metrics/output/logs/metrics-events.ndjson"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trimmed) + "\n")


def _bundle_size_metrics(repo_root: Path) -> dict[str, Any]:
    targets = [
        repo_root / "dashboard" / "index.html",
        repo_root / "reports" / "latest.md",
        repo_root / "artifacts" / "metrics" / "latest" / "manifest.json",
        repo_root / "artifacts" / "metrics" / "latest" / "metrics.json",
        repo_root / "artifacts" / "metrics" / "latest" / "summary.json",
    ]
    present = [path for path in targets if path.exists()]
    if not present:
        return {
            "status": "not_available",
            "reason": "presentation artifacts missing",
        }
    total_bytes = sum(path.stat().st_size for path in present)
    return {
        "status": "success",
        "files": len(present),
        "total_bytes": total_bytes,
    }


def _always_deferred(reason: str) -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": reason,
    }


BUILTIN_COLLECTORS = {
    "bundle_size": lambda repo_root: _bundle_size_metrics(repo_root),
    "openapi_complexity": lambda _repo_root: _always_deferred("collector not yet implemented"),
    "api_surface_diff": lambda _repo_root: _always_deferred("collector not yet implemented"),
    "vitest_coverage": lambda _repo_root: _always_deferred("collector deferred"),
    "playwright_coverage": lambda _repo_root: _always_deferred("collector deferred"),
}


def run_optional_collectors(repo_root: Path, run_id: str) -> dict[str, Any]:
    ensure_ops_state(repo_root)
    extension_cfg = _read_json(_state_path(repo_root, "extensions.json"), fallback=default_extensions_config())
    payload: dict[str, Any] = {
        "status": "not_available",
        "collectors": {},
    }

    any_enabled = False
    any_success = False
    for item in extension_cfg.get("collectors", []):
        name = str(item.get("name", ""))
        enabled = bool(item.get("enabled", False))
        optional = bool(item.get("optional", True))
        if not name:
            continue
        if not enabled:
            payload["collectors"][name] = {
                "status": "not_available",
                "optional": optional,
                "reason": "disabled",
            }
            continue
        any_enabled = True
        collector = BUILTIN_COLLECTORS.get(name)
        if collector is None:
            payload["collectors"][name] = {
                "status": "not_available",
                "optional": optional,
                "reason": "collector not registered",
            }
            continue
        result = collector(repo_root)
        payload["collectors"][name] = {
            "optional": optional,
            **result,
        }
        if result.get("status") == "success":
            any_success = True

    if not any_enabled:
        payload["status"] = "not_available"
    elif any_success:
        payload["status"] = "partial"
    else:
        payload["status"] = "not_available"

    out = repo_root / "metrics" / "output" / "extensions" / run_id / "optional_collectors.json"
    _write_json(out, payload)

    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    if latest_metrics_path.exists():
        latest_metrics = _read_json(latest_metrics_path)
        modules = latest_metrics.setdefault("modules", {})
        modules["optional_collectors"] = payload
        _write_json(latest_metrics_path, latest_metrics)

    return payload


def apply_retention_policy(repo_root: Path, max_history_runs: int) -> dict[str, Any]:
    history_root = repo_root / "artifacts" / "metrics" / "history"
    if not history_root.exists() or max_history_runs <= 0:
        return {"kept": 0, "pruned": []}

    runs = [item for item in history_root.iterdir() if item.is_dir()]
    runs.sort(key=lambda path: path.name)

    if len(runs) <= max_history_runs:
        return {"kept": len(runs), "pruned": []}

    prune = runs[: len(runs) - max_history_runs]
    pruned_names: list[str] = []
    for run in prune:
        pruned_names.append(run.name)
        for child in run.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(run.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        run.rmdir()
    return {"kept": max_history_runs, "pruned": pruned_names}
