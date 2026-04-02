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
config_version = 2
poll_interval_minutes = 720
process_accounts_in_config_order = true
staging_path = {tmp_path / 'staging'}
pending_path = {tmp_path / 'pending'}
accepted_path = {tmp_path / 'accepted'}
accepted_storage_template = {{yyyy}}/{{mm}}/{{original}}
rejected_path = {tmp_path / 'rejected'}
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
    assert row.current_path is not None
    assert Path(row.current_path).exists()
    assert str(Path(row.current_path).parent).startswith(str(tmp_path / "rejected"))
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
    assert known_row.current_path is not None
    assert Path(known_row.current_path).exists()

    unknown_sha = _sha256_bytes(b"unknown")
    unknown_row = registry.get_file(sha256=unknown_sha)
    assert unknown_row is not None
    assert unknown_row.status == "rejected"
    assert unknown_row.current_path is not None
    assert Path(unknown_row.current_path).exists()
    assert str(Path(unknown_row.current_path)).startswith(str(tmp_path / "rejected"))

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


def test_cli_accept_moves_pending_and_records_acceptance(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    pending_root = tmp_path / "pending"
    pending_root.mkdir(parents=True)
    pending_file = pending_root / "2026" / "04" / "IMG_PENDING.HEIC"
    pending_file.parent.mkdir(parents=True)
    pending_file.write_bytes(b"pending-payload")

    sha = _sha256_bytes(b"pending-payload")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"pending-payload"),
        status="pending",
        original_filename="IMG_PENDING.HEIC",
        current_path=str(pending_file),
    )
    registry.upsert_metadata_index(
        account="primary",
        onedrive_id="item-pending-1",
        size_bytes=len(b"pending-payload"),
        modified_time="2026-04-01T10:11:12+00:00",
        sha256=sha,
    )
    registry.upsert_file_origin(
        sha256=sha,
        account="primary",
        onedrive_id="item-pending-1",
        path_hint="/Camera Roll/2026",
    )

    exit_code = cli.main(["accept", sha, "--reason", "operator_accept", "--path", str(cfg)])
    assert exit_code == 0

    row = registry.get_file(sha256=sha)
    assert row is not None
    assert row.status == "accepted"
    assert row.current_path is not None
    assert Path(row.current_path).exists()
    assert str(Path(row.current_path)).startswith(str(tmp_path / "accepted"))
    assert not pending_file.exists()
    assert registry.acceptance_count(sha256=sha) == 1


def test_cli_accept_requires_origin_context(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    pending_root = tmp_path / "pending"
    pending_root.mkdir(parents=True)
    pending_file = pending_root / "IMG_PENDING_MISSING_CTX.HEIC"
    pending_file.write_bytes(b"pending-missing-ctx")

    sha = _sha256_bytes(b"pending-missing-ctx")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"pending-missing-ctx"),
        status="pending",
        original_filename="IMG_PENDING_MISSING_CTX.HEIC",
        current_path=str(pending_file),
    )

    exit_code = cli.main(["accept", sha, "--path", str(cfg)])
    assert exit_code == 2
    assert pending_file.exists()


def test_cli_purge_rejects_path_outside_rejected_root(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    outside = tmp_path / "outside" / "bad.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"outside")

    sha = _sha256_bytes(b"outside")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"outside"),
        status="rejected",
        original_filename="bad.bin",
        current_path=str(outside),
    )

    exit_code = cli.main(["purge", sha, "--path", str(cfg)])
    assert exit_code == 2
    assert outside.exists()
    row = registry.get_file(sha256=sha)
    assert row is not None
    assert row.status == "rejected"


def test_cli_purge_allows_missing_rejected_file_path(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    stale = tmp_path / "rejected" / "stale.bin"
    stale.parent.mkdir(parents=True)

    sha = _sha256_bytes(b"stale")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"stale"),
        status="rejected",
        original_filename="stale.bin",
        current_path=str(stale),
    )

    exit_code = cli.main(["purge", sha, "--path", str(cfg)])
    assert exit_code == 0
    row = registry.get_file(sha256=sha)
    assert row is not None
    assert row.status == "purged"
    assert row.current_path is None


def test_cli_accept_rejects_source_outside_pending_root(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    outside = tmp_path / "outside" / "pending.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"outside-pending")

    sha = _sha256_bytes(b"outside-pending")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"outside-pending"),
        status="pending",
        original_filename="pending.bin",
        current_path=str(outside),
    )
    registry.upsert_metadata_index(
        account="primary",
        onedrive_id="item-outside-pending",
        size_bytes=len(b"outside-pending"),
        modified_time="2026-04-01T10:11:12+00:00",
        sha256=sha,
    )
    registry.upsert_file_origin(
        sha256=sha,
        account="primary",
        onedrive_id="item-outside-pending",
        path_hint="/Camera Roll/2026",
    )

    exit_code = cli.main(["accept", sha, "--path", str(cfg)])
    assert exit_code == 2
    assert outside.exists()


def test_cli_reject_rejects_source_outside_managed_queue_roots(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    outside = tmp_path / "outside" / "accepted.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"outside-accepted")

    sha = _sha256_bytes(b"outside-accepted")
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.create_or_update_file(
        sha256=sha,
        size_bytes=len(b"outside-accepted"),
        status="accepted",
        original_filename="accepted.bin",
        current_path=str(outside),
    )

    exit_code = cli.main(["reject", sha, "--path", str(cfg)])
    assert exit_code == 2
    assert outside.exists()
    row = registry.get_file(sha256=sha)
    assert row is not None
    assert row.status == "accepted"
