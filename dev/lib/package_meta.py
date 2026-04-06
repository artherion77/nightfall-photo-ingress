#!/usr/bin/env python3
"""Package metadata helpers for Node version and dependency consistency."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import namedtuple
from pathlib import Path

Mismatch = namedtuple("Mismatch", ["package", "left_major", "right_major"])
ConsistencyResult = namedtuple("ConsistencyResult", ["ok", "mismatches"])


def read_node_version(repo_root: Path) -> str:
    """Read pinned Node version, preferring .node-version over .nvmrc."""
    node_version = repo_root / ".node-version"
    nvmrc = repo_root / ".nvmrc"

    raw = ""
    if node_version.is_file():
        raw = node_version.read_text(encoding="utf-8")
    elif nvmrc.is_file():
        raw = nvmrc.read_text(encoding="utf-8")

    raw = "".join(raw.split())
    return raw[1:] if raw.startswith("v") else raw


def extract_major(semver: str) -> int:
    """Extract major number from semver/range string.

    Supported examples: 5.3.1, ^5.3.1, ~5.3.1, >=5.3.1, <=5.3.1, >5, <5.
    Raises ValueError when no leading major can be extracted.
    """
    value = semver.strip()

    if value.startswith(">=") or value.startswith("<="):
        value = value[2:]
    elif value.startswith("^") or value.startswith("~") or value.startswith(">") or value.startswith("<"):
        value = value[1:]

    match = re.match(r"(\d+)", value)
    if not match:
        raise ValueError(f"unable to extract major from semver: {semver}")
    return int(match.group(1))


def dependency_version(package_json: Path, name: str) -> str:
    """Read devDependencies[name] from package.json, returning empty if absent."""
    pkg = json.loads(package_json.read_text(encoding="utf-8"))
    dev_deps = pkg.get("devDependencies", {})
    if not isinstance(dev_deps, dict):
        return ""
    value = dev_deps.get(name, "")
    return value if isinstance(value, str) else ""


def check_stack_consistency(
    webui_pkg: Path,
    dashboard_pkg: Path,
    packages: list[str],
) -> ConsistencyResult:
    """Compare package major versions between two package.json manifests."""
    mismatches: list[Mismatch] = []

    for package_name in packages:
        left = dependency_version(webui_pkg, package_name)
        right = dependency_version(dashboard_pkg, package_name)

        try:
            left_major = extract_major(left)
            right_major = extract_major(right)
        except ValueError:
            mismatches.append(Mismatch(package_name, "", ""))
            continue

        if left_major != right_major:
            mismatches.append(Mismatch(package_name, str(left_major), str(right_major)))

    return ConsistencyResult(ok=(len(mismatches) == 0), mismatches=mismatches)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="package_meta.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_node = subparsers.add_parser("node-version")
    p_node.add_argument("repo_root")

    p_dep = subparsers.add_parser("dep-version")
    p_dep.add_argument("package_json")
    p_dep.add_argument("name")

    p_consistency = subparsers.add_parser("check-consistency")
    p_consistency.add_argument("webui_pkg")
    p_consistency.add_argument("dashboard_pkg")
    p_consistency.add_argument(
        "--packages",
        nargs="+",
        default=["@sveltejs/kit", "vite"],
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "node-version":
        print(read_node_version(Path(args.repo_root)))
        return 0

    if args.command == "dep-version":
        print(dependency_version(Path(args.package_json), args.name))
        return 0

    if args.command == "check-consistency":
        result = check_stack_consistency(
            Path(args.webui_pkg),
            Path(args.dashboard_pkg),
            list(args.packages),
        )
        if result.ok:
            print("ok")
            return 0

        for mismatch in result.mismatches:
            if mismatch.left_major == "" and mismatch.right_major == "":
                print(
                    f"{mismatch.package}: unable to derive major version from one or both manifests",
                    file=sys.stderr,
                )
            else:
                print(
                    f"{mismatch.package}: major mismatch left={mismatch.left_major} right={mismatch.right_major}",
                    file=sys.stderr,
                )
        return 1

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
