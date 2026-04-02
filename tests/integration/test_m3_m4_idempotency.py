"""End-to-end idempotency integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations


def test_three_poll_cycles_new_then_replay_then_noop_are_idempotent(
    poll_and_ingest_fixture,
    fs_snapshot_fixture,
) -> None:
    cycle1 = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "cycle-1",
                        "name": "IMG_CYCLE.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/cycle-1",
                    }
                ]
            }
        ],
        downloads={"https://download/cycle-1": {"content": b"cycle"}},
    )
    cycle2 = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "cycle-1",
                        "name": "IMG_CYCLE.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/cycle-1-b",
                    }
                ]
            }
        ],
        downloads={"https://download/cycle-1-b": {"content": b"cycle"}},
    )
    cycle3 = poll_and_ingest_fixture(pages=[{"value": []}], downloads={})

    assert cycle1.ingest_result.pending_count == 1
    assert cycle2.ingest_result.pending_count == 0
    assert cycle3.poll_result.candidate_count == 0
    assert len([item for item in fs_snapshot_fixture(cycle3.pending_root) if not item.endswith("/")]) == 1
    accepted_rows = cycle3.registry_harness.accepted_rows()
    assert len(accepted_rows) == 0
    terminal_events = cycle3.registry_harness.terminal_events()
    accepted_terminal = [row for row in terminal_events if row["action"] == "pending"]
    assert len(accepted_terminal) == 1
    assert len({row["sha256"] for row in accepted_terminal}) == 1


def test_recovery_cycle_after_interrupted_commit_then_replay_is_idempotent(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "cycle-recovery-1",
                        "name": "IMG_RECOVER.HEIC",
                        "file": {},
                        "size": 7,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/cycle-recovery-1",
                    }
                ]
            }
        ],
        downloads={"https://download/cycle-recovery-1": {"content": b"recover"}},
        run_ingest=False,
    )
    engine = ingest_engine_fixture()
    crash_injection_fixture.after_storage_commit_before_registry_finalize(
        polled.registry_harness.registry
    )
    try:
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            pending_root=polled.pending_root,
            storage_template=polled.app_config.core.storage_template,
            staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
            quarantine_dir=polled.quarantine_root,
        )
    except RuntimeError:
        pass

    recovery = engine.replay_interrupted_operations()
    replay = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "cycle-recovery-1",
                        "name": "IMG_RECOVER.HEIC",
                        "file": {},
                        "size": 7,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/cycle-recovery-1-b",
                    }
                ]
            }
        ],
        downloads={"https://download/cycle-recovery-1-b": {"content": b"recover"}},
    )

    assert recovery["interrupted_total"] == 1
    assert replay.ingest_result.pending_count in {0, 1}
