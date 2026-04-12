"""Read-only parser for authoritative `.hashes.v2` cache files."""

from __future__ import annotations

import re
from pathlib import Path


CACHE_SCHEMA_HEADER = "CACHE_SCHEMA v2"
DIRECTORY_HASH_HEADER_RE = re.compile(r"^DIRECTORY_HASH\s+([0-9a-fA-F]{40})$")
SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class HashImportParseError(RuntimeError):
    """Raised when a `.hashes.v2` cache file fails validation."""

    def __init__(self, source: str, line_number: int, message: str) -> None:
        self.source = source
        self.line_number = line_number
        self.message = message
        super().__init__(f"{source}: line {line_number}: {message}")


def parse_hashes_v2_file(cache_path: Path) -> tuple[str, ...]:
    """Parse one `.hashes.v2` file and return validated SHA-256 values."""

    try:
        text = cache_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HashImportParseError(str(cache_path), 0, f"unable to read file: {exc}") from exc

    return parse_hashes_v2_text(text, source=str(cache_path))


def parse_hashes_v2_text(text: str, *, source: str = "<memory>") -> tuple[str, ...]:
    """Parse `.hashes.v2` content and return validated SHA-256 values."""

    lines = text.splitlines()
    if not lines or lines[0] != CACHE_SCHEMA_HEADER:
        raise HashImportParseError(source, 1, "expected exact header 'CACHE_SCHEMA v2'")

    if len(lines) < 2:
        raise HashImportParseError(source, 2, "missing DIRECTORY_HASH header")
    if DIRECTORY_HASH_HEADER_RE.fullmatch(lines[1]) is None:
        raise HashImportParseError(source, 2, "invalid DIRECTORY_HASH header")

    sha256_values: list[str] = []
    for line_number, raw_line in enumerate(lines[2:], start=3):
        columns = raw_line.split("\t")
        if len(columns) != 3:
            raise HashImportParseError(source, line_number, "expected exactly 3 tab-separated fields")

        sha1_value, sha256_value, path_value = columns
        if SHA1_RE.fullmatch(sha1_value) is None:
            raise HashImportParseError(source, line_number, "invalid SHA-1 value in column 1")
        if SHA256_RE.fullmatch(sha256_value) is None:
            raise HashImportParseError(source, line_number, "invalid SHA-256 value in column 2")
        if not path_value:
            raise HashImportParseError(source, line_number, "empty path in column 3")

        sha256_values.append(sha256_value.lower())

    return tuple(sha256_values)