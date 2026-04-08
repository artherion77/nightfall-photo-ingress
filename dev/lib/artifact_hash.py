#!/usr/bin/env python3
"""Deterministic artifact hashing utilities for govctl."""

from __future__ import annotations

import argparse
import glob
import hashlib
from pathlib import Path


def _has_glob_chars(value: str) -> bool:
    return any(ch in value for ch in "*?[]")


def _hash_files(paths: list[Path], rel_base: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.as_posix()):
        rel = path.relative_to(rel_base).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def compute_artifact_hash(expr: str, cwd: Path) -> str:
    p = Path(expr)
    if not p.is_absolute():
        p = (cwd / p).resolve()

    if p.exists() and p.is_file():
        return _hash_files([p], p.parent)

    if p.exists() and p.is_dir():
        files = [x for x in p.rglob("*") if x.is_file()]
        if not files:
            raise ValueError(f"directory contains no files: {expr}")
        return _hash_files(files, p)

    if _has_glob_chars(expr):
        matches = [Path(m).resolve() for m in glob.glob(str(cwd / expr), recursive=True)]
        files = [m for m in matches if m.is_file()]
        if not files:
            raise ValueError(f"glob matched no files: {expr}")
        return _hash_files(files, cwd)

    raise ValueError(f"artifact path not found: {expr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artifact_hash.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_compute = sub.add_parser("compute")
    p_compute.add_argument("artifact_expr")
    p_compute.add_argument("--cwd", default=".")

    args = parser.parse_args(argv)
    if args.cmd == "compute":
        try:
            print(compute_artifact_hash(args.artifact_expr, Path(args.cwd).resolve()))
            return 0
        except ValueError as exc:
            print(f"ERROR:{exc}")
            return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
