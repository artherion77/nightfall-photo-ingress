"""Integration coverage for sync-import from a read-only permanent library."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from nightfall_photo_ingress.sync_import import EXTERNAL_HASH_CACHE_SCOPE, run_sync_import


def test_sync_import_nested_read_only_library_with_fallback_rehash(
    app_config_fixture,
    registry_fixture,
    tmp_path: Path,
) -> None:
    config = app_config_fixture(
        core_overrides={
            "registry_path": registry_fixture.db_path,
            "sync_hash_import_path": tmp_path / "pictures",
        }
    )
    library_root = config.core.sync_hash_import_path
    dir_a = library_root / "2026" / "04"
    dir_b = library_root / "2026" / "05"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)

    file_a = dir_a / "A.HEIC"
    file_b = dir_b / "B.HEIC"
    file_a.write_bytes(b"alpha")
    file_b.write_bytes(b"beta")

    # Valid cache in one directory, missing cache in the other.
    (dir_a / ".hashes.sha1").write_text(
        "\n".join(
            [
                "DIRECTORY_HASH 0123456789012345678901234567890123456789",
                "be76331b95dfc399cd776d2fc68021e0db03cc4f  " + str(file_a),
            ]
        ),
        encoding="utf-8",
    )

    summary = run_sync_import(config, dry_run=False)

    assert summary.cache_files_used == 1
    assert summary.directories_rehashed >= 1
    assert summary.imported_rows == 2
    assert not (dir_b / ".hashes.sha1").exists()

    conn = sqlite3.connect(registry_fixture.db_path)
    try:
        rows = conn.execute(
            """
            SELECT account_name, source_relpath, hash_algo
            FROM external_hash_cache
            ORDER BY source_relpath
            """
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        (EXTERNAL_HASH_CACHE_SCOPE, "2026/04/A.HEIC", "sha1"),
        (EXTERNAL_HASH_CACHE_SCOPE, "2026/05/B.HEIC", "sha1"),
    ]
