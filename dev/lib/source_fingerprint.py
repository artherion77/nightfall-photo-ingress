#!/usr/bin/env python3
"""Deterministic source fingerprinting and build stamp writing."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_INCLUDE_GLOBS = [
    "**/*.svelte",
    "**/*.ts",
    "**/*.js",
    "**/*.css",
    "svelte.config.js",
    "vite.config.js",
    "package.json",
    "package-lock.json",
]
DEFAULT_EXCLUDE_DIRS = ["node_modules", ".svelte-kit"]


def compute_fingerprint(
    root: Path,
    include_globs: list[str],
    exclude_dirs: list[str],
) -> str:
    """Compute deterministic SHA256 over sorted matching files."""
    paths: list[Path] = []
    for pattern in include_globs:
        paths.extend(root.glob(pattern))

    hasher = hashlib.sha256()
    selected = [
        p
        for p in paths
        if p.is_file() and not any(excluded in p.parts for excluded in exclude_dirs)
    ]

    for path in sorted(set(selected), key=lambda p: str(p.relative_to(root))):
        hasher.update(str(path.relative_to(root)).encode("utf-8"))
        hasher.update(path.read_bytes())

    return hasher.hexdigest()


def write_build_stamp(
    root: Path,
    stamp_path: Path,
    include_globs: list[str],
    exclude_dirs: list[str],
) -> dict[str, str]:
    """Compute fingerprint and write JSON stamp."""
    fingerprint = compute_fingerprint(root, include_globs, exclude_dirs)
    stamp = {
        "fingerprint": fingerprint,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source_fingerprint.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_compute = subparsers.add_parser("compute")
    p_compute.add_argument("root")
    p_compute.add_argument("--include", nargs="+", default=None)
    p_compute.add_argument("--exclude-dir", nargs="+", default=None)

    p_stamp = subparsers.add_parser("stamp")
    p_stamp.add_argument("root")
    p_stamp.add_argument("stamp_path")
    p_stamp.add_argument("--include", nargs="+", default=None)
    p_stamp.add_argument("--exclude-dir", nargs="+", default=None)

    return parser


def _resolve_include(value: list[str] | None) -> list[str]:
    return DEFAULT_INCLUDE_GLOBS if value is None else list(value)


def _resolve_exclude(value: list[str] | None) -> list[str]:
    return DEFAULT_EXCLUDE_DIRS if value is None else list(value)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    include_globs = _resolve_include(args.include)
    exclude_dirs = _resolve_exclude(args.exclude_dir)

    if args.command == "compute":
        print(compute_fingerprint(Path(args.root), include_globs, exclude_dirs))
        return 0

    if args.command == "stamp":
        stamp = write_build_stamp(
            Path(args.root),
            Path(args.stamp_path),
            include_globs,
            exclude_dirs,
        )
        print(json.dumps(stamp))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
