"""M4-H1 tests for atomic ingest-finalize transaction behavior."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.domain.registry import Registry, RegistryError
from nightfall_photo_ingress.domain.storage import sha256_file


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _count(conn, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def test_finalize_unknown_ingest_rollback_on_injected_failure(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)

    for fail_step in (1, 2, 3, 4):
        try:
            registry.finalize_unknown_ingest(
                sha256=f"{'a'*63}{fail_step}",
                size_bytes=123,
                original_filename="a.heic",
                current_path="/accepted/a.heic",
                account="lisa",
                onedrive_id=f"id-{fail_step}",
                source_path="/Camera Roll/a.heic",
                modified_time="2026-03-31T10:11:12+00:00",
                actor="ingest_pipeline",
                fail_after_step=fail_step,
            )
        except RegistryError:
            pass
        else:
            raise AssertionError("Expected injected failure")

    with registry._connect() as conn:  # noqa: SLF001 - test-only internal check
        assert _count(conn, "files") == 0
        assert _count(conn, "accepted_records") == 0
        assert _count(conn, "metadata_index") == 0
        assert _count(conn, "file_origins") == 0
        assert _count(conn, "audit_log") == 0


def test_finalize_unknown_ingest_writes_all_tables(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    sha = "b" * 64

    registry.finalize_unknown_ingest(
        sha256=sha,
        size_bytes=777,
        original_filename="img.heic",
        current_path="/accepted/img.heic",
        account="lisa",
        onedrive_id="id-1",
        source_path="/Camera Roll/img.heic",
        modified_time="2026-03-31T10:11:12+00:00",
        actor="ingest_pipeline",
    )

    with registry._connect() as conn:  # noqa: SLF001 - test-only internal check
        assert _count(conn, "files") == 1
        assert _count(conn, "accepted_records") == 0
        assert _count(conn, "metadata_index") == 1
        assert _count(conn, "file_origins") == 1
        assert _count(conn, "audit_log") == 1


def test_idempotent_replay_after_simulated_failure(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    staged = tmp_path / "staged.bin"
    staged.write_bytes(b"payload")
    sha = sha256_file(staged)

    try:
        registry.finalize_unknown_ingest(
            sha256=sha,
            size_bytes=7,
            original_filename="payload.bin",
            current_path="/accepted/payload.bin",
            account="lisa",
            onedrive_id="id-replay",
            source_path="/Camera Roll/payload.bin",
            modified_time="2026-03-31T10:11:12+00:00",
            actor="ingest_pipeline",
            fail_after_step=3,
        )
    except RegistryError:
        pass

    registry.finalize_unknown_ingest(
        sha256=sha,
        size_bytes=7,
        original_filename="payload.bin",
        current_path="/accepted/payload.bin",
        account="lisa",
        onedrive_id="id-replay",
        source_path="/Camera Roll/payload.bin",
        modified_time="2026-03-31T10:11:12+00:00",
        actor="ingest_pipeline",
    )

    with registry._connect() as conn:  # noqa: SLF001 - test-only internal check
        assert _count(conn, "files") == 1
        assert _count(conn, "accepted_records") == 0
        assert _count(conn, "metadata_index") == 1
        assert _count(conn, "file_origins") == 1
        assert _count(conn, "audit_log") == 1
