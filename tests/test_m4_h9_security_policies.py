"""M4-H9 tests for ingest and storage security policy tightening."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.pipeline.ingest import IngestDecisionEngine, IngestError, StagedCandidate
from nightfall_photo_ingress.registry import Registry
from nightfall_photo_ingress.storage import (
    StorageError,
    choose_collision_safe_destination_with_threshold,
    commit_staging_to_accepted,
    lint_storage_template,
)


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def test_template_linter_detects_unsafe_patterns() -> None:
    findings = lint_storage_template("../{unknown}/file")
    assert "template_contains_traversal" in findings
    assert "template_unknown_placeholder:{unknown}" in findings


def test_collision_threshold_raises_with_actionable_error(tmp_path: Path) -> None:
    base = tmp_path / "accepted" / "dup.bin"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(b"x")
    (tmp_path / "accepted" / "dup-1.bin").write_bytes(b"x")

    with pytest.raises(StorageError, match="Collision threshold exceeded"):
        choose_collision_safe_destination_with_threshold(base_path=base, max_attempts=1)


def test_commit_enforces_file_and_dir_modes(tmp_path: Path) -> None:
    source = tmp_path / "staging" / "item.bin"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"payload")
    destination = tmp_path / "accepted" / "item.bin"

    commit_staging_to_accepted(
        source_path=source,
        destination_path=destination,
        staging_on_same_pool=False,
        destination_root=tmp_path / "accepted",
        file_mode=0o600,
        dir_mode=0o700,
    )

    assert destination.exists()
    file_mode = destination.stat().st_mode & 0o777
    dir_mode = destination.parent.stat().st_mode & 0o777
    assert file_mode == 0o600
    assert dir_mode == 0o700


def test_ingest_rejects_unsafe_storage_template(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "item.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"data")

    candidate = StagedCandidate(
        account_name="lisa",
        onedrive_id="id-1",
        original_filename="item.bin",
        relative_path="/item.bin",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=4,
        staging_path=staged,
    )

    with pytest.raises(IngestError, match="Unsafe storage template"):
        engine.process_batch(
            candidates=[candidate],
            accepted_root=tmp_path / "accepted",
            storage_template="../{original}",
            staging_on_same_pool=False,
        )
