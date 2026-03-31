"""Crash-boundary and replay integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations

import json

import pytest


def test_crash_after_download_before_ingest_leaves_recoverable_staging_state(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    fs_snapshot_fixture,
) -> None:
    pages = [
        {
            "value": [
                {
                    "id": "crash-download-1",
                    "name": "IMG_1000.HEIC",
                    "file": {},
                    "size": 6,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/crash-download-1",
                }
            ]
        }
    ]
    polled = poll_and_ingest_fixture(
        pages=pages,
        downloads={"https://download/crash-download-1": {"content": b"abc123"}},
        run_ingest=False,
    )

    assert polled.registry_harness.file_origins() == []
    assert len(polled.poll_result.downloaded_paths) == 1
    staged_path = polled.poll_result.downloaded_paths[0]
    assert staged_path.exists()

    engine = ingest_engine_fixture()
    replayed = engine.process_batch(
        candidates=list(polled.staged_candidates),
        accepted_root=polled.app_config.core.accepted_path,
        storage_template=polled.app_config.core.storage_template,
        staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
        quarantine_dir=polled.quarantine_root,
    )

    assert replayed.accepted_count == 1
    assert fs_snapshot_fixture(polled.accepted_root)


def test_crash_after_storage_commit_before_registry_finalize_replays_or_completes_safely(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "crash-storage-1",
                        "name": "IMG_2000.HEIC",
                        "file": {},
                        "size": 7,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/crash-storage-1",
                    }
                ]
            }
        ],
        downloads={"https://download/crash-storage-1": {"content": b"abcdefg"}},
        run_ingest=False,
    )
    engine = ingest_engine_fixture()
    crash_injection_fixture.after_storage_commit_before_registry_finalize(
        polled.registry_harness.registry
    )

    with pytest.raises(RuntimeError, match="after storage commit"):
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            accepted_root=polled.app_config.core.accepted_path,
            storage_template=polled.app_config.core.storage_template,
            staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
            quarantine_dir=polled.quarantine_root,
        )

    replay = engine.replay_interrupted_operations()
    assert replay["interrupted_total"] == 1
    assert replay["quarantined_destinations"] == 1
    assert replay["removed_staging"] in {0, 1}
    assert any(path.suffix == ".orphaned" for path in polled.accepted_root.rglob("*"))


def test_crash_during_cross_pool_copy_never_leaves_false_accepted_state(
    app_config_fixture,
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
    fs_snapshot_fixture,
) -> None:
    config = app_config_fixture(core_overrides={"staging_on_same_pool": False})
    polled = poll_and_ingest_fixture(
        app_config=config,
        pages=[
            {
                "value": [
                    {
                        "id": "copy-crash-1",
                        "name": "IMG_3000.MOV",
                        "file": {},
                        "size": 9,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/copy-crash-1",
                    }
                ]
            }
        ],
        downloads={"https://download/copy-crash-1": {"content": b"123456789"}},
        run_ingest=False,
    )
    engine = ingest_engine_fixture()
    crash_injection_fixture.during_cross_pool_copy()

    with pytest.raises(RuntimeError, match="cross-pool copy"):
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            accepted_root=config.core.accepted_path,
            storage_template=config.core.storage_template,
            staging_on_same_pool=False,
            quarantine_dir=polled.quarantine_root,
        )

    assert polled.registry_harness.metadata_rows() == []
    assert polled.registry_harness.file_origins() == []
    accepted_snapshot = fs_snapshot_fixture(config.core.accepted_path)
    assert not any(path.endswith(".heic") or path.endswith(".mov") for path in accepted_snapshot)


def test_replay_of_interrupted_operation_is_monotonic_and_idempotent(
    ingest_engine_fixture,
    registry_fixture,
    tmp_path,
) -> None:
    journal_path = tmp_path / "ingest.journal"
    payload = {
        "op_id": "op-1",
        "account": "lisa",
        "onedrive_id": "item-1",
        "staging_path": str(tmp_path / "staging" / "item.bin"),
        "destination_path": str(tmp_path / "accepted" / "item.bin"),
        "sha256": "a" * 64,
        "ts": "2026-04-01T10:11:12+00:00",
    }
    journal_path.write_text(
        "\n".join(
            json.dumps({**payload, "phase": phase})
            for phase in ("ingest_started", "hash_completed", "storage_committed")
        )
        + "\n",
        encoding="utf-8",
    )
    staging = tmp_path / "staging" / "item.bin"
    destination = tmp_path / "accepted" / "item.bin"
    staging.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(b"abc")
    destination.write_bytes(b"abc")

    engine = ingest_engine_fixture()
    first = engine.replay_interrupted_operations()
    second = engine.replay_interrupted_operations()

    assert first["interrupted_total"] == 1
    assert second["interrupted_total"] == 0
    assert not journal_path.exists()


def test_corrupted_journal_entry_isolated_without_blocking_other_replays(
    ingest_engine_fixture,
    tmp_path,
) -> None:
    journal_path = tmp_path / "ingest.journal"
    valid_staging = tmp_path / "staging" / "valid.bin"
    valid_destination = tmp_path / "accepted" / "valid.bin"
    valid_staging.parent.mkdir(parents=True, exist_ok=True)
    valid_destination.parent.mkdir(parents=True, exist_ok=True)
    valid_staging.write_bytes(b"valid")
    valid_destination.write_bytes(b"valid")
    journal_path.write_text(
        "{bad-json\n"
        + json.dumps(
            {
                "op_id": "good-op",
                "phase": "storage_committed",
                "account": "lisa",
                "onedrive_id": "item-good",
                "staging_path": str(valid_staging),
                "destination_path": str(valid_destination),
                "sha256": "b" * 64,
                "ts": "2026-04-01T10:11:12+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    engine = ingest_engine_fixture()
    replay = engine.replay_interrupted_operations()

    assert replay["interrupted_total"] == 1
    assert (tmp_path / "accepted" / "valid.bin.orphaned").exists()
