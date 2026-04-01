"""Registry operation tests for Module 2."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nightfall_photo_ingress.domain.registry import Registry, RegistryError


def _new_registry(tmp_path: Path) -> Registry:
    """Build and initialize a registry for each test."""

    reg = Registry(tmp_path / "registry.db")
    reg.initialize()
    return reg


def test_status_transition_transaction_flow(tmp_path: Path) -> None:
    """Status transitions should be persisted with ordered audit entries."""

    reg = _new_registry(tmp_path)
    sha = "b" * 64
    reg.create_or_update_file(
        sha256=sha,
        size_bytes=111,
        status="accepted",
        original_filename="img.heic",
        current_path="/nightfall/media/photo-ingress/accepted/img.heic",
    )

    reg.transition_status(sha256=sha, new_status="rejected", reason="operator reject", actor="cli")
    reg.transition_status(sha256=sha, new_status="purged", reason="cleanup", actor="pipeline")

    file_row = reg.get_file(sha256=sha)
    assert file_row is not None
    assert file_row.status == "purged"

    events = reg.list_audit_events(sha256=sha)
    assert [event.action for event in events] == ["rejected", "purged"]


def test_audit_log_is_append_only(tmp_path: Path) -> None:
    """Audit table should reject update and delete statements via triggers."""

    reg = _new_registry(tmp_path)
    sha = "c" * 64
    reg.create_or_update_file(sha256=sha, size_bytes=50, status="accepted")
    event_id = reg.append_audit_event(
        sha256=sha,
        action="accepted",
        reason="initial",
        actor="pipeline",
    )

    conn = sqlite3.connect(reg.db_path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET action = 'mutated' WHERE id = ?", (event_id,))

        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log WHERE id = ?", (event_id,))
    finally:
        conn.close()


def test_accepted_history_remains_after_current_path_cleared(tmp_path: Path) -> None:
    """Acceptance history must survive manual queue move-outs."""

    reg = _new_registry(tmp_path)
    sha = "d" * 64
    reg.create_or_update_file(
        sha256=sha,
        size_bytes=77,
        status="accepted",
        current_path="/nightfall/media/photo-ingress/accepted/2026/03/d.heic",
    )
    reg.record_acceptance(
        sha256=sha,
        account="primary",
        source_path="/nightfall/media/photo-ingress/accepted/2026/03/d.heic",
    )

    reg.clear_current_path(sha256=sha)

    file_row = reg.get_file(sha256=sha)
    assert file_row is not None
    assert file_row.current_path is None
    assert reg.acceptance_count(sha256=sha) == 1


def test_end_to_end_db_lifecycle_from_empty_to_populated(tmp_path: Path) -> None:
    """Registry should support complete lifecycle writes in one run."""

    reg = _new_registry(tmp_path)
    sha = "e" * 64

    reg.create_or_update_file(
        sha256=sha,
        size_bytes=1234,
        status="accepted",
        original_filename="IMG_0001.HEIC",
        current_path="/nightfall/media/photo-ingress/accepted/2026/03/IMG_0001.HEIC",
    )
    reg.upsert_metadata_index(
        account="primary",
        onedrive_id="od-123",
        size_bytes=1234,
        modified_time="2026-03-31T12:34:56Z",
        sha256=sha,
    )
    reg.upsert_file_origin(
        sha256=sha,
        account="primary",
        onedrive_id="od-123",
        path_hint="/Camera Roll/IMG_0001.HEIC",
    )
    reg.record_acceptance(
        sha256=sha,
        account="primary",
        source_path="/nightfall/media/photo-ingress/accepted/2026/03/IMG_0001.HEIC",
    )
    reg.transition_status(sha256=sha, new_status="rejected", reason="operator", actor="cli")

    row = reg.get_file(sha256=sha)
    assert row is not None
    assert row.status == "rejected"
    assert reg.acceptance_count(sha256=sha) == 1


def test_simulated_restart_preserves_consistency(tmp_path: Path) -> None:
    """Data written before restart should remain queryable after re-open."""

    db_path = tmp_path / "registry.db"
    reg_a = Registry(db_path)
    reg_a.initialize()
    sha = "f" * 64
    reg_a.create_or_update_file(sha256=sha, size_bytes=42, status="accepted")
    reg_a.append_audit_event(sha256=sha, action="accepted", reason=None, actor="pipeline")

    reg_b = Registry(db_path)
    reg_b.initialize()

    file_row = reg_b.get_file(sha256=sha)
    assert file_row is not None
    assert file_row.status == "accepted"
    assert len(reg_b.list_audit_events(sha256=sha)) == 1


def test_transition_missing_sha_raises_registry_error(tmp_path: Path) -> None:
    """Transition API should fail fast for missing file rows."""

    reg = _new_registry(tmp_path)

    with pytest.raises(RegistryError):
        reg.transition_status(
            sha256="0" * 64,
            new_status="rejected",
            reason="missing",
            actor="test",
        )


def test_append_audit_event_allows_sha256_none_and_details_payload(tmp_path: Path) -> None:
    """Canonical audit_log allows optional sha256 with structured details payload."""

    reg = _new_registry(tmp_path)
    event_id = reg.append_audit_event(
        sha256=None,
        action="auth_failure",
        reason="token_expired",
        actor="poller",
        account_name="primary",
        details_json='{"status":401}',
    )

    conn = sqlite3.connect(reg.db_path)
    try:
        row = conn.execute(
            "SELECT sha256, account_name, details_json FROM audit_log WHERE id = ?",
            (event_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] is None
    assert row[1] == "primary"
    assert row[2] == '{"status":401}'


def test_external_hash_cache_upsert_is_idempotent(tmp_path: Path) -> None:
    """Sync-import external hash cache rows should upsert deterministically."""

    reg = _new_registry(tmp_path)
    reg.upsert_external_hash_cache(
        account_name="primary",
        source_relpath="2026/04/IMG_1.HEIC",
        hash_algo="sha1",
        hash_value="abc",
        verified_sha256=None,
    )
    reg.upsert_external_hash_cache(
        account_name="primary",
        source_relpath="2026/04/IMG_1.HEIC",
        hash_algo="sha1",
        hash_value="abc",
        verified_sha256="f" * 64,
    )

    conn = sqlite3.connect(reg.db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*), MAX(verified_sha256)
            FROM external_hash_cache
            WHERE account_name = ? AND source_relpath = ? AND hash_algo = ? AND hash_value = ?
            """,
            ("primary", "2026/04/IMG_1.HEIC", "sha1", "abc"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row[0]) == 1
    assert row[1] == "f" * 64
