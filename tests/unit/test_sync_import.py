"""Sync-import parser and import workflow tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nightfall_photo_ingress.config import AccountConfig, AppConfig, CoreConfig, LoggingConfig
from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.sync_import import (
    EXTERNAL_HASH_CACHE_SCOPE,
    build_directory_import_plan,
    run_sync_import,
)


def _sha1_bytes(value: bytes) -> str:
    return hashlib.sha1(value).hexdigest()


def _make_app_config(tmp_path: Path) -> AppConfig:
    registry_path = tmp_path / "registry.db"
    library_root = tmp_path / "pictures"
    account = AccountConfig(
        name="primary",
        enabled=True,
        display_name="primary",
        provider="onedrive",
        authority="https://login.microsoftonline.com/consumers",
        client_id="cid-primary",
        onedrive_root="/Camera Roll",
        token_cache=tmp_path / "token.json",
        delta_cursor=tmp_path / "cursor.txt",
        max_downloads=10,
    )
    core = CoreConfig(
        config_version=2,
        poll_interval_minutes=720,
        process_accounts_in_config_order=True,
        staging_path=tmp_path / "staging",
        pending_path=tmp_path / "pending",
        accepted_path=tmp_path / "accepted",
        accepted_storage_template="{yyyy}/{mm}/{original}",
        rejected_path=tmp_path / "rejected",
        trash_path=tmp_path / "trash",
        registry_path=registry_path,
        staging_on_same_pool=False,
        storage_template="{yyyy}/{mm}/{original}",
        verify_sha256_on_first_download=True,
        max_downloads_per_poll=100,
        max_poll_runtime_seconds=300,
        tmp_ttl_minutes=120,
        failed_ttl_hours=24,
        orphan_ttl_days=7,
        live_photo_capture_tolerance_seconds=3,
        live_photo_stem_mode="exact_stem",
        live_photo_component_order="photo_first",
        live_photo_conflict_policy="nearest_capture_time",
        sync_hash_import_enabled=True,
        sync_hash_import_path=library_root,
        sync_hash_import_glob=".hashes.sha1",
    )
    return AppConfig(
        source_path=tmp_path / "photo-ingress.conf",
        core=core,
        logging=LoggingConfig(log_level="INFO", console_format="json"),
        accounts=(account,),
    )


def test_build_directory_import_plan_uses_valid_hash_cache(tmp_path: Path) -> None:
    library_root = tmp_path / "pictures"
    target_dir = library_root / "2026" / "04"
    target_dir.mkdir(parents=True)
    file_path = target_dir / "IMG 1.HEIC"
    file_path.write_bytes(b"abc")
    (target_dir / ".hashes.sha1").write_text(
        "\n".join(
            [
                "DIRECTORY_HASH 0123456789012345678901234567890123456789",
                f"{_sha1_bytes(b'abc')}  {file_path}",
            ]
        ),
        encoding="utf-8",
    )

    plan = build_directory_import_plan(
        library_root=library_root,
        directory=target_dir,
        hash_glob=".hashes.sha1",
    )

    assert plan.source == "cache"
    assert plan.invalid_line_count == 0
    assert plan.entries[0].source_relpath == "2026/04/IMG 1.HEIC"
    assert plan.entries[0].sha1 == _sha1_bytes(b"abc")


def test_build_directory_import_plan_rehashes_when_cache_invalid(tmp_path: Path) -> None:
    library_root = tmp_path / "pictures"
    target_dir = library_root / "2026" / "04"
    target_dir.mkdir(parents=True)
    file_path = target_dir / "IMG_2.HEIC"
    file_path.write_bytes(b"payload")
    (target_dir / ".hashes.sha1").write_text(
        "DIRECTORY_HASH not-a-hash\nthis is invalid\n",
        encoding="utf-8",
    )

    plan = build_directory_import_plan(
        library_root=library_root,
        directory=target_dir,
        hash_glob=".hashes.sha1",
    )

    assert plan.source == "rehash"
    assert plan.invalid_line_count >= 1
    assert plan.entries == (
        type(plan.entries[0])(
            source_relpath="2026/04/IMG_2.HEIC",
            sha1=_sha1_bytes(b"payload"),
        ),
    )


def test_build_directory_import_plan_rehashes_when_cache_missing_file(tmp_path: Path) -> None:
    library_root = tmp_path / "pictures"
    target_dir = library_root / "2026" / "04"
    target_dir.mkdir(parents=True)
    file_path = target_dir / "IMG_3.HEIC"
    file_path.write_bytes(b"fresh")
    stale_path = target_dir / "MISSING.HEIC"
    (target_dir / ".hashes.sha1").write_text(
        "\n".join(
            [
                "DIRECTORY_HASH 0123456789012345678901234567890123456789",
                f"{_sha1_bytes(b'stale')}  {stale_path}",
            ]
        ),
        encoding="utf-8",
    )

    plan = build_directory_import_plan(
        library_root=library_root,
        directory=target_dir,
        hash_glob=".hashes.sha1",
    )

    assert plan.source == "rehash"
    assert plan.invalid_line_count >= 1
    assert [entry.source_relpath for entry in plan.entries] == ["2026/04/IMG_3.HEIC"]


def test_run_sync_import_dry_run_reports_without_writing_rows(tmp_path: Path) -> None:
    app_config = _make_app_config(tmp_path)
    target_dir = app_config.core.sync_hash_import_path / "2026" / "04"
    target_dir.mkdir(parents=True)
    file_path = target_dir / "IMG_4.HEIC"
    file_path.write_bytes(b"hello")

    summary = run_sync_import(app_config, dry_run=True)

    assert summary.dry_run is True
    assert summary.imported_rows == 1
    registry = Registry(app_config.core.registry_path)
    registry.initialize()
    with registry._connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM external_hash_cache").fetchone()
    assert int(row[0]) == 0


def test_run_sync_import_writes_rows_and_is_idempotent(tmp_path: Path) -> None:
    app_config = _make_app_config(tmp_path)
    target_dir = app_config.core.sync_hash_import_path / "albums"
    target_dir.mkdir(parents=True)
    first = target_dir / "A.HEIC"
    second = target_dir / "B.HEIC"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    first_summary = run_sync_import(app_config, dry_run=False)
    second_summary = run_sync_import(app_config, dry_run=False)

    assert first_summary.imported_rows == 2
    assert second_summary.imported_rows == 0
    assert second_summary.skipped_rows == 2

    registry = Registry(app_config.core.registry_path)
    registry.initialize()
    with registry._connect() as conn:
        rows = conn.execute(
            """
            SELECT account_name, source_relpath, hash_algo, hash_value, verified_sha256
            FROM external_hash_cache
            ORDER BY source_relpath
            """
        ).fetchall()
        audit_rows = conn.execute(
            "SELECT action, account_name, details_json FROM audit_log ORDER BY id"
        ).fetchall()

    assert [(row[0], row[1], row[2]) for row in rows] == [
        (EXTERNAL_HASH_CACHE_SCOPE, "albums/A.HEIC", "sha1"),
        (EXTERNAL_HASH_CACHE_SCOPE, "albums/B.HEIC", "sha1"),
    ]
    assert all(row[4] is None for row in rows)
    assert [row[0] for row in audit_rows] == ["sync_import", "sync_import"]
    assert all(row[1] == EXTERNAL_HASH_CACHE_SCOPE for row in audit_rows)
    details = [json.loads(row[2]) for row in audit_rows]
    assert details == [
        {"hash_algo": "sha1", "source_relpath": "albums/A.HEIC"},
        {"hash_algo": "sha1", "source_relpath": "albums/B.HEIC"},
    ]
