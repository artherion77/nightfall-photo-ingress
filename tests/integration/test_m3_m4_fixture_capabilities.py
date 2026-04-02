"""Chunk 3 fixture-capability and determinism integration tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _single_page(item_id: str, url: str, size: int = 6) -> list[dict[str, object]]:
    return [
        {
            "value": [
                {
                    "id": item_id,
                    "name": f"{item_id}.HEIC",
                    "file": {},
                    "size": size,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": url,
                }
            ]
        }
    ]


def test_crash_hook_after_staging_write_interrupts_poll(
    poll_and_ingest_fixture,
    crash_injection_fixture,
    registry_fixture,
) -> None:
    crash_injection_fixture.after_staging_write()

    with pytest.raises(RuntimeError, match="after staging write"):
        poll_and_ingest_fixture(
            pages=_single_page("chunk3-stage", "https://download/chunk3-stage"),
            downloads={"https://download/chunk3-stage": {"content": b"abcdef"}},
            run_ingest=False,
        )

    assert registry_fixture.terminal_events() == []


def test_crash_hook_after_hash_complete_interrupts_ingest(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=_single_page("chunk3-hash", "https://download/chunk3-hash"),
        downloads={"https://download/chunk3-hash": {"content": b"abcdef"}},
        run_ingest=False,
    )

    engine = ingest_engine_fixture()
    crash_injection_fixture.after_hash_complete(engine)

    with pytest.raises(RuntimeError, match="after hash complete"):
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            pending_root=polled.app_config.core.pending_path,
            storage_template=polled.app_config.core.storage_template,
            staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
            quarantine_dir=polled.quarantine_root,
        )

    assert engine._journal is not None
    journal_lines = engine._journal.path.read_text(encoding="utf-8").splitlines()
    assert any('"phase":"hash_completed"' in line for line in journal_lines)


def test_crash_hook_during_journal_append_interrupts_ingest(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
    registry_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=_single_page("chunk3-append", "https://download/chunk3-append"),
        downloads={"https://download/chunk3-append": {"content": b"abcdef"}},
        run_ingest=False,
    )

    engine = ingest_engine_fixture()
    crash_injection_fixture.during_journal_append(engine)

    with pytest.raises(RuntimeError, match="during journal append"):
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            pending_root=polled.app_config.core.pending_path,
            storage_template=polled.app_config.core.storage_template,
            staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
            quarantine_dir=polled.quarantine_root,
        )

    assert registry_fixture.accepted_rows() == []


def test_crash_hook_during_journal_replay_interrupts_recovery(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=_single_page("chunk3-replay", "https://download/chunk3-replay", size=7),
        downloads={"https://download/chunk3-replay": {"content": b"abcdefg"}},
        run_ingest=False,
    )

    engine = ingest_engine_fixture()
    crash_injection_fixture.after_storage_commit_before_registry_finalize(
        polled.registry_harness.registry
    )

    with pytest.raises(RuntimeError, match="after storage commit"):
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            pending_root=polled.app_config.core.pending_path,
            storage_template=polled.app_config.core.storage_template,
            staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
            quarantine_dir=polled.quarantine_root,
        )

    crash_injection_fixture.during_journal_replay(engine)
    with pytest.raises(RuntimeError, match="during journal replay"):
        engine.replay_interrupted_operations()


def test_audit_reader_extended_helpers_expose_reasons_actors_and_sequences(
    poll_and_ingest_fixture,
    audit_reader_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=_single_page("chunk3-audit", "https://download/chunk3-audit"),
        downloads={"https://download/chunk3-audit": {"content": b"abcdef"}},
    )

    assert result.ingest_result is not None
    sha = result.ingest_result.outcomes[0].sha256 or ""
    assert "pending" in audit_reader_fixture.terminal_actions()
    assert "unknown_hash" in audit_reader_fixture.terminal_reasons()
    assert "ingest_pipeline" in audit_reader_fixture.terminal_actors()
    assert all(batch_id for batch_id in audit_reader_fixture.batch_run_ids())
    seq = audit_reader_fixture.sequence_numbers()
    assert seq == tuple(sorted(seq))
    assert "ingest_pipeline" in audit_reader_fixture.audit_actors(sha)


def test_deterministic_time_fixture_controls_journal_and_drift_classification(
    tmp_path: Path,
    ingest_engine_fixture,
    deterministic_time_fixture,
    registry_fixture,
) -> None:
    deterministic_time_fixture("2026-04-01T12:00:00+00:00")

    staging_root = tmp_path / "staging"
    quarantine_root = tmp_path / "quarantine"
    stale_tmp = staging_root / "old.tmp"
    stale_tmp.parent.mkdir(parents=True, exist_ok=True)
    stale_tmp.write_bytes(b"temp")

    old_epoch = 0
    os.utime(stale_tmp, (old_epoch, old_epoch))

    engine = ingest_engine_fixture()
    report = engine.reconcile_staging_drift(
        staging_dir=staging_root,
        quarantine_dir=quarantine_root,
        tmp_ttl_minutes=1,
        failed_ttl_hours=1,
        orphan_ttl_days=1,
    )

    assert report.stale_temp_count == 1
    assert report.quarantined_count == 1

    # Journal timestamps should use frozen clock.
    candidate = result_candidate = None
    staged = staging_root / "fixed.bin"
    staged.write_bytes(b"abc")
    from nightfall_photo_ingress.domain.ingest import StagedCandidate

    candidate = StagedCandidate(
        account_name="lisa",
        onedrive_id="chunk3-time",
        original_filename="fixed.bin",
        relative_path="/Camera Roll/2026",
        modified_time="2026-04-01T10:11:12+00:00",
        size_bytes=3,
        staging_path=staged,
    )
    batch = engine.process_batch(
        candidates=[candidate],
        pending_root=tmp_path / "accepted",
        storage_template="{yyyy}/{mm}/{sha8}-{original}",
        staging_on_same_pool=True,
        quarantine_dir=quarantine_root,
    )
    assert batch.pending_count == 1

    journal_lines = (tmp_path / "ingest.journal").read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in journal_lines if line.strip()]
    assert all(entry["ts"].startswith("2026-04-01T12:00:00") for entry in payloads)
    assert registry_fixture.accepted_rows() == []
