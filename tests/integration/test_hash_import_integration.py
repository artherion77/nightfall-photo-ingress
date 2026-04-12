"""Integration coverage for recursive hash-import tree walking."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from nightfall_photo_ingress.domain.registry import HASH_IMPORT_ACCOUNT, Registry
from nightfall_photo_ingress.hash_import import HASHFILE_V2_NAME, _compute_directory_hash, run_hash_import


def _sha1_bytes(value: bytes) -> str:
    return hashlib.sha1(value).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_valid_v2(directory: Path, file_path: Path) -> None:
    (directory / HASHFILE_V2_NAME).write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                f"DIRECTORY_HASH {_compute_directory_hash(directory)}",
                f"{_sha1_bytes(file_path.read_bytes())}\t{_sha256_bytes(file_path.read_bytes())}\t{file_path}",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_v1(directory: Path, file_path: Path) -> None:
    (directory / ".hashes.sha1").write_text(
        "\n".join(
            [
                f"DIRECTORY_HASH {_compute_directory_hash(directory)}",
                f"{_sha1_bytes(file_path.read_bytes())}  {file_path}",
            ]
        ),
        encoding="utf-8",
    )


def test_run_hash_import_walks_tree_with_valid_stale_and_v1_backfill_dirs(tmp_path: Path) -> None:
    root = tmp_path / "pictures"
    dir_a = root / "2026" / "04"
    dir_b = root / "2026" / "05"
    dir_c = root / "2026" / "06"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)
    dir_c.mkdir(parents=True)

    file_a = dir_a / "A.HEIC"
    file_b = dir_b / "B.HEIC"
    file_c = dir_c / "C.HEIC"
    file_a.write_bytes(b"alpha")
    file_b.write_bytes(b"beta")
    file_c.write_bytes(b"gamma")

    _write_valid_v2(dir_a, file_a)
    (dir_b / HASHFILE_V2_NAME).write_text(
        "\n".join(
            [
                "CACHE_SCHEMA v2",
                "DIRECTORY_HASH 0000000000000000000000000000000000000000",
                f"{_sha1_bytes(b'beta')}\t{_sha256_bytes(b'beta')}\t{file_b}",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_v1(dir_c, file_c)

    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    summary = run_hash_import(root_path=root, registry=registry, chunk_size=2)

    assert summary.directories_processed == 3
    assert summary.valid_caches_consumed == 1
    assert summary.recomputes_performed == 2
    assert summary.stale_invalid_caches_replaced == 1
    assert summary.total_imported == 3
    assert summary.total_skipped == 0
    assert [result.imported for result in summary.chunk_results] == [2, 1]

    conn = sqlite3.connect(registry.db_path)
    try:
        rows = conn.execute(
            """
            SELECT account_name, source_relpath, hash_algo, hash_value, verified_sha256
            FROM external_hash_cache
            ORDER BY hash_value
            """
        ).fetchall()
    finally:
        conn.close()

    expected_hashes = sorted(
        [_sha256_bytes(b"alpha"), _sha256_bytes(b"beta"), _sha256_bytes(b"gamma")]
    )
    assert rows == [
        (HASH_IMPORT_ACCOUNT, None, "sha256", hash_value, hash_value)
        for hash_value in expected_hashes
    ]
    assert not (dir_c / HASHFILE_V2_NAME).exists()