"""M4-H5 tests for storage durability and root-containment hardening."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.storage import (
    StorageError,
    commit_staging_to_accepted,
    render_storage_relative_path,
)


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_template_rejects_absolute_rendered_path() -> None:
    with pytest.raises(StorageError, match="relative path"):
        render_storage_relative_path(
            storage_template="/absolute/{original}",
            sha256="a" * 64,
            original_filename="x.bin",
            modified_time_iso="2026-03-31T10:11:12+00:00",
        )


def test_template_rejects_traversal_path() -> None:
    with pytest.raises(StorageError, match="unsafe path"):
        render_storage_relative_path(
            storage_template="../{original}",
            sha256="a" * 64,
            original_filename="x.bin",
            modified_time_iso="2026-03-31T10:11:12+00:00",
        )


def test_destination_root_containment_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "staging" / "file.bin"
    _write(source, b"payload")
    allowed_root = tmp_path / "accepted"
    forbidden_dest = tmp_path / "other" / "file.bin"

    with pytest.raises(StorageError, match="escapes accepted root"):
        commit_staging_to_accepted(
            source_path=source,
            destination_path=forbidden_dest,
            staging_on_same_pool=False,
            destination_root=allowed_root,
        )


def test_cross_pool_fsync_failure_raises_storage_error(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "staging" / "file.bin"
    destination = tmp_path / "accepted" / "file.bin"
    _write(source, b"payload")

    def fake_fsync(_fd: int) -> None:
        raise OSError("simulated power-loss boundary")

    monkeypatch.setattr("nightfall_photo_ingress.storage.os.fsync", fake_fsync)

    with pytest.raises(StorageError, match="fsync"):
        commit_staging_to_accepted(
            source_path=source,
            destination_path=destination,
            staging_on_same_pool=False,
            destination_root=tmp_path / "accepted",
        )
