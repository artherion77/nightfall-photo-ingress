"""M4-H8 tests for ingest worker orchestration and diagnostics."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine, IngestOutcome, StagedCandidate
from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.domain.storage import sha256_file


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _candidate(tmp_path: Path, name: str, size: int) -> StagedCandidate:
    path = tmp_path / "staging" / "lisa" / f"{name}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return StagedCandidate(
        account_name="lisa",
        onedrive_id=name,
        original_filename=f"{name}.bin",
        relative_path=f"/{name}.bin",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=size,
        staging_path=path,
    )


def test_size_aware_scheduling_prioritizes_larger_candidates(tmp_path: Path, monkeypatch) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    calls: list[str] = []

    def fake_process_one(*, candidate, **_kwargs):
        calls.append(candidate.onedrive_id)
        return IngestOutcome(
            account_name=candidate.account_name,
            onedrive_id=candidate.onedrive_id,
            action="accepted",
            sha256="a" * 64,
            destination_path=tmp_path / "accepted" / f"{candidate.onedrive_id}.bin",
            prefilter_hit=False,
        )

    monkeypatch.setattr(engine, "_process_one", fake_process_one)

    candidates = [
        _candidate(tmp_path, "small", 1),
        _candidate(tmp_path, "big", 10),
        _candidate(tmp_path, "mid", 5),
    ]

    engine.process_batch(
        candidates=candidates,
        pending_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        worker_count=1,
        size_aware_scheduling=True,
    )

    assert calls == ["big", "mid", "small"]


def test_worker_pool_keeps_terminal_audit_sequence_stable(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    candidates = [
        _candidate(tmp_path, "a", 3),
        _candidate(tmp_path, "b", 3),
        _candidate(tmp_path, "c", 3),
    ]

    batch = engine.process_batch(
        candidates=candidates,
        pending_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        worker_count=3,
        size_aware_scheduling=False,
    )

    assert len(batch.outcomes) == 3
    with registry._connect() as conn:  # noqa: SLF001 - test query
        rows = conn.execute(
            "SELECT sequence_no, onedrive_id FROM ingest_terminal_audit ORDER BY id ASC"
        ).fetchall()
    assert [int(row["sequence_no"]) for row in rows] == [1, 2, 3]
    assert [row["onedrive_id"] for row in rows] == ["a", "b", "c"]


def test_prefilter_hit_and_miss_diagnostics(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    hit = _candidate(tmp_path, "hit", 4)
    miss = _candidate(tmp_path, "miss", 6)

    hit_hash = sha256_file(hit.staging_path)
    registry.create_or_update_file(
        sha256=hit_hash,
        size_bytes=4,
        status="accepted",
        original_filename="hit.bin",
        current_path=None,
    )
    registry.upsert_metadata_index(
        account="lisa",
        onedrive_id="hit",
        size_bytes=4,
        modified_time="2026-03-31T10:11:12+00:00",
        sha256=hit_hash,
    )

    batch = engine.process_batch(
        candidates=[hit, miss],
        pending_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
        worker_count=1,
    )

    assert batch.prefilter_hit_count == 1
    assert batch.prefilter_miss_count == 1
