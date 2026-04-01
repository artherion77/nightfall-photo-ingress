"""Unit coverage for Module 7 reject and trash workflows."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from nightfall_photo_ingress import cli
from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.reject import process_trash


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "photo-ingress.conf"
    cfg.write_text(
        f"""
[core]
config_version = 1
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = {tmp_path / 'staging'}
accepted_path = {tmp_path / 'accepted'}
trash_path = {tmp_path / 'trash'}
registry_path = {tmp_path / 'registry.db'}
staging_on_same_pool = false
storage_template = {{yyyy}}/{{mm}}/{{original}}
verify_sha256_on_first_download = true
max_downloads_per_poll = 200
max_poll_runtime_seconds = 300
sync_hash_import_enabled = true
sync_hash_import_path = {tmp_path / 'pictures'}
sync_hash_import_glob = .hashes.sha1

[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = cid
onedrive_root = /Camera Roll
token_cache = {tmp_path / 'primary.token'}
delta_cursor = {tmp_path / 'primary.cursor'}
""".strip(),
        encoding="utf-8",
    )
    return cfg


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_cli_reject_is_idempotent_and_preserves_acceptance_history(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    accepted_root = tmp_path / "accepted"
    accepted_root.mkdir(parents=True)
    queue_file = accepted_root / "2026" / "04" / "IMG_1.HEIC"
    queue_file.parent.mkdir(parents=True)
    queue_file.write_bytes(b"accepted")

    sha = _sha256_bytes(b"accepted")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"accepted"),
        status="accepted",
        original_filename="IMG_1.HEIC",
        current_path=str(queue_file),
    )
    registry.record_acceptance(
        sha256=sha,
        account="primary",
        source_path="/Camera Roll/2026",
    )

    first_exit = cli.main(["reject", sha, "--reason", "operator", "--path", str(cfg)])
    second_exit = cli.main(["reject", sha, "--reason", "operator", "--path", str(cfg)])

    assert first_exit == 0
    assert second_exit == 0
    assert not queue_file.exists()

    row = registry.get_file(sha256=sha)
    assert row is not None
    assert row.status == "rejected"
    assert row.current_path is None
    assert registry.acceptance_count(sha256=sha) == 1
    actions = [event.action for event in registry.list_audit_events(sha256=sha)]
    assert actions == ["rejected", "reject_noop_already_rejected"]


def test_process_trash_rejects_known_and_unknown_files(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    accepted_root = tmp_path / "accepted"
    accepted_root.mkdir(parents=True)
    queue_file = accepted_root / "known.HEIC"
    queue_file.write_bytes(b"known")
    trash_root = tmp_path / "trash"
    trash_root.mkdir(parents=True)
    (trash_root / "known-copy.HEIC").write_bytes(b"known")
    (trash_root / "unknown.HEIC").write_bytes(b"unknown")

    known_sha = _sha256_bytes(b"known")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=known_sha,
        size_bytes=len(b"known"),
        status="accepted",
        original_filename="known.HEIC",
        current_path=str(queue_file),
    )

    app_exit = cli.main(["process-trash", "--path", str(cfg)])
    assert app_exit == 0
    assert not any(trash_root.rglob("*"))
    assert not queue_file.exists()

    known_row = registry.get_file(sha256=known_sha)
    assert known_row is not None
    assert known_row.status == "rejected"

    with sqlite3.connect(registry.db_path) as conn:
        rows = conn.execute("SELECT status FROM files").fetchall()
    assert len(rows) == 2
    assert all(row[0] == "rejected" for row in rows)


def test_process_trash_batch_summary_counts(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    trash_root = tmp_path / "trash"
    trash_root.mkdir(parents=True)
    (trash_root / "one.HEIC").write_bytes(b"one")
    (trash_root / "two.HEIC").write_bytes(b"two")

    from nightfall_photo_ingress.config import load_config

    summary = process_trash(load_config(cfg))

    assert summary.processed_files == 2
    assert summary.rejected_files == 2
    assert summary.noop_files == 0
    assert summary.unknown_files == 2
