"""Registry operation tests for Module 2."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nightfall_photo_ingress.domain.registry import HASH_IMPORT_ACCOUNT, Registry, RegistryError


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


def test_prune_auth_failure_backlog_preserves_non_auth_audit_and_append_only_guards(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)
    sha = "a" * 64
    reg.append_audit_event(
        sha256=sha,
        action="accepted",
        reason="ok",
        actor="operator",
    )
    reg.append_audit_event(
        sha256=None,
        action="auth_failure",
        reason="Missing Authorization header",
        actor="api_auth",
        details_json='{"path":"/api/v1/health"}',
    )
    reg.append_audit_event(
        sha256=None,
        action="auth_failure",
        reason="Missing Authorization header",
        actor="api_auth",
        details_json='{"path":"/api/v1/staging"}',
    )

    pruned = reg.prune_auth_failure_audit_backlog(keep_latest=0)

    assert pruned == 2
    remaining = reg.list_audit_events(sha256=sha)
    assert [event.action for event in remaining] == ["accepted"]

    conn = sqlite3.connect(reg.db_path)
    try:
        total_auth = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'auth_failure'").fetchone()[0]
        assert total_auth == 0
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log WHERE action = 'accepted'")
    finally:
        conn.close()


def test_prune_auth_failure_backlog_can_keep_latest_rows(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)
    for suffix in ("a", "b", "c"):
        reg.append_audit_event(
            sha256=None,
            action="auth_failure",
            reason=f"reason-{suffix}",
            actor="api_auth",
        )

    pruned = reg.prune_auth_failure_audit_backlog(keep_latest=1)

    assert pruned == 2
    conn = sqlite3.connect(reg.db_path)
    try:
        rows = conn.execute(
            "SELECT reason FROM audit_log WHERE action = 'auth_failure' ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()

    assert [row[0] for row in rows] == ["reason-c"]


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


def test_external_hash_cache_hash_import_rows_upsert_by_null_source_relpath(tmp_path: Path) -> None:
    """Hash-import rows with NULL source_relpath must be idempotent."""

    reg = _new_registry(tmp_path)
    reg.upsert_external_hash_cache(
        account_name="__hash_import__",
        source_relpath=None,
        hash_algo="sha256",
        hash_value="a" * 64,
        verified_sha256=None,
    )
    reg.upsert_external_hash_cache(
        account_name="__hash_import__",
        source_relpath=None,
        hash_algo="sha256",
        hash_value="a" * 64,
        verified_sha256="a" * 64,
    )

    conn = sqlite3.connect(reg.db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*), MAX(verified_sha256)
            FROM external_hash_cache
            WHERE account_name = ? AND source_relpath IS NULL AND hash_algo = ? AND hash_value = ?
            """,
            ("__hash_import__", "sha256", "a" * 64),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row[0]) == 1
    assert row[1] == "a" * 64


def test_external_hash_cache_sync_import_rows_remain_path_distinct(tmp_path: Path) -> None:
    """Legacy sync-import rows remain distinct by source_relpath."""

    reg = _new_registry(tmp_path)
    for source_relpath in ("album/A.HEIC", "album/B.HEIC"):
        reg.upsert_external_hash_cache(
            account_name="__library__",
            source_relpath=source_relpath,
            hash_algo="sha1",
            hash_value="same-hash",
            verified_sha256=None,
        )

    conn = sqlite3.connect(reg.db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM external_hash_cache
            WHERE account_name = ? AND hash_algo = ? AND hash_value = ?
            """,
            ("__library__", "sha1", "same-hash"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row[0]) == 2


def test_bulk_insert_hash_import_inserts_rows_and_reports_chunk_stats(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    results = reg.bulk_insert_hash_import(
        hashes=["a" * 64, "b" * 64, "c" * 64, "d" * 64],
        chunk_size=3,
    )

    assert results == (
        type(results[0])(chunk_index=1, imported=3, skipped_existing=0),
        type(results[1])(chunk_index=2, imported=1, skipped_existing=0),
    )

    conn = sqlite3.connect(reg.db_path)
    try:
        rows = conn.execute(
            """
            SELECT account_name, source_relpath, hash_algo, hash_value, verified_sha256
            FROM external_hash_cache
            WHERE account_name = ?
            ORDER BY hash_value
            """,
            (HASH_IMPORT_ACCOUNT,),
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        (HASH_IMPORT_ACCOUNT, None, "sha256", "a" * 64, "a" * 64),
        (HASH_IMPORT_ACCOUNT, None, "sha256", "b" * 64, "b" * 64),
        (HASH_IMPORT_ACCOUNT, None, "sha256", "c" * 64, "c" * 64),
        (HASH_IMPORT_ACCOUNT, None, "sha256", "d" * 64, "d" * 64),
    ]


def test_bulk_insert_hash_import_is_fully_idempotent_across_reimports(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)
    hashes = ["a" * 64, "b" * 64, "c" * 64]

    first = reg.bulk_insert_hash_import(hashes=hashes, chunk_size=10)
    second = reg.bulk_insert_hash_import(hashes=hashes, chunk_size=10)

    assert first == (type(first[0])(chunk_index=1, imported=3, skipped_existing=0),)
    assert second == (type(second[0])(chunk_index=1, imported=0, skipped_existing=3),)

    conn = sqlite3.connect(reg.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM external_hash_cache WHERE account_name = ?",
            (HASH_IMPORT_ACCOUNT,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row[0]) == 3


def test_bulk_insert_hash_import_only_inserts_new_rows_for_overlapping_imports(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    reg.bulk_insert_hash_import(hashes=["a" * 64, "b" * 64], chunk_size=10)
    results = reg.bulk_insert_hash_import(hashes=["b" * 64, "c" * 64, "d" * 64], chunk_size=10)

    assert results == (type(results[0])(chunk_index=1, imported=2, skipped_existing=1),)


def test_bulk_insert_hash_import_does_not_write_files_or_audit_tables(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    reg.create_or_update_file(sha256="f" * 64, size_bytes=42, status="pending")
    reg.append_audit_event(sha256="f" * 64, action="pending", reason=None, actor="test")
    reg.bulk_insert_hash_import(hashes=["a" * 64, "b" * 64], chunk_size=1)

    conn = sqlite3.connect(reg.db_path)
    try:
        files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        accepted_count = conn.execute("SELECT COUNT(*) FROM accepted_records").fetchone()[0]
        metadata_count = conn.execute("SELECT COUNT(*) FROM metadata_index").fetchone()[0]
        origins_count = conn.execute("SELECT COUNT(*) FROM file_origins").fetchone()[0]
        pair_count = conn.execute("SELECT COUNT(*) FROM live_photo_pairs").fetchone()[0]
    finally:
        conn.close()

    assert files_count == 1
    assert audit_count == 1
    assert accepted_count == 0
    assert metadata_count == 0
    assert origins_count == 0
    assert pair_count == 0


def test_bulk_insert_hash_import_rejects_non_positive_chunk_size(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    with pytest.raises(RegistryError, match="chunk_size must be > 0"):
        reg.bulk_insert_hash_import(hashes=["a" * 64], chunk_size=0)


def test_bulk_insert_hash_import_empty_input_returns_no_chunks(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    assert reg.bulk_insert_hash_import(hashes=[], chunk_size=1000) == ()
