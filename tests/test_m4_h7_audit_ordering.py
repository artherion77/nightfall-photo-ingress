"""M4-H7 tests for terminal audit completeness and ordering metadata."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.pipeline.ingest import IngestDecisionEngine, StagedCandidate
from nightfall_photo_ingress.registry import Registry
from nightfall_photo_ingress.storage import sha256_file


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _candidate(staging_path: Path, onedrive_id: str, size: int | None) -> StagedCandidate:
    return StagedCandidate(
        account_name="lisa",
        onedrive_id=onedrive_id,
        original_filename=f"{onedrive_id}.bin",
        relative_path=f"/{onedrive_id}.bin",
        modified_time="2026-03-31T10:11:12+00:00",
        size_bytes=size,
        staging_path=staging_path,
    )


def test_terminal_audit_completeness_and_ordering(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    missing = tmp_path / "staging" / "lisa" / "missing.bin"

    accepted = tmp_path / "staging" / "lisa" / "accepted.bin"
    accepted.parent.mkdir(parents=True, exist_ok=True)
    accepted.write_bytes(b"accepted")

    known = tmp_path / "staging" / "lisa" / "known.bin"
    known.write_bytes(b"known")
    known_hash = sha256_file(known)
    registry.create_or_update_file(
        sha256=known_hash,
        size_bytes=5,
        status="rejected",
        original_filename="known.bin",
        current_path=None,
    )

    batch = engine.process_batch(
        candidates=[
            _candidate(missing, "missing", 0),
            _candidate(accepted, "accepted", 8),
            _candidate(known, "known", 5),
        ],
        accepted_root=tmp_path / "accepted-root",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=False,
    )

    assert len(batch.outcomes) == 3

    with registry._connect() as conn:  # noqa: SLF001 - test query
        rows = conn.execute(
            """
            SELECT batch_run_id, sequence_no, action
            FROM ingest_terminal_audit
            ORDER BY id ASC
            """
        ).fetchall()

    assert len(rows) == 3
    assert len({row["batch_run_id"] for row in rows}) == 1
    assert [int(row["sequence_no"]) for row in rows] == [1, 2, 3]
    assert [row["action"] for row in rows] == [
        "missing_staged",
        "accepted",
        "discard_rejected",
    ]
