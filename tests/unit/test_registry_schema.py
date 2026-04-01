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


def test_canonical_v1_columns_present(tmp_path: Path) -> None:
    """Canonical V1 column names should exist for files and metadata_index."""

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
