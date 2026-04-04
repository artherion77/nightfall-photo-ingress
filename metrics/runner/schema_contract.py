from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def _read_schema(file_name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / file_name).read_text(encoding="utf-8"))


def manifest_schema() -> dict[str, Any]:
    return _read_schema("manifest.schema.v1.json")


def metrics_schema() -> dict[str, Any]:
    return _read_schema("metrics.schema.v1.json")


def _require_object(name: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    return payload


def validate_manifest_payload(payload: Any) -> None:
    data = _require_object("manifest", payload)
    required = [
        "schema_version",
        "run_id",
        "source",
        "trigger",
        "execution",
        "tools",
        "steps",
        "artifacts",
        "publication",
        "warnings",
        "failures",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"manifest missing required keys: {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValueError("manifest schema_version must equal 1")
    source = _require_object("manifest.source", data["source"])
    commit = source.get("commit_sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("manifest.source.commit_sha must be a 40-char sha")


def validate_metrics_payload(payload: Any) -> None:
    data = _require_object("metrics", payload)
    required = ["schema_version", "run_id", "source", "collection_status", "modules", "delta"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"metrics missing required keys: {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValueError("metrics schema_version must equal 1")
    source = _require_object("metrics.source", data["source"])
    commit = source.get("commit_sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("metrics.source.commit_sha must be a 40-char sha")
    modules = _require_object("metrics.modules", data["modules"])
    for key in ("backend", "frontend"):
        if key not in modules or not isinstance(modules[key], dict):
            raise ValueError(f"metrics.modules.{key} must exist")
