"""Parser tests for the hash-import `.hashes.v2` format."""

from __future__ import annotations

import io
import hashlib
import os
import subprocess
import json
import logging
import sqlite3
from pathlib import Path

import pytest

from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.hash_import import (
    HASHFILE_V2_NAME,
    HashImportError,
    HashImportParseError,
    build_hash_import_directory_plan,
    format_hash_import_error,
    parse_hashes_v2_file,
    parse_hashes_v2_text,
    run_hash_import,
    run_hash_import_command,
    _compute_directory_hash,
    _parse_hashes_v1_cache,
    _parse_hashes_v2_cache,
    _sha1_file,
)
from nightfall_photo_ingress.logging_bootstrap import JsonFormatter


def _sha1_bytes(value: bytes) -> str:
    return hashlib.sha1(value).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_valid_v2(directory: Path, *, files: list[Path]) -> None:
    directory_hash = _compute_directory_hash(directory)
    rows = [f"{_sha1_bytes(path.read_bytes())}\t{_sha256_bytes(path.read_bytes())}\t{path}" for path in files]
    (directory / HASHFILE_V2_NAME).write_text(
        "\n".join(["CACHE_SCHEMA v2", f"DIRECTORY_HASH {directory_hash}", *rows]),
        encoding="utf-8",
    )


def _write_valid_v1(directory: Path, *, files: list[Path]) -> None:
    directory_hash = _compute_directory_hash(directory)
    rows = [f"{_sha1_bytes(path.read_bytes())}  {path}" for path in files]
    (directory / ".hashes.sha1").write_text(
        "\n".join([f"DIRECTORY_HASH {directory_hash}", *rows]),
        encoding="utf-8",
    )


def test_parse_hashes_v2_text_returns_sha256_values_in_order() -> None:
    parsed = parse_hashes_v2_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t/library/A.HEIC",
                "fedcba9876543210fedcba9876543210fedcba98\tBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\t/library/B.HEIC",
            ]
        ),
        source="fixture.hashes.v2",
    )

    assert parsed == (
        "a" * 64,
        "b" * 64,
    )


def test_parse_hashes_v2_file_reads_from_disk(tmp_path: Path) -> None:
    cache_path = tmp_path / ".hashes.v2"
    cache_path.write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t/library/A.HEIC",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_hashes_v2_file(cache_path) == ("a" * 64,)


def test_parse_hashes_v2_text_rejects_missing_header() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 1: expected exact header 'CACHE_SCHEMA v2'"):
        parse_hashes_v2_text(
            "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567\n",
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_file_rejects_unreadable_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.hashes.v2"

    with pytest.raises(HashImportParseError, match=r"missing\.hashes\.v2: line 0: unable to read file"):
        parse_hashes_v2_file(missing)


def test_parse_hashes_v2_text_rejects_invalid_directory_hash_header() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 2: invalid DIRECTORY_HASH header"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH not-a-hash",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_rejects_invalid_sha256_with_line_number() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: invalid SHA-256 value in column 2"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\tnot-a-sha256\t/library/A.HEIC",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_rejects_rows_with_fewer_than_three_fields() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: expected exactly 3 tab-separated fields"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_parse_hashes_v2_text_allows_header_only_file() -> None:
    assert parse_hashes_v2_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
            ]
        ),
        source="fixture.hashes.v2",
    ) == ()


def test_parse_hashes_v2_text_rejects_empty_path() -> None:
    with pytest.raises(HashImportParseError, match=r"fixture\.hashes\.v2: line 3: empty path in column 3"):
        parse_hashes_v2_text(
            "\n".join(
                [
                    "CACHE_SCHEMA v2",
                    "DIRECTORY_HASH 0123456789abcdef0123456789abcdef01234567",
                    "0123456789abcdef0123456789abcdef01234567\taaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\t",
                ]
            ),
            source="fixture.hashes.v2",
        )


def test_compute_directory_hash_matches_script_contract(tmp_path: Path) -> None:
    directory = tmp_path / "library"
    directory.mkdir()
    first = directory / "A.HEIC"
    second = directory / "B.HEIC"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    (directory / ".hashes.sha1").write_text("ignored", encoding="utf-8")
    (directory / ".hashes.v2").write_text("ignored", encoding="utf-8")
    (directory / "Thumbs.DB").write_text("ignored", encoding="utf-8")

    os.utime(first, ns=(1_710_000_000_123_456_789, 1_710_000_000_123_456_789))
    os.utime(second, ns=(1_710_000_100_987_654_321, 1_710_000_100_987_654_321))

    expected = subprocess.run(
        [
            "bash",
            "-lc",
            (
                "find \"$1\" -maxdepth 1 -type f "
                "! -name '.hashes.sha1' ! -name '.hashes.v1' ! -name '.hashes.v2' ! -iname 'thumbs.db' "
                "-printf '%f %s %T@\\n' | LC_ALL=C sort | sha1sum | awk '{print $1}'"
            ),
            "bash",
            str(directory),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert _compute_directory_hash(directory) == expected


def test_build_hash_import_directory_plan_uses_valid_v2_cache(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "04"
    directory.mkdir(parents=True)
    file_path = directory / "A.HEIC"
    file_path.write_bytes(b"alpha")
    _write_valid_v2(directory, files=[file_path])

    plan = build_hash_import_directory_plan(root_path=root, directory=directory)

    assert plan.source == "cache_v2"
    assert plan.stale_or_invalid_cache_replaced is False
    assert plan.sha256_values == (_sha256_bytes(b"alpha"),)
    assert not (directory / ".hashes.sha1").exists()


def test_build_hash_import_directory_plan_recomputes_stale_v2_without_writing_cache(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "05"
    directory.mkdir(parents=True)
    file_path = directory / "B.HEIC"
    file_path.write_bytes(b"beta")
    (directory / ".hashes.v2").write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0000000000000000000000000000000000000000",
                f"{_sha1_bytes(b'beta')}\t{_sha256_bytes(b'beta')}\t{file_path}",
            ]
        ),
        encoding="utf-8",
    )

    original_text = (directory / ".hashes.v2").read_text(encoding="utf-8")
    plan = build_hash_import_directory_plan(root_path=root, directory=directory)

    assert plan.source == "recompute"
    assert plan.stale_or_invalid_cache_replaced is True
    assert plan.sha256_values == (_sha256_bytes(b"beta"),)
    assert (directory / ".hashes.v2").read_text(encoding="utf-8") == original_text
    assert not (directory / ".hashes.sha1").exists()


def test_build_hash_import_directory_plan_backfills_from_current_v1_without_writing_v2(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "06"
    directory.mkdir(parents=True)
    file_path = directory / "C.HEIC"
    file_path.write_bytes(b"gamma")
    _write_valid_v1(directory, files=[file_path])

    plan = build_hash_import_directory_plan(root_path=root, directory=directory)

    assert plan.source == "backfill_v1"
    assert plan.stale_or_invalid_cache_replaced is False
    assert plan.sha256_values == (_sha256_bytes(b"gamma"),)
    assert not (directory / ".hashes.v2").exists()


def test_run_hash_import_recomputes_missing_cache_without_writing_files(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "07"
    directory.mkdir(parents=True)
    (directory / "D.HEIC").write_bytes(b"delta")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()

    summary = run_hash_import(root_path=root, registry=registry, chunk_size=1000)

    assert summary.directories_processed == 1
    assert summary.recomputes_performed == 1
    assert summary.valid_caches_consumed == 0
    assert summary.stale_invalid_caches_replaced == 0
    assert summary.total_imported == 1
    assert summary.total_skipped == 0
    assert not (directory / ".hashes.v2").exists()
    assert not (directory / ".hashes.sha1").exists()


def test_run_hash_import_on_empty_tree_returns_zero_stats(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    root.mkdir()
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()

    summary = run_hash_import(root_path=root, registry=registry, chunk_size=1000)

    assert summary.directories_processed == 0
    assert summary.recomputes_performed == 0
    assert summary.valid_caches_consumed == 0
    assert summary.total_imported == 0
    assert summary.total_skipped == 0


def test_run_hash_import_rejects_missing_root(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()

    with pytest.raises(HashImportError, match="hash-import root does not exist"):
        run_hash_import(root_path=tmp_path / "missing", registry=registry, chunk_size=1000)


def test_run_hash_import_rejects_file_root(tmp_path: Path) -> None:
    root_file = tmp_path / "not-a-dir"
    root_file.write_text("x", encoding="utf-8")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()

    with pytest.raises(HashImportError, match="hash-import root is not a directory"):
        run_hash_import(root_path=root_file, registry=registry, chunk_size=1000)


def test_build_hash_import_directory_plan_supports_hashes_v1_filename(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "08"
    directory.mkdir(parents=True)
    file_path = directory / "E.HEIC"
    file_path.write_bytes(b"epsilon")
    directory_hash = _compute_directory_hash(directory)
    (directory / ".hashes.v1").write_text(
        "\n".join([f"DIRECTORY_HASH {directory_hash}", f"{_sha1_bytes(b'epsilon')}  {file_path}"]),
        encoding="utf-8",
    )

    plan = build_hash_import_directory_plan(root_path=root, directory=directory)

    assert plan.source == "backfill_v1"
    assert plan.sha256_values == (_sha256_bytes(b"epsilon"),)


def test_build_hash_import_directory_plan_recomputes_when_v1_cache_is_invalid(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "08-invalid"
    directory.mkdir(parents=True)
    file_path = directory / "E2.HEIC"
    file_path.write_bytes(b"epsilon-2")
    (directory / ".hashes.sha1").write_text("not-a-valid-cache\n", encoding="utf-8")

    plan = build_hash_import_directory_plan(root_path=root, directory=directory)

    assert plan.source == "recompute"
    assert plan.stale_or_invalid_cache_replaced is True
    assert plan.sha256_values == (_sha256_bytes(b"epsilon-2"),)


def test_parse_hashes_v2_cache_rejects_relative_path(tmp_path: Path) -> None:
    directory = tmp_path / "2026" / "09"
    directory.mkdir(parents=True)
    file_path = directory / "F.HEIC"
    file_path.write_bytes(b"phi")
    cache_path = directory / ".hashes.v2"
    cache_path.write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                f"DIRECTORY_HASH {_compute_directory_hash(directory)}",
                f"{_sha1_bytes(b'phi')}\t{_sha256_bytes(b'phi')}\tF.HEIC",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(HashImportParseError, match=r"line 3: path must be absolute"):
        _parse_hashes_v2_cache(
            cache_path=cache_path,
            directory=directory,
            expected_directory_hash=_compute_directory_hash(directory),
        )


def test_parse_hashes_v1_cache_rejects_path_outside_directory(tmp_path: Path) -> None:
    directory = tmp_path / "2026" / "10"
    directory.mkdir(parents=True)
    file_path = directory / "G.HEIC"
    file_path.write_bytes(b"gamma-2")
    other_dir = tmp_path / "outside"
    other_dir.mkdir()
    outside_path = other_dir / "OUTSIDE.HEIC"
    outside_path.write_bytes(b"x")
    cache_path = directory / ".hashes.sha1"
    cache_path.write_text(
        "\n".join(
            [
                f"DIRECTORY_HASH {_compute_directory_hash(directory)}",
                f"{_sha1_bytes(b'x')}  {outside_path}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(HashImportParseError, match=r"line 2: path must belong to cache directory"):
        _parse_hashes_v1_cache(
            cache_path=cache_path,
            directory=directory,
            expected_directory_hash=_compute_directory_hash(directory),
        )


def test_sha1_file_hashes_streamed_content(tmp_path: Path) -> None:
    file_path = tmp_path / "stream.bin"
    file_path.write_bytes(b"streamed-content")

    assert _sha1_file(file_path) == _sha1_bytes(b"streamed-content")


def test_run_hash_import_command_standard_output_renders_chunks_and_done(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    first_dir = root / "2026" / "11"
    second_dir = root / "2026" / "12"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first_file = first_dir / "A.HEIC"
    second_file = second_dir / "B.HEIC"
    first_file.write_bytes(b"alpha")
    second_file.write_bytes(b"beta")

    _write_valid_v2(first_dir, files=[first_file])
    _write_valid_v2(second_dir, files=[second_file])

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    out = io.StringIO()

    summary = run_hash_import_command(
        root_path=root,
        registry=registry,
        chunk_size=1,
        dry_run=False,
        quiet=False,
        stats=False,
        out=out,
    )

    rendered = out.getvalue().strip().splitlines()
    assert rendered[0].startswith("[chunk 1] imported=1 skipped_existing=0 duration=")
    assert rendered[1].startswith("[chunk 2] imported=1 skipped_existing=0 duration=")
    assert rendered[2] == "DONE: total_imported=2 total_skipped=0"
    assert summary.total_imported == 2


def test_run_hash_import_command_dry_run_prints_summary_without_db_writes(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "13"
    directory.mkdir(parents=True)
    file_path = directory / "C.HEIC"
    file_path.write_bytes(b"gamma")
    _write_valid_v2(directory, files=[file_path])

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    out = io.StringIO()

    summary = run_hash_import_command(
        root_path=root,
        registry=registry,
        chunk_size=1000,
        dry_run=True,
        quiet=False,
        stats=False,
        out=out,
    )

    assert out.getvalue().strip() == "DRY RUN: total=1 new=1 existing=0"
    assert summary.total_imported == 1
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM external_hash_cache").fetchone()[0] == 0


def test_run_hash_import_command_quiet_mode_suppresses_non_error_output(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "14"
    directory.mkdir(parents=True)
    file_path = directory / "D.HEIC"
    file_path.write_bytes(b"delta")
    _write_valid_v2(directory, files=[file_path])

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    out = io.StringIO()

    run_hash_import_command(
        root_path=root,
        registry=registry,
        chunk_size=1000,
        dry_run=False,
        quiet=True,
        stats=True,
        out=out,
    )

    assert out.getvalue() == ""


def test_run_hash_import_command_stats_mode_includes_recompute_aware_counters(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    valid_dir = root / "2026" / "15"
    stale_dir = root / "2026" / "16"
    valid_dir.mkdir(parents=True)
    stale_dir.mkdir(parents=True)
    valid_file = valid_dir / "A.HEIC"
    stale_file = stale_dir / "B.HEIC"
    valid_file.write_bytes(b"alpha")
    stale_file.write_bytes(b"beta")
    _write_valid_v2(valid_dir, files=[valid_file])
    (stale_dir / ".hashes.v2").write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0000000000000000000000000000000000000000",
                f"{_sha1_bytes(b'beta')}\t{_sha256_bytes(b'beta')}\t{stale_file}",
            ]
        ),
        encoding="utf-8",
    )

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    out = io.StringIO()

    run_hash_import_command(
        root_path=root,
        registry=registry,
        chunk_size=1000,
        dry_run=True,
        quiet=False,
        stats=True,
        out=out,
    )

    rendered = out.getvalue().strip().splitlines()
    assert rendered[0] == "DRY RUN: total=2 new=2 existing=0"
    assert rendered[1].startswith("[chunk 1] imported=2 skipped_existing=0 duration=")
    assert rendered[2] == (
        "STATS: directories_processed=2 recomputes_performed=1 "
        "valid_caches_consumed=1 stale_invalid_caches_replaced=1"
    )


def test_run_hash_import_command_emits_structured_json_log_fields(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    directory = root / "2026" / "17"
    directory.mkdir(parents=True)
    file_path = directory / "E.HEIC"
    file_path.write_bytes(b"epsilon")
    _write_valid_v2(directory, files=[file_path])

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.hash_import.command")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        run_hash_import_command(
            root_path=root,
            registry=registry,
            chunk_size=1000,
            dry_run=False,
            quiet=True,
            stats=False,
            logger=logger,
        )
    finally:
        logger.handlers.clear()

    payloads = [json.loads(line) for line in log_stream.getvalue().strip().splitlines()]
    assert len(payloads) == 2
    assert payloads[0]["command"] == "hash-import"
    assert payloads[0]["chunk_index"] == 1
    assert payloads[0]["imported"] == 1
    assert payloads[0]["skipped_existing"] == 0
    assert isinstance(payloads[0]["duration"], float)
    assert payloads[1]["chunk_index"] == 0
    assert payloads[1]["directories_processed"] == 1


def test_format_hash_import_error_includes_file_and_line_context() -> None:
    message = format_hash_import_error(HashImportParseError("/tmp/example.hashes.v2", 42, "invalid SHA-256"))

    assert message == "ERROR: /tmp/example.hashes.v2: line 42: invalid SHA-256"