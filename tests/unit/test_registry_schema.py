"""Schema and migration tests for Module 2 registry."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from nightfall_photo_ingress.domain.registry import LATEST_SCHEMA_VERSION, Registry


def _table_names(db_path: Path) -> set[str]:
    """Return user table names from SQLite for assertions."""

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def test_initialize_fresh_database_creates_expected_schema(tmp_path: Path) -> None:
    """Fresh initialization should create all required Module 2 tables."""

    db_path = tmp_path / "registry.db"
    registry = Registry(db_path)

    registry.initialize()

    tables = _table_names(db_path)
    assert {
        "files",
        "metadata_index",
        "accepted_records",
        "file_origins",
        "audit_log",
        "live_photo_pairs",
        "external_hash_cache",
    }.issubset(tables)
    assert registry.schema_version() == LATEST_SCHEMA_VERSION


def test_canonical_v2_columns_present(tmp_path: Path) -> None:
    """Canonical v2 column names should exist for files and metadata_index."""

    db_path = tmp_path / "registry.db"
    registry = Registry(db_path)
    registry.initialize()

    conn = sqlite3.connect(db_path)
    try:
        files_cols = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        metadata_cols = {row[1] for row in conn.execute("PRAGMA table_info(metadata_index)").fetchall()}
        audit_cols = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
    finally:
        conn.close()

    assert "first_seen_at" in files_cols
    assert "account_name" in metadata_cols
    assert {"sha256", "account_name", "details_json"}.issubset(audit_cols)


def test_external_hash_cache_supports_null_source_relpath_for_hash_import(tmp_path: Path) -> None:
    """H1 schema allows source_relpath NULL for hash-import rows."""

    db_path = tmp_path / "registry.db"
    registry = Registry(db_path)
    registry.initialize()

    conn = sqlite3.connect(db_path)
    try:
        cols = conn.execute("PRAGMA table_info(external_hash_cache)").fetchall()
        source = next(row for row in cols if row[1] == "source_relpath")
        # PRAGMA table_info: row[3] is notnull flag.
        assert int(source[3]) == 0

        indexes = conn.execute("PRAGMA index_list(external_hash_cache)").fetchall()
        index_names = {row[1] for row in indexes}
    finally:
        conn.close()

    assert "idx_external_hash_cache_hash_import_unique" in index_names


def test_migration_is_idempotent_on_repeated_initialize(tmp_path: Path) -> None:
    """Running initialization repeatedly should preserve schema version and data."""

    db_path = tmp_path / "registry.db"
    registry = Registry(db_path)

    registry.initialize()
    registry.create_or_update_file(
        sha256="a" * 64,
        size_bytes=123,
        status="accepted",
        original_filename="x.heic",
        current_path="/queue/x.heic",
    )

    registry.initialize()

    row = registry.get_file(sha256="a" * 64)
    assert row is not None
    assert row.size_bytes == 123
    assert registry.schema_version() == LATEST_SCHEMA_VERSION


def test_legacy_v1_registry_is_rejected(tmp_path: Path) -> None:
    """v2 runtime must fail closed on legacy registry schemas."""

    db_path = tmp_path / "registry.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()

    registry = Registry(db_path)

    try:
        registry.initialize()
    except Exception as exc:
        assert "Legacy registry schema detected" in str(exc)
    else:
        raise AssertionError("Expected initialize() to reject legacy schema version 1")
