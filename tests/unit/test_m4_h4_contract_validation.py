"""M4-H4 tests for ingest boundary contract validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightfall_photo_ingress.domain.ingest import (
    INGEST_INPUT_SCHEMA_VERSION,
    IngestDecisionEngine,
    IngestError,
    StagedCandidate,
)
from nightfall_photo_ingress.domain.registry import Registry


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _candidate(staging_path: Path) -> StagedCandidate:
    return StagedCandidate(
        account_name="lisa",
        onedrive_id="id-1",
        original_filename="IMG_0001.HEIC",
        relative_path="/Camera Roll/IMG_0001.HEIC",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=4,
        staging_path=staging_path,
    )


def test_schema_version_mismatch_fails_fast(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    candidate = _candidate(tmp_path / "staging" / "item.bin")
    with pytest.raises(IngestError, match="Incompatible ingest input schema version"):
        engine.process_batch(
            candidates=[candidate],
            accepted_root=tmp_path / "accepted",
            storage_template="{yyyy}/{mm}/{sha8}-{original}",
            staging_on_same_pool=False,
            input_schema_version=INGEST_INPUT_SCHEMA_VERSION + 1,
        )


def test_malformed_candidate_relative_path_fails(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    candidate = _candidate(tmp_path / "staging" / "item.bin")
    bad = StagedCandidate(
        account_name=candidate.account_name,
        onedrive_id=candidate.onedrive_id,
        original_filename=candidate.original_filename,
        relative_path="Camera Roll/file.bin",
        modified_time=candidate.modified_time,
        size_bytes=candidate.size_bytes,
        staging_path=candidate.staging_path,
    )

    with pytest.raises(IngestError, match="relative_path must start"):
        engine.process_batch(
            candidates=[bad],
            accepted_root=tmp_path / "accepted",
            storage_template="{yyyy}/{mm}/{sha8}-{original}",
            staging_on_same_pool=False,
        )


def test_malformed_candidate_modified_time_fails(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    candidate = _candidate(tmp_path / "staging" / "item.bin")
    bad = StagedCandidate(
        account_name=candidate.account_name,
        onedrive_id=candidate.onedrive_id,
        original_filename=candidate.original_filename,
        relative_path=candidate.relative_path,
        modified_time="not-a-date",
        size_bytes=candidate.size_bytes,
        staging_path=candidate.staging_path,
    )

    with pytest.raises(IngestError, match="modified_time is not valid ISO-8601"):
        engine.process_batch(
            candidates=[bad],
            accepted_root=tmp_path / "accepted",
            storage_template="{yyyy}/{mm}/{sha8}-{original}",
            staging_on_same_pool=False,
        )


def test_valid_contract_allows_processing(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "item.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"data")

    result = engine.process_batch(
        candidates=[_candidate(staged)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        input_schema_version=INGEST_INPUT_SCHEMA_VERSION,
    )

    assert result.accepted_count == 1
