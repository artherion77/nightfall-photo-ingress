"""Read-only parser and walker for authoritative `.hashes.v2` cache files."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import TextIO

from .domain.registry import HashImportChunkResult, Registry
from .domain.storage import sha256_file


CACHE_SCHEMA_HEADER = "CACHE_SCHEMA v2"
HASHFILE_V2_NAME = ".hashes.v2"
HASHFILE_V1_NAMES = (".hashes.sha1", ".hashes.v1")
DIRECTORY_HASH_HEADER_RE = re.compile(r"^DIRECTORY_HASH\s+([0-9a-fA-F]{40})$")
SHA1_ROW_RE = re.compile(r"^([0-9a-fA-F]{40})\s+[ *](.+)$")
SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
IGNORED_FILENAMES = frozenset({HASHFILE_V2_NAME, *HASHFILE_V1_NAMES})
IGNORED_BASENAMES_CASEFOLD = frozenset({"thumbs.db"})
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HashImportDirectoryRow:
    """One in-memory v2-equivalent row for hash-import."""

    sha1: str
    sha256: str
    path: Path


@dataclass(frozen=True)
class HashImportDirectoryPlan:
    """Import plan for a single directory in the library tree."""

    directory: Path
    source: str
    sha256_values: tuple[str, ...]
    stale_or_invalid_cache_replaced: bool = False


@dataclass(frozen=True)
class HashImportSummary:
    """Aggregate result for one recursive hash-import run."""

    directories_processed: int
    recomputes_performed: int
    valid_caches_consumed: int
    stale_invalid_caches_replaced: int
    total_imported: int
    total_skipped: int
    chunk_results: tuple[HashImportChunkResult, ...]


class HashImportError(RuntimeError):
    """Raised when hash-import tree walking fails before or during import."""


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

    _, rows = _parse_hashes_v2_lines(text, source=source)
    return tuple(sha256_value for _, sha256_value, _ in rows)


def build_hash_import_directory_plan(*, root_path: Path, directory: Path) -> HashImportDirectoryPlan:
    """Build import plan for one directory using v2, v1 backfill, or recompute."""

    current_dir_hash = _compute_directory_hash(directory)
    v2_path = directory / HASHFILE_V2_NAME
    if v2_path.exists():
        try:
            rows = _parse_hashes_v2_cache(
                cache_path=v2_path,
                directory=directory,
                expected_directory_hash=current_dir_hash,
            )
            return HashImportDirectoryPlan(
                directory=directory,
                source="cache_v2",
                sha256_values=tuple(row.sha256 for row in rows),
            )
        except HashImportParseError:
            rows = _rehash_directory_rows(directory)
            return HashImportDirectoryPlan(
                directory=directory,
                source="recompute",
                sha256_values=tuple(row.sha256 for row in rows),
                stale_or_invalid_cache_replaced=True,
            )

    v1_path = _find_v1_cache_path(directory)
    if v1_path is not None:
        try:
            rows = _backfill_v2_rows_from_v1(
                cache_path=v1_path,
                directory=directory,
                expected_directory_hash=current_dir_hash,
            )
            return HashImportDirectoryPlan(
                directory=directory,
                source="backfill_v1",
                sha256_values=tuple(row.sha256 for row in rows),
            )
        except HashImportParseError:
            rows = _rehash_directory_rows(directory)
            return HashImportDirectoryPlan(
                directory=directory,
                source="recompute",
                sha256_values=tuple(row.sha256 for row in rows),
                stale_or_invalid_cache_replaced=True,
            )

    rows = _rehash_directory_rows(directory)
    return HashImportDirectoryPlan(
        directory=directory,
        source="recompute",
        sha256_values=tuple(row.sha256 for row in rows),
    )


def run_hash_import(*, root_path: Path, registry: Registry, chunk_size: int) -> HashImportSummary:
    """Walk a library tree and import authoritative SHA-256 hashes."""

    plans = _collect_hash_import_plans(root_path)
    chunk_results = _execute_hash_import_chunks(
        registry=registry,
        hashes=[sha256_value for plan in plans for sha256_value in plan.sha256_values],
        chunk_size=chunk_size,
        dry_run=False,
    )
    return _build_hash_import_summary(plans=plans, chunk_results=chunk_results)


def run_hash_import_command(
    *,
    root_path: Path,
    registry: Registry,
    chunk_size: int,
    dry_run: bool,
    quiet: bool,
    stats: bool,
    logger: logging.Logger | None = None,
    out: TextIO | None = None,
) -> HashImportSummary:
    """Execute hash-import with human output and structured log records."""

    target_logger = logger or LOGGER
    target_out = out or sys.stdout

    plans = _collect_hash_import_plans(root_path)
    chunk_results = _execute_hash_import_chunks(
        registry=registry,
        hashes=[sha256_value for plan in plans for sha256_value in plan.sha256_values],
        chunk_size=chunk_size,
        dry_run=dry_run,
    )
    summary = _build_hash_import_summary(plans=plans, chunk_results=chunk_results)

    _emit_hash_import_logs(target_logger, summary=summary, chunk_results=chunk_results, dry_run=dry_run)
    _write_hash_import_output(target_out, summary=summary, dry_run=dry_run, quiet=quiet, stats=stats)
    return summary


def format_hash_import_error(exc: Exception) -> str:
    """Render hash-import errors with CLI-facing prefix text."""

    return f"ERROR: {exc}"


def _collect_hash_import_plans(root_path: Path) -> tuple[HashImportDirectoryPlan, ...]:
    """Validate root and build directory plans in stable tree order."""

    if not root_path.exists():
        raise HashImportError(f"hash-import root does not exist: {root_path}")
    if not root_path.is_dir():
        raise HashImportError(f"hash-import root is not a directory: {root_path}")

    directories = _iter_candidate_directories(root_path)
    if not directories:
        return ()
    return tuple(build_hash_import_directory_plan(root_path=root_path, directory=directory) for directory in directories)


def _build_hash_import_summary(
    *,
    plans: tuple[HashImportDirectoryPlan, ...],
    chunk_results: tuple[HashImportChunkResult, ...],
) -> HashImportSummary:
    """Assemble aggregate summary from per-directory plans and chunk results."""

    return HashImportSummary(
        directories_processed=len(plans),
        recomputes_performed=sum(1 for plan in plans if plan.source != "cache_v2"),
        valid_caches_consumed=sum(1 for plan in plans if plan.source == "cache_v2"),
        stale_invalid_caches_replaced=sum(1 for plan in plans if plan.stale_or_invalid_cache_replaced),
        total_imported=sum(result.imported for result in chunk_results),
        total_skipped=sum(result.skipped_existing for result in chunk_results),
        chunk_results=chunk_results,
    )


def _execute_hash_import_chunks(
    *,
    registry: Registry,
    hashes: list[str],
    chunk_size: int,
    dry_run: bool,
) -> tuple[HashImportChunkResult, ...]:
    """Execute or simulate chunked hash-import work."""

    if chunk_size <= 0:
        raise HashImportError("chunk_size must be > 0")
    if not hashes:
        return ()

    reports: list[HashImportChunkResult] = []
    known_existing = _fetch_existing_hash_import_hashes(registry.db_path, hashes) if dry_run else set()
    simulated_seen = set(known_existing)

    for chunk_index, start in enumerate(range(0, len(hashes), chunk_size), start=1):
        chunk_hashes = hashes[start : start + chunk_size]
        if dry_run:
            imported = 0
            skipped_existing = 0
            for hash_value in chunk_hashes:
                if hash_value in simulated_seen:
                    skipped_existing += 1
                    continue
                imported += 1
                simulated_seen.add(hash_value)
            reports.append(
                HashImportChunkResult(
                    chunk_index=chunk_index,
                    imported=imported,
                    skipped_existing=skipped_existing,
                )
            )
            continue

        start_ts = perf_counter()
        chunk_result = registry.bulk_insert_hash_import(
            hashes=chunk_hashes,
            chunk_size=len(chunk_hashes),
        )[0]
        duration_seconds = perf_counter() - start_ts
        reports.append(
            HashImportChunkResult(
                chunk_index=chunk_index,
                imported=chunk_result.imported,
                skipped_existing=chunk_result.skipped_existing,
                duration_seconds=duration_seconds,
            )
        )

    return tuple(reports)


def _fetch_existing_hash_import_hashes(db_path: Path, hashes: list[str]) -> set[str]:
    """Return hash-import SHA-256 values already present in the registry."""

    existing: set[str] = set()
    unique_hashes = sorted(set(hashes))
    if not unique_hashes:
        return existing

    with sqlite3.connect(db_path) as conn:
        for start in range(0, len(unique_hashes), 500):
            chunk = unique_hashes[start : start + 500]
            placeholders = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT hash_value
                FROM external_hash_cache
                WHERE account_name = '__hash_import__'
                  AND source_relpath IS NULL
                  AND hash_algo = 'sha256'
                  AND hash_value IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            existing.update(str(row[0]) for row in rows)
    return existing


def _emit_hash_import_logs(
    logger: logging.Logger,
    *,
    summary: HashImportSummary,
    chunk_results: tuple[HashImportChunkResult, ...],
    dry_run: bool,
) -> None:
    """Emit structured chunk and summary logs for hash-import."""

    total_duration = 0.0
    for result in chunk_results:
        duration_seconds = result.duration_seconds or 0.0
        total_duration += duration_seconds
        logger.info(
            "hash-import chunk completed",
            extra={
                "command": "hash-import",
                "chunk_index": result.chunk_index,
                "imported": result.imported,
                "skipped_existing": result.skipped_existing,
                "duration": round(duration_seconds, 6),
                "dry_run": dry_run,
            },
        )

    logger.info(
        "hash-import summary",
        extra={
            "command": "hash-import",
            "chunk_index": 0,
            "imported": summary.total_imported,
            "skipped_existing": summary.total_skipped,
            "duration": round(total_duration, 6),
            "dry_run": dry_run,
            "directories_processed": summary.directories_processed,
            "recomputes_performed": summary.recomputes_performed,
            "valid_caches_consumed": summary.valid_caches_consumed,
            "stale_invalid_caches_replaced": summary.stale_invalid_caches_replaced,
        },
    )


def _write_hash_import_output(
    out: TextIO,
    *,
    summary: HashImportSummary,
    dry_run: bool,
    quiet: bool,
    stats: bool,
) -> None:
    """Render human output for hash-import modes."""

    if quiet:
        return

    if not dry_run:
        for result in summary.chunk_results:
            duration_seconds = result.duration_seconds or 0.0
            print(
                f"[chunk {result.chunk_index}] imported={result.imported} "
                f"skipped_existing={result.skipped_existing} duration={duration_seconds:.2f}s",
                file=out,
            )
        print(
            f"DONE: total_imported={summary.total_imported} total_skipped={summary.total_skipped}",
            file=out,
        )
    else:
        total = summary.total_imported + summary.total_skipped
        print(
            f"DRY RUN: total={total} new={summary.total_imported} existing={summary.total_skipped}",
            file=out,
        )
        if stats:
            for result in summary.chunk_results:
                print(
                    f"[chunk {result.chunk_index}] imported={result.imported} "
                    f"skipped_existing={result.skipped_existing} duration={(result.duration_seconds or 0.0):.2f}s",
                    file=out,
                )

    if stats:
        print(
            "STATS: "
            f"directories_processed={summary.directories_processed} "
            f"recomputes_performed={summary.recomputes_performed} "
            f"valid_caches_consumed={summary.valid_caches_consumed} "
            f"stale_invalid_caches_replaced={summary.stale_invalid_caches_replaced}",
            file=out,
        )


def _parse_hashes_v2_lines(text: str, *, source: str) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    """Return stored directory hash and validated row tuples from v2 text."""

    lines = text.splitlines()
    if not lines or lines[0] != CACHE_SCHEMA_HEADER:
        raise HashImportParseError(source, 1, "expected exact header 'CACHE_SCHEMA v2'")

    if len(lines) < 2:
        raise HashImportParseError(source, 2, "missing DIRECTORY_HASH header")
    match = DIRECTORY_HASH_HEADER_RE.fullmatch(lines[1])
    if match is None:
        raise HashImportParseError(source, 2, "invalid DIRECTORY_HASH header")

    rows: list[tuple[str, str, str]] = []
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

        rows.append((sha1_value.lower(), sha256_value.lower(), path_value))

    return match.group(1).lower(), tuple(rows)


def _parse_hashes_v2_cache(
    *,
    cache_path: Path,
    directory: Path,
    expected_directory_hash: str,
) -> tuple[HashImportDirectoryRow, ...]:
    """Parse one `.hashes.v2` file and validate it against current directory state."""

    text = _read_text_file(cache_path)
    stored_directory_hash, rows = _parse_hashes_v2_lines(text, source=str(cache_path))
    if stored_directory_hash != expected_directory_hash:
        raise HashImportParseError(str(cache_path), 2, "stale DIRECTORY_HASH header")

    parsed_rows: list[HashImportDirectoryRow] = []
    seen_paths: set[Path] = set()
    for line_number, (sha1_value, sha256_value, path_value) in enumerate(rows, start=3):
        file_path = Path(path_value)
        _validate_cache_row_path(
            source=str(cache_path),
            line_number=line_number,
            file_path=file_path,
            directory=directory,
        )
        seen_paths.add(file_path)
        parsed_rows.append(
            HashImportDirectoryRow(
                sha1=sha1_value,
                sha256=sha256_value,
                path=file_path,
            )
        )

    _validate_required_rows(str(cache_path), seen_paths, directory)
    return tuple(parsed_rows)


def _backfill_v2_rows_from_v1(
    *,
    cache_path: Path,
    directory: Path,
    expected_directory_hash: str,
) -> tuple[HashImportDirectoryRow, ...]:
    """Build ephemeral v2-equivalent rows from a current v1 cache file."""

    rows = _parse_hashes_v1_cache(
        cache_path=cache_path,
        directory=directory,
        expected_directory_hash=expected_directory_hash,
    )
    return tuple(
        HashImportDirectoryRow(
            sha1=sha1_value,
            sha256=sha256_file(file_path),
            path=file_path,
        )
        for sha1_value, file_path in rows
    )


def _parse_hashes_v1_cache(
    *,
    cache_path: Path,
    directory: Path,
    expected_directory_hash: str,
) -> tuple[tuple[str, Path], ...]:
    """Parse one legacy v1 cache for ephemeral backfill only."""

    lines = _read_text_file(cache_path).splitlines()
    if not lines:
        raise HashImportParseError(str(cache_path), 1, "missing DIRECTORY_HASH header")

    match = DIRECTORY_HASH_HEADER_RE.fullmatch(lines[0].strip())
    if match is None:
        raise HashImportParseError(str(cache_path), 1, "invalid DIRECTORY_HASH header")
    if match.group(1).lower() != expected_directory_hash:
        raise HashImportParseError(str(cache_path), 1, "stale DIRECTORY_HASH header")

    parsed_rows: list[tuple[str, Path]] = []
    seen_paths: set[Path] = set()
    for line_number, raw_line in enumerate(lines[1:], start=2):
        row_match = SHA1_ROW_RE.fullmatch(raw_line.rstrip("\n"))
        if row_match is None:
            raise HashImportParseError(str(cache_path), line_number, "invalid v1 cache row")

        sha1_value = row_match.group(1).lower()
        file_path = Path(row_match.group(2))
        _validate_cache_row_path(
            source=str(cache_path),
            line_number=line_number,
            file_path=file_path,
            directory=directory,
        )
        seen_paths.add(file_path)
        parsed_rows.append((sha1_value, file_path))

    _validate_required_rows(str(cache_path), seen_paths, directory)
    return tuple(parsed_rows)


def _rehash_directory_rows(directory: Path) -> tuple[HashImportDirectoryRow, ...]:
    """Compute in-memory dual-hash rows without writing cache files."""

    rows: list[HashImportDirectoryRow] = []
    for file_path in _iter_importable_files(directory):
        rows.append(
            HashImportDirectoryRow(
                sha1=_sha1_file(file_path),
                sha256=sha256_file(file_path),
                path=file_path,
            )
        )
    return tuple(rows)


def _validate_cache_row_path(*, source: str, line_number: int, file_path: Path, directory: Path) -> None:
    """Validate a cached path against current directory invariants."""

    if not file_path.is_absolute():
        raise HashImportParseError(source, line_number, "path must be absolute")
    if file_path.parent != directory:
        raise HashImportParseError(source, line_number, "path must belong to cache directory")
    if _is_ignored_file(file_path):
        raise HashImportParseError(source, line_number, "path references ignored file")
    if not file_path.exists() or not file_path.is_file():
        raise HashImportParseError(source, line_number, "path does not exist as a file")


def _validate_required_rows(source: str, seen_paths: set[Path], directory: Path) -> None:
    """Ensure cache rows cover the exact current directory file set."""

    actual_files = set(_iter_importable_files(directory))
    if actual_files != seen_paths:
        raise HashImportParseError(source, 0, "cache rows do not match current directory contents")


def _iter_candidate_directories(root_path: Path) -> tuple[Path, ...]:
    """Return directories relevant to hash-import in stable order."""

    candidates: list[Path] = []
    for directory in [root_path, *sorted((path for path in root_path.rglob("*") if path.is_dir()), key=lambda path: str(path.relative_to(root_path)))]:
        if _directory_has_hash_import_inputs(directory):
            candidates.append(directory)
    return tuple(candidates)


def _directory_has_hash_import_inputs(directory: Path) -> bool:
    """Return True when a directory contains cache files or importable content."""

    try:
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if path.name == HASHFILE_V2_NAME or path.name in HASHFILE_V1_NAMES:
                return True
            if not _is_ignored_file(path):
                return True
    except OSError as exc:
        raise HashImportError(f"unable to list directory {directory}: {exc}") from exc
    return False


def _find_v1_cache_path(directory: Path) -> Path | None:
    """Return the existing legacy v1 cache path for a directory, if any."""

    for name in HASHFILE_V1_NAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _read_text_file(path: Path) -> str:
    """Read UTF-8 text or raise a parse error with file context."""

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HashImportParseError(str(path), 0, f"unable to read file: {exc}") from exc


def _iter_importable_files(directory: Path) -> tuple[Path, ...]:
    """Return immediate importable files in C-locale basename order."""

    try:
        return tuple(
            sorted(
                (
                    path
                    for path in directory.iterdir()
                    if path.is_file() and not _is_ignored_file(path)
                ),
                key=lambda path: os.fsencode(path.name),
            )
        )
    except OSError as exc:
        raise HashImportError(f"unable to list directory {directory}: {exc}") from exc


def _is_ignored_file(path: Path) -> bool:
    """Return True for cache/meta files excluded from hash-import content."""

    return path.name in IGNORED_FILENAMES or path.name.casefold() in IGNORED_BASENAMES_CASEFOLD


def _compute_directory_hash(directory: Path) -> str:
    """Compute directory hash using the exact producer line semantics."""

    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        find_process = subprocess.Popen(
            [
                "find",
                str(directory),
                "-maxdepth",
                "1",
                "-type",
                "f",
                "!",
                "-name",
                ".hashes.sha1",
                "!",
                "-name",
                ".hashes.v1",
                "!",
                "-name",
                ".hashes.v2",
                "!",
                "-iname",
                "thumbs.db",
                "-printf",
                "%f %s %T@\n",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        sort_process = subprocess.Popen(
            ["sort"],
            stdin=find_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        assert find_process.stdout is not None
        find_process.stdout.close()
        sha1sum_process = subprocess.run(
            ["sha1sum"],
            stdin=sort_process.stdout,
            capture_output=True,
            check=True,
            env=env,
        )
        assert sort_process.stdout is not None
        sort_process.stdout.close()
        if find_process.wait() != 0 or sort_process.wait() != 0:
            raise HashImportError(f"failed to compute directory hash for {directory}")
    except OSError as exc:
        raise HashImportError(f"failed to compute directory hash for {directory}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise HashImportError(f"failed to compute directory hash for {directory}: {exc}") from exc

    stdout = sha1sum_process.stdout.decode("utf-8", errors="strict").strip()
    if not stdout:
        raise HashImportError(f"failed to compute directory hash for {directory}: empty sha1sum output")
    return stdout.split()[0]


def _sha1_file(path: Path, chunk_size: int = 64 * 1024) -> str:
    """Return SHA-1 for one file using streaming reads."""

    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()