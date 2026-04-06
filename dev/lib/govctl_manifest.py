#!/usr/bin/env python3
"""Validate and normalize govctl target manifest YAML.

This helper is designed for Bash callers: it reads a YAML manifest,
validates schema and reference integrity, and emits normalized JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # pragma: no cover - exercised only in broken envs
    print(f"ERROR: PyYAML import failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


class ManifestError(ValueError):
    """Manifest validation error."""


def _as_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field_name} must be a mapping")
    return value


def _as_list_of_str(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ManifestError(f"{field_name} must be a list of strings")
    return value


def _validate_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ManifestError(f"{field_name} must be a positive integer")
    return value


def _validate_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ManifestError(f"{field_name} must be boolean")
    return value


def _expand_group_targets(
    group_name: str,
    groups: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    stack: list[str] | None = None,
    memo: dict[str, list[str]] | None = None,
) -> list[str]:
    stack = stack or []
    memo = memo or {}

    if group_name in memo:
        return memo[group_name]

    if group_name in stack:
        cycle = " -> ".join(stack + [group_name])
        raise ManifestError(f"groups contain a cycle: {cycle}")

    group = groups.get(group_name)
    if group is None:
        raise ManifestError(f"unknown group reference: {group_name}")

    expanded: list[str] = []
    seen: set[str] = set()

    for ref in group["targets"]:
        if ref in targets:
            if ref not in seen:
                expanded.append(ref)
                seen.add(ref)
            continue

        if ref in groups:
            nested = _expand_group_targets(ref, groups, targets, stack + [group_name], memo)
            for target_name in nested:
                if target_name not in seen:
                    expanded.append(target_name)
                    seen.add(target_name)
            continue

        raise ManifestError(
            f"group '{group_name}' references unknown target/group '{ref}'"
        )

    memo[group_name] = expanded
    return expanded


def _expand_requires_ref(
    ref: str,
    groups: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
) -> list[str]:
    if ref in targets:
        return [ref]
    if ref in groups:
        return _expand_group_targets(ref, groups, targets)
    raise ManifestError(f"unknown requires reference '{ref}'")


def _detect_requires_cycle(adjacency: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        if node in visiting:
            cycle_start = path.index(node)
            cycle = " -> ".join(path[cycle_start:] + [node])
            raise ManifestError(f"requires graph contains a cycle: {cycle}")
        if node in visited:
            return

        visiting.add(node)
        for dep in adjacency.get(node, []):
            dfs(dep, path + [dep])
        visiting.remove(node)
        visited.add(node)

    for target_name in adjacency:
        if target_name not in visited:
            dfs(target_name, [target_name])


def validate_and_normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    root = _as_dict(raw, "manifest")

    if "version" not in root:
        raise ManifestError("version is required")
    version = _validate_positive_int(root["version"], "version")

    defaults_in = root.get("defaults", {})
    defaults = _as_dict(defaults_in, "defaults")
    lock_default = defaults.get("lock", False)
    timeout_default = defaults.get("timeout_seconds", 300)
    lock_default = _validate_bool(lock_default, "defaults.lock")
    timeout_default = _validate_positive_int(timeout_default, "defaults.timeout_seconds")

    if "targets" not in root:
        raise ManifestError("targets is required")
    targets_in = _as_dict(root["targets"], "targets")
    if not targets_in:
        raise ManifestError("targets must not be empty")

    groups_in = root.get("groups", {})
    groups_raw = _as_dict(groups_in, "groups")

    targets: dict[str, dict[str, Any]] = {}
    for target_name, target_raw in targets_in.items():
        if not isinstance(target_name, str) or not target_name:
            raise ManifestError("target names must be non-empty strings")
        target = _as_dict(target_raw, f"targets.{target_name}")

        description = target.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ManifestError(f"targets.{target_name}.description must be a non-empty string")

        command = target.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ManifestError(f"targets.{target_name}.command must be a non-empty string")

        requires = _as_list_of_str(target.get("requires", []), f"targets.{target_name}.requires")
        preflight = _as_list_of_str(
            target.get("preflight", []), f"targets.{target_name}.preflight"
        )

        lock = target.get("lock", lock_default)
        lock = _validate_bool(lock, f"targets.{target_name}.lock")

        timeout = target.get("timeout_seconds", timeout_default)
        timeout = _validate_positive_int(timeout, f"targets.{target_name}.timeout_seconds")

        targets[target_name] = {
            "description": description.strip(),
            "command": command,
            "requires": requires,
            "preflight": preflight,
            "lock": lock,
            "timeout_seconds": timeout,
        }

    groups: dict[str, dict[str, Any]] = {}
    for group_name, group_raw in groups_raw.items():
        if not isinstance(group_name, str) or not group_name:
            raise ManifestError("group names must be non-empty strings")
        group = _as_dict(group_raw, f"groups.{group_name}")
        group_targets = _as_list_of_str(group.get("targets"), f"groups.{group_name}.targets")
        if not group_targets:
            raise ManifestError(f"groups.{group_name}.targets must not be empty")
        groups[group_name] = {"targets": group_targets}

    expanded_groups: dict[str, list[str]] = {}
    for group_name in groups:
        expanded_groups[group_name] = _expand_group_targets(group_name, groups, targets)

    adjacency: dict[str, list[str]] = {}
    for target_name, target in targets.items():
        expanded_requires: list[str] = []
        seen: set[str] = set()
        for ref in target["requires"]:
            for dep_target in _expand_requires_ref(ref, groups, targets):
                if dep_target == target_name:
                    raise ManifestError(
                        f"targets.{target_name}.requires contains self-reference '{dep_target}'"
                    )
                if dep_target not in seen:
                    expanded_requires.append(dep_target)
                    seen.add(dep_target)

        target["requires_expanded"] = expanded_requires
        adjacency[target_name] = expanded_requires

    _detect_requires_cycle(adjacency)

    return {
        "version": version,
        "defaults": {
            "lock": lock_default,
            "timeout_seconds": timeout_default,
        },
        "targets": targets,
        "groups": groups,
        "groups_expanded": expanded_groups,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ManifestError(f"manifest file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raise ManifestError(f"manifest file is empty: {path}")

    return validate_and_normalize_manifest(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and normalize a govctl manifest YAML file"
    )
    parser.add_argument(
        "manifest_path",
        nargs="?",
        default="dev/govctl-targets.yaml",
        help="Path to govctl YAML manifest (default: dev/govctl-targets.yaml)",
    )
    args = parser.parse_args(argv)

    try:
        normalized = load_manifest(Path(args.manifest_path))
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(normalized, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())