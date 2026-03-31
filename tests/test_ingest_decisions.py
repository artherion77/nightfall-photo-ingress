"""Ingest pipeline unit and integration tests for decision workflows."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.pipeline.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.registry import Registry
from nightfall_photo_ingress.storage import (
    StorageError,
    commit_staging_to_accepted,
    render_storage_relative_path,
    sanitize_filename,
    sha256_file,
)


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _write_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _candidate(
    *,
    staging_path: Path,
    account: str = "lisa",
    onedrive_id: str = "item-1",
    name: str = "IMG_0001.HEIC",
    rel: str = "/Camera Roll/IMG_0001.HEIC",
    modified: str = "2026-03-31T10:11:12+00:00",
    size: int | None = None,
) -> StagedCandidate:
    return StagedCandidate(
        account_name=account,
        onedrive_id=onedrive_id,
        original_filename=name,
        relative_path=rel,
        modified_time=modified,
        size_bytes=size,
        staging_path=staging_path,
    )


def test_sha256_hashing_correctness(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    _write_file(sample, b"abc")
    assert sha256_file(sample) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_decision_matrix_unknown_is_accepted(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    staging_file = tmp_path / "staging" / "lisa" / "item-a.bin"
    _write_file(staging_file, b"new-data")

    result = engine.process_batch(
        candidates=[
            _candidate(staging_path=staging_file, onedrive_id="item-a", size=8),
        ],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert result.accepted_count == 1
    outcome = result.outcomes[0]
    assert outcome.action == "accepted"
    assert outcome.destination_path is not None
    assert outcome.destination_path.exists()
    assert not staging_file.exists()
    assert registry.get_file(sha256=outcome.sha256 or "") is not None


def test_decision_matrix_known_statuses_are_discarded(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    statuses = ("accepted", "rejected", "purged")
    for index, status in enumerate(statuses):
        payload = f"known-{status}".encode("utf-8")
        staging_file = tmp_path / "staging" / "lisa" / f"item-{status}.bin"
        _write_file(staging_file, payload)
        file_hash = sha256_file(staging_file)

        registry.create_or_update_file(
            sha256=file_hash,
            size_bytes=len(payload),
            status=status,
            original_filename=f"{status}.bin",
            current_path=None,
        )

        result = engine.process_batch(
            candidates=[
                _candidate(
                    staging_path=staging_file,
                    onedrive_id=f"item-{status}",
                    name=f"{status}.bin",
                    rel=f"/{status}.bin",
                    size=len(payload),
                ),
            ],
            accepted_root=tmp_path / "accepted",
            storage_template="{yyyy}/{mm}/{sha8}-{original}",
            staging_on_same_pool=False,
        )

        assert result.accepted_count == 0
        outcome = result.outcomes[0]
        assert outcome.action == f"discard_{status}"
        assert outcome.destination_path is None
        assert not staging_file.exists(), f"staged file for {status} was not removed"
        assert registry.acceptance_count(sha256=file_hash) == 0
        _ = index


def test_metadata_prefilter_skips_hashing_and_discards(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    staging_file = tmp_path / "staging" / "lisa" / "prefilter.bin"
    payload = b"prefilter-data"
    _write_file(staging_file, payload)
    file_hash = sha256_file(staging_file)

    registry.create_or_update_file(
        sha256=file_hash,
        size_bytes=len(payload),
        status="accepted",
        original_filename="prefilter.bin",
        current_path=None,
    )
    registry.upsert_metadata_index(
        account="lisa",
        onedrive_id="prefilter-item",
        size_bytes=len(payload),
        modified_time="2026-03-31T10:11:12+00:00",
        sha256=file_hash,
    )

    result = engine.process_batch(
        candidates=[
            _candidate(
                staging_path=staging_file,
                onedrive_id="prefilter-item",
                name="prefilter.bin",
                rel="/prefilter.bin",
                size=len(payload),
            )
        ],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert result.prefilter_discard_count == 1
    assert result.outcomes[0].prefilter_hit is True
    assert result.outcomes[0].action == "discard_accepted"
    assert not staging_file.exists()


def test_collision_safe_naming_creates_unique_destination(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)
    accepted_root = tmp_path / "accepted"

    first_stage = tmp_path / "staging" / "lisa" / "first.bin"
    second_stage = tmp_path / "staging" / "lisa" / "second.bin"
    _write_file(first_stage, b"first-payload")
    _write_file(second_stage, b"second-payload")

    first = engine.process_batch(
        candidates=[
            _candidate(staging_path=first_stage, onedrive_id="first", name="dup.heic", size=13),
        ],
        accepted_root=accepted_root,
        storage_template="{yyyy}/{mm}/fixed-{original}",
        staging_on_same_pool=False,
    )
    second = engine.process_batch(
        candidates=[
            _candidate(staging_path=second_stage, onedrive_id="second", name="dup.heic", size=14),
        ],
        accepted_root=accepted_root,
        storage_template="{yyyy}/{mm}/fixed-{original}",
        staging_on_same_pool=False,
    )

    first_dest = first.outcomes[0].destination_path
    second_dest = second.outcomes[0].destination_path
    assert first_dest is not None and second_dest is not None
    assert first_dest != second_dest
    assert first_dest.exists() and second_dest.exists()


def test_cross_pool_copy_verify_unlink_behavior(tmp_path: Path) -> None:
    source = tmp_path / "staging" / "lisa" / "source.bin"
    destination = tmp_path / "accepted" / "target.bin"
    _write_file(source, b"copy-verify-data")

    result = commit_staging_to_accepted(
        source_path=source,
        destination_path=destination,
        staging_on_same_pool=False,
    )

    assert result.method == "copy_verify_unlink"
    assert destination.exists()
    assert not source.exists()


def test_cross_pool_size_mismatch_raises_storage_error(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "staging" / "source.bin"
    destination = tmp_path / "accepted" / "target.bin"
    _write_file(source, b"abcdef")

    from nightfall_photo_ingress import storage as storage_module

    original_copy2 = storage_module.shutil.copy2

    def fake_copy2(src: Path, dst: Path) -> Path:
        original_copy2(src, dst)
        Path(dst).write_bytes(b"x")
        return Path(dst)

    monkeypatch.setattr(storage_module.shutil, "copy2", fake_copy2)

    try:
        commit_staging_to_accepted(
            source_path=source,
            destination_path=destination,
            staging_on_same_pool=False,
        )
    except StorageError as exc:
        assert "size mismatch" in str(exc)
    else:
        raise AssertionError("Expected StorageError for size mismatch")


def test_render_storage_template_and_sanitize_filename() -> None:
    rel = render_storage_relative_path(
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        sha256="a" * 64,
        original_filename="IMG:bad/name?.HEIC",
        modified_time_iso="2026-04-01T01:02:03+00:00",
    )
    assert str(rel).startswith("2026/04/aaaaaaaa-")
    assert "IMG_bad_name_.HEIC" in str(rel)
    assert sanitize_filename("...") == "unnamed"
