"""Storage, integrity, and reject-path integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations

import pytest

from nightfall_photo_ingress.onedrive.errors import DownloadError
from nightfall_photo_ingress.pipeline.ingest import StagedCandidate
from nightfall_photo_ingress.storage import sha256_file


def test_size_mismatch_between_metadata_and_staged_file_rejected_before_accept(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    fs_snapshot_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "mismatch-1",
                        "name": "IMG_MISMATCH.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/mismatch-1",
                    }
                ]
            }
        ],
        downloads={"https://download/mismatch-1": {"content": b"short"}},
        run_ingest=False,
    )

    candidate = polled.staged_candidates[0]
    mismatched_candidate = StagedCandidate(
        account_name=candidate.account_name,
        onedrive_id=candidate.onedrive_id,
        original_filename=candidate.original_filename,
        relative_path=candidate.relative_path,
        modified_time=candidate.modified_time,
        size_bytes=100,
        staging_path=candidate.staging_path,
    )
    engine = ingest_engine_fixture()
    result = engine.process_batch(
        candidates=[mismatched_candidate],
        accepted_root=polled.accepted_root,
        storage_template=polled.app_config.core.storage_template,
        staging_on_same_pool=polled.app_config.core.staging_on_same_pool,
        quarantine_dir=polled.quarantine_root,
    )

    assert result.size_mismatch_count == 1
    assert fs_snapshot_fixture(polled.accepted_root) == tuple()
    assert any("size_mismatch" in path for path in fs_snapshot_fixture(polled.quarantine_root))


def test_truncated_download_detected_end_to_end(
    poll_and_ingest_fixture,
) -> None:
    with pytest.raises(DownloadError, match="Downloaded byte count did not match expected size"):
        poll_and_ingest_fixture(
            pages=[
                {
                    "value": [
                        {
                            "id": "truncated-1",
                            "name": "IMG_TRUNC.HEIC",
                            "file": {},
                            "size": 8,
                            "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                            "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                            "@microsoft.graph.downloadUrl": "https://download/truncated-1",
                        }
                    ]
                }
            ],
            downloads={"https://download/truncated-1": {"chunks": [b"123", b"45"], "repeat": 4}},
            run_ingest=False,
        )


def test_zero_byte_policy_is_enforced_consistently(
    app_config_fixture,
    poll_and_ingest_fixture,
) -> None:
    config = app_config_fixture()
    result = poll_and_ingest_fixture(
        app_config=config,
        pages=[
            {
                "value": [
                    {
                        "id": "zero-1",
                        "name": "ZERO.HEIC",
                        "file": {},
                        "size": 0,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/zero-1",
                    }
                ]
            }
        ],
        downloads={"https://download/zero-1": {"content": b""}},
        zero_byte_policy="quarantine",
    )

    assert result.ingest_result.zero_byte_quarantine_count == 1
    assert result.ingest_result.outcomes[0].action == "quarantine_zero_byte"


def test_same_pool_atomic_rename_is_single_commit_visibility(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "rename-1",
                        "name": "IMG_RENAME.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/rename-1",
                    }
                ]
            }
        ],
        downloads={"https://download/rename-1": {"content": b"rename"}},
    )

    outcome = result.ingest_result.outcomes[0]
    assert outcome.destination_path is not None and outcome.destination_path.exists()
    assert not any(path.suffix == ".tmp" for path in result.accepted_root.rglob("*"))


def test_cross_pool_copy_verify_unlink_rejects_on_hash_mismatch(
    app_config_fixture,
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
) -> None:
    config = app_config_fixture(core_overrides={"staging_on_same_pool": False})
    polled = poll_and_ingest_fixture(
        app_config=config,
        pages=[
            {
                "value": [
                    {
                        "id": "cross-mismatch-1",
                        "name": "IMG_CROSS.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/cross-mismatch-1",
                    }
                ]
            }
        ],
        downloads={"https://download/cross-mismatch-1": {"content": b"abcdef"}},
        run_ingest=False,
    )
    engine = ingest_engine_fixture()
    crash_injection_fixture.during_cross_pool_copy()
    try:
        engine.process_batch(
            candidates=list(polled.staged_candidates),
            accepted_root=config.core.accepted_path,
            storage_template=config.core.storage_template,
            staging_on_same_pool=False,
            quarantine_dir=polled.quarantine_root,
        )
    except RuntimeError:
        pass

    assert polled.registry_harness.accepted_rows() == []


def test_collision_safe_destination_generation_remains_deterministic(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "collision-a",
                        "name": "same.heic",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/collision-a",
                    }
                ]
            }
        ],
        downloads={"https://download/collision-a": {"content": b"AAAAA"}},
        storage_template="{yyyy}/{mm}/fixed-{original}",
    )
    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "collision-b",
                        "name": "same.heic",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/collision-b",
                    }
                ]
            }
        ],
        downloads={"https://download/collision-b": {"content": b"BBBBB"}},
        storage_template="{yyyy}/{mm}/fixed-{original}",
    )

    paths = [first.ingest_result.outcomes[0].destination_path, second.ingest_result.outcomes[0].destination_path]
    assert paths[0] != paths[1]


def test_registry_rejected_hash_is_discarded_without_accept_commit(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    file_bytes = b"reject-me"
    temp_path = registry_fixture.db_path.parent / "reject.bin"
    temp_path.write_bytes(file_bytes)
    digest = sha256_file(temp_path)
    registry_fixture.registry.create_or_update_file(
        sha256=digest,
        size_bytes=len(file_bytes),
        status="rejected",
        original_filename="reject.bin",
        current_path=None,
    )
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "reject-1",
                        "name": "reject.bin",
                        "file": {},
                        "size": len(file_bytes),
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/reject-1",
                    }
                ]
            }
        ],
        downloads={"https://download/reject-1": {"content": file_bytes}},
    )

    assert result.ingest_result.outcomes[0].action == "discard_rejected"
    assert result.registry_harness.accepted_rows() == []


def test_registry_purged_hash_is_not_reaccepted(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    file_bytes = b"purged!"
    temp_path = registry_fixture.db_path.parent / "purged.bin"
    temp_path.write_bytes(file_bytes)
    digest = sha256_file(temp_path)
    registry_fixture.registry.create_or_update_file(
        sha256=digest,
        size_bytes=len(file_bytes),
        status="purged",
        original_filename="purged.bin",
        current_path=None,
    )
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "purged-1",
                        "name": "purged.bin",
                        "file": {},
                        "size": len(file_bytes),
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/purged-1",
                    }
                ]
            }
        ],
        downloads={"https://download/purged-1": {"content": file_bytes}},
    )

    assert result.ingest_result.outcomes[0].action == "discard_purged"
    assert result.registry_harness.accepted_rows() == []
