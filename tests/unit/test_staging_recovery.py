"""Ingest pipeline integration tests for staging restart recovery behavior."""

from __future__ import annotations

import os
import time
from pathlib import Path

from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.domain.registry import Registry


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_synthetic_ingest_mixed_known_unknown_rejected(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    accepted_root = tmp_path / "accepted"
    staging_root = tmp_path / "staging" / "lisa"

    unknown_path = staging_root / "unknown.bin"
    known_rejected_path = staging_root / "rejected.bin"
    known_accepted_path = staging_root / "accepted.bin"

    _write(unknown_path, b"unknown-new")
    _write(known_rejected_path, b"already-rejected")
    _write(known_accepted_path, b"already-accepted")

    from nightfall_photo_ingress.domain.storage import sha256_file

    rejected_hash = sha256_file(known_rejected_path)
    accepted_hash = sha256_file(known_accepted_path)

    registry.create_or_update_file(
        sha256=rejected_hash,
        size_bytes=16,
        status="rejected",
        original_filename="rejected.bin",
        current_path=None,
    )
    registry.create_or_update_file(
        sha256=accepted_hash,
        size_bytes=16,
        status="accepted",
        original_filename="accepted.bin",
        current_path=None,
    )

    batch = engine.process_batch(
        candidates=[
            StagedCandidate(
                account_name="lisa",
                onedrive_id="id-unknown",
                original_filename="unknown.bin",
                relative_path="/unknown.bin",
                modified_time="2026-03-31T10:11:12+00:00",
                size_bytes=11,
                staging_path=unknown_path,
            ),
            StagedCandidate(
                account_name="lisa",
                onedrive_id="id-rejected",
                original_filename="rejected.bin",
                relative_path="/rejected.bin",
                modified_time="2026-03-31T10:11:13+00:00",
                size_bytes=16,
                staging_path=known_rejected_path,
            ),
            StagedCandidate(
                account_name="lisa",
                onedrive_id="id-accepted",
                original_filename="accepted.bin",
                relative_path="/accepted.bin",
                modified_time="2026-03-31T10:11:14+00:00",
                size_bytes=16,
                staging_path=known_accepted_path,
            ),
        ],
        accepted_root=accepted_root,
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert batch.accepted_count == 1
    actions = sorted(item.action for item in batch.outcomes)
    assert actions == ["accepted", "discard_accepted", "discard_rejected"]


def test_restart_recovery_removes_old_tmp_and_keeps_recent_tmp(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    staging_dir = tmp_path / "staging" / "lisa"
    old_tmp = staging_dir / "old-file.tmp"
    recent_tmp = staging_dir / "recent-file.tmp"
    _write(old_tmp, b"old")
    _write(recent_tmp, b"recent")

    now = time.time()
    os.utime(old_tmp, (now - 3600, now - 3600))
    os.utime(recent_tmp, (now, now))

    removed = engine.cleanup_staging_tmp_files(staging_dir=staging_dir, tmp_ttl_minutes=10)

    assert removed == 1
    assert not old_tmp.exists()
    assert recent_tmp.exists()


def test_missing_staged_file_is_reported_not_failed(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    missing = tmp_path / "staging" / "lisa" / "missing.bin"
    batch = engine.process_batch(
        candidates=[
            StagedCandidate(
                account_name="lisa",
                onedrive_id="missing-id",
                original_filename="missing.bin",
                relative_path="/missing.bin",
                modified_time="2026-03-31T10:11:12+00:00",
                size_bytes=0,
                staging_path=missing,
            )
        ],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert batch.accepted_count == 0
    assert batch.outcomes[0].action == "missing_staged"
