#!/usr/bin/env python3
"""Deterministic package manifest hashing.

Computes SHA256 from package.json + package-lock.json concatenation.
Equivalent to devctl's compute_manifest_hash() Bash function:
    cat package.json package-lock.json | sha256sum | awk '{print $1}'

Usage (CLI):
    python3 dev/lib/manifest_hash.py compute <directory>
    python3 dev/lib/manifest_hash.py compare <directory> <hash_file>
"""

from __future__ import annotations

import hashlib
import sys
from collections import namedtuple
from pathlib import Path

CompareResult = namedtuple("CompareResult", ["match", "host_hash", "stored_hash"])


def compute_hash(directory: Path) -> str:
    """Compute SHA256 hex digest from package.json + package-lock.json.

    Returns empty string if either file is missing.
    """
    pkg_json = directory / "package.json"
    lock_json = directory / "package-lock.json"

    if not pkg_json.exists() or not lock_json.exists():
        return ""

    h = hashlib.sha256()
    h.update(pkg_json.read_bytes())
    h.update(lock_json.read_bytes())
    return h.hexdigest()


def read_hash_file(path: Path) -> str:
    """Read a single-line hash file, strip whitespace."""
    return path.read_text(encoding="utf-8").strip()


def compare(host_dir: Path, hash_file: Path) -> CompareResult:
    """Compare computed hash of host_dir against stored hash in hash_file."""
    host_hash = compute_hash(host_dir)
    stored_hash = read_hash_file(hash_file)
    return CompareResult(
        match=(host_hash == stored_hash),
        host_hash=host_hash,
        stored_hash=stored_hash,
    )


def _cli_compute(args: list[str]) -> int:
    if len(args) != 1:
        print("Usage: manifest_hash.py compute <directory>", file=sys.stderr)
        return 2
    result = compute_hash(Path(args[0]))
    if not result:
        print("error: missing package.json or package-lock.json", file=sys.stderr)
        return 1
    print(result)
    return 0


def _cli_compare(args: list[str]) -> int:
    if len(args) != 2:
        print("Usage: manifest_hash.py compare <directory> <hash_file>", file=sys.stderr)
        return 2
    result = compare(Path(args[0]), Path(args[1]))
    if result.match:
        return 0
    print(
        f"mismatch: host={result.host_hash} stored={result.stored_hash}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: manifest_hash.py {compute|compare} ...", file=sys.stderr)
        return 2

    command, rest = args[0], args[1:]
    if command == "compute":
        return _cli_compute(rest)
    if command == "compare":
        return _cli_compare(rest)

    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
