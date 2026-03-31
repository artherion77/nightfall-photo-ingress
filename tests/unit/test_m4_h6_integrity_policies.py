"""M4-H6 tests for ingest integrity and zero-byte policy controls."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.domain.registry import Registry


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _candidate(staging_path: Path, *, size: int | None) -> StagedCandidate:
    return StagedCandidate(
        account_name="lisa",
        onedrive_id="id-1",
        original_filename="IMG_0001.HEIC",
        relative_path="/Camera Roll/IMG_0001.HEIC",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=size,
        staging_path=staging_path,
    )


def test_pre_hash_size_verification_detects_mismatch(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "item.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"abcd")

    result = engine.process_batch(
        candidates=[_candidate(staged, size=10)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        pre_hash_size_verify=True,
        quarantine_dir=tmp_path / "quarantine",
    )

    assert result.size_mismatch_count == 1
    assert result.outcomes[0].action == "size_mismatch"
    assert (tmp_path / "quarantine" / "size_mismatch" / "item.bin").exists()


def test_missing_size_does_not_fail_verification(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "item.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"abcd")

    result = engine.process_batch(
        candidates=[_candidate(staged, size=None)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        pre_hash_size_verify=True,
    )

    assert result.accepted_count == 1
    assert result.size_mismatch_count == 0


def test_zero_byte_policy_reject(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "zero.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"")

    result = engine.process_batch(
        candidates=[_candidate(staged, size=0)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        zero_byte_policy="reject",
    )

    assert result.zero_byte_reject_count == 1
    assert result.outcomes[0].action == "reject_zero_byte"
    assert not staged.exists()


def test_zero_byte_policy_quarantine(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    staged = tmp_path / "staging" / "lisa" / "zero.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"")

    result = engine.process_batch(
        candidates=[_candidate(staged, size=0)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        zero_byte_policy="quarantine",
        quarantine_dir=tmp_path / "quarantine",
    )

    assert result.zero_byte_quarantine_count == 1
    assert result.outcomes[0].action == "quarantine_zero_byte"
    assert (tmp_path / "quarantine" / "zero_byte" / "zero.bin").exists()
