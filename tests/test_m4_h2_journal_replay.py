"""M4-H2 tests for ingest lifecycle journal and replay logic."""

from __future__ import annotations

import json
from pathlib import Path

from nightfall_photo_ingress.pipeline.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.pipeline.journal import IngestOperationJournal
from nightfall_photo_ingress.registry import Registry


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _candidate(staging_path: Path) -> StagedCandidate:
    return StagedCandidate(
        account_name="lisa",
        onedrive_id="item-1",
        original_filename="IMG_0001.HEIC",
        relative_path="/Camera Roll/IMG_0001.HEIC",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=4,
        staging_path=staging_path,
    )


def test_journal_rotation_happens_when_max_size_exceeded(tmp_path: Path) -> None:
    journal = IngestOperationJournal(path=tmp_path / "ingest.journal", max_bytes=80)

    for index in range(10):
        journal.append(
            op_id=f"op-{index}",
            phase="ingest_started",
            account="lisa",
            onedrive_id=f"id-{index}",
            staging_path=tmp_path / f"{index}.tmp",
        )

    rotated = tmp_path / "ingest.journal.1"
    assert rotated.exists()
    assert journal.path.exists()


def test_replay_reconciles_interrupted_operation(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    journal_path = tmp_path / "ingest.journal"
    engine = IngestDecisionEngine(registry, journal_path=journal_path)

    staging = tmp_path / "staging" / "lisa" / "item.bin"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(b"data")

    destination = tmp_path / "accepted" / "item.bin"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"committed")

    with journal_path.open("w", encoding="utf-8") as handle:
        for phase, dest, sha in (
            ("ingest_started", None, None),
            ("hash_completed", None, "a" * 64),
            ("storage_committed", str(destination), "a" * 64),
        ):
            handle.write(
                json.dumps(
                    {
                        "op_id": "op-1",
                        "phase": phase,
                        "ts": "2026-03-31T10:11:12+00:00",
                        "account": "lisa",
                        "onedrive_id": "item-1",
                        "staging_path": str(staging),
                        "destination_path": dest,
                        "sha256": sha,
                    }
                )
                + "\n"
            )

    result = engine.replay_interrupted_operations()
    assert result["interrupted_total"] == 1
    assert result["quarantined_destinations"] == 1
    assert result["removed_staging"] == 1
    assert not staging.exists()
    assert (tmp_path / "accepted" / "item.bin.orphaned").exists()
    assert not journal_path.exists()


def test_replay_ignores_completed_operation(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    journal_path = tmp_path / "ingest.journal"
    engine = IngestDecisionEngine(registry, journal_path=journal_path)

    with journal_path.open("w", encoding="utf-8") as handle:
        for phase in ("ingest_started", "hash_completed", "storage_committed", "registry_persisted"):
            handle.write(
                json.dumps(
                    {
                        "op_id": "op-1",
                        "phase": phase,
                        "ts": "2026-03-31T10:11:12+00:00",
                        "account": "lisa",
                        "onedrive_id": "item-1",
                        "staging_path": "/tmp/staging/file.bin",
                        "destination_path": "/tmp/accepted/file.bin",
                        "sha256": "a" * 64,
                    }
                )
                + "\n"
            )

    result = engine.replay_interrupted_operations()
    assert result["interrupted_total"] == 0


def test_batch_emits_lifecycle_entries(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    journal_path = tmp_path / "ingest.journal"
    engine = IngestDecisionEngine(registry, journal_path=journal_path)

    staged = tmp_path / "staging" / "lisa" / "item.bin"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"data")

    batch = engine.process_batch(
        candidates=[_candidate(staged)],
        accepted_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert batch.accepted_count == 1

    records = IngestOperationJournal(path=journal_path).read_all()
    phases = [record.phase for record in records]
    assert "ingest_started" in phases
    assert "hash_completed" in phases
    assert "storage_committed" in phases
    assert "registry_persisted" in phases
