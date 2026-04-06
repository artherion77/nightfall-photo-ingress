#!/usr/bin/env python3
"""Resolve requested govctl targets/groups to execution order.

This helper consumes the normalized JSON emitted by govctl_manifest.py and
prints a newline-delimited topological execution order.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class ResolveError(ValueError):
    """Resolution error for requested targets/groups."""


def _load_manifest_json(path: str | None) -> dict[str, Any]:
    try:
        if path is None or path == "-":
            payload = json.load(sys.stdin)
        else:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResolveError(f"manifest JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        source = "stdin" if path in (None, "-") else path
        raise ResolveError(f"invalid JSON in {source}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ResolveError("manifest JSON root must be an object")
    if "targets" not in payload or not isinstance(payload["targets"], dict):
        raise ResolveError("manifest JSON missing targets mapping")
    if "groups_expanded" not in payload or not isinstance(payload["groups_expanded"], dict):
        raise ResolveError("manifest JSON missing groups_expanded mapping")

    return payload


def _expand_requested_name(manifest: dict[str, Any], name: str) -> list[str]:
    targets = manifest["targets"]
    groups_expanded = manifest["groups_expanded"]

    if name in targets:
        return [name]
    if name in groups_expanded:
        return list(groups_expanded[name])
    raise ResolveError(f"unknown target/group '{name}'")


def resolve_requested_targets(manifest: dict[str, Any], requested: list[str]) -> list[str]:
    if not requested:
        raise ResolveError("at least one target or group must be requested")

    targets = manifest["targets"]

    requested_targets: list[str] = []
    seen_requested: set[str] = set()
    for name in requested:
        for target_name in _expand_requested_name(manifest, name):
            if target_name not in seen_requested:
                requested_targets.append(target_name)
                seen_requested.add(target_name)

    resolved: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def dfs(target_name: str) -> None:
        if target_name in visiting:
            raise ResolveError(f"cycle encountered while resolving target '{target_name}'")
        if target_name in visited:
            return

        visiting.add(target_name)
        requires = targets[target_name].get("requires_expanded")
        if not isinstance(requires, list):
            raise ResolveError(
                f"target '{target_name}' missing requires_expanded; manifest must be normalized"
            )

        for dep in requires:
            if dep not in targets:
                raise ResolveError(f"target '{target_name}' depends on unknown target '{dep}'")
            dfs(dep)

        visiting.remove(target_name)
        visited.add(target_name)
        resolved.append(target_name)

    for target_name in requested_targets:
        dfs(target_name)

    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve requested govctl targets/groups to execution order"
    )
    parser.add_argument(
        "requested",
        nargs="+",
        help="Requested target/group names to resolve",
    )
    parser.add_argument(
        "--manifest-json",
        default="-",
        help="Path to normalized manifest JSON, or '-' to read from stdin (default: -)",
    )
    args = parser.parse_args(argv)

    try:
        manifest = _load_manifest_json(args.manifest_json)
        resolved = resolve_requested_targets(manifest, args.requested)
    except ResolveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for target_name in resolved:
        print(target_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())