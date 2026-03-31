"""Happy-path and prefilter integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations

from nightfall_photo_ingress.storage import sha256_file


def test_e2e_single_new_photo_same_pool_accepts_cleanly(
    poll_and_ingest_fixture,
    audit_reader_fixture,
) -> None:
    pages = [
        {
            "value": [
                {
                    "id": "item-1",
                    "name": "IMG_0001.HEIC",
                    "file": {},
                    "size": 7,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/item-1",
                }
            ]
        }
    ]
    result = poll_and_ingest_fixture(
        pages=pages,
        downloads={"https://download/item-1": {"content": b"payload"}},
    )

    assert result.poll_result.candidate_count == 1
    assert result.ingest_result is not None
    assert result.ingest_result.accepted_count == 1
    outcome = result.ingest_result.outcomes[0]
    assert outcome.action == "accepted"
    assert outcome.destination_path is not None and outcome.destination_path.exists()
    assert result.registry_harness.registry.get_file(sha256=outcome.sha256 or "") is not None
    assert len(result.registry_harness.metadata_rows()) == 1
    assert len(result.registry_harness.file_origins()) == 1
    assert len(result.registry_harness.accepted_rows()) == 1
    assert audit_reader_fixture.terminal_actions() == ("accepted",)


def test_e2e_single_new_photo_cross_pool_accepts_with_copy_verify(
    app_config_fixture,
    poll_and_ingest_fixture,
    fs_snapshot_fixture,
) -> None:
    config = app_config_fixture(core_overrides={"staging_on_same_pool": False})
    pages = [
        {
            "value": [
                {
                    "id": "item-2",
                    "name": "IMG_0002.MOV",
                    "file": {},
                    "size": 8,
                    "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/item-2",
                }
            ]
        }
    ]
    result = poll_and_ingest_fixture(
        app_config=config,
        pages=pages,
        downloads={"https://download/item-2": {"content": b"movbytes"}},
    )

    assert result.ingest_result is not None
    outcome = result.ingest_result.outcomes[0]
    assert outcome.action == "accepted"
    assert outcome.destination_path is not None
    assert outcome.destination_path.read_bytes() == b"movbytes"
    assert fs_snapshot_fixture(config.core.staging_path / "lisa") == (
        "_lifecycle.journal.jsonl",
        "_quarantine/",
    )


def test_prefilter_hit_skips_hashing_for_known_metadata_match(
    poll_and_ingest_fixture,
) -> None:
    initial_pages = [
        {
            "value": [
                {
                    "id": "prefilter-1",
                    "name": "IMG_0100.HEIC",
                    "file": {},
                    "size": 10,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/prefilter-1-a",
                }
            ]
        }
    ]
    first = poll_and_ingest_fixture(
        pages=initial_pages,
        downloads={"https://download/prefilter-1-a": {"content": b"abcdefghij"}},
    )
    assert first.ingest_result is not None
    accepted_hash = first.ingest_result.outcomes[0].sha256

    replay_pages = [
        {
            "value": [
                {
                    "id": "prefilter-1",
                    "name": "IMG_0100.HEIC",
                    "file": {},
                    "size": 10,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/prefilter-1-b",
                }
            ]
        }
    ]
    second = poll_and_ingest_fixture(
        pages=replay_pages,
        downloads={"https://download/prefilter-1-b": {"content": b"abcdefghij"}},
    )

    assert second.ingest_result is not None
    assert second.ingest_result.prefilter_hit_count == 1
    assert second.ingest_result.outcomes[0].action == "discard_accepted"
    assert second.ingest_result.outcomes[0].prefilter_hit is True
    assert second.registry_harness.registry.acceptance_count(sha256=accepted_hash or "") == 1


def test_prefilter_miss_hashes_and_accepts_when_registry_unknown(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "miss-1",
                        "name": "MISS.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/miss-1",
                    }
                ]
            }
        ],
        downloads={"https://download/miss-1": {"content": b"12345"}},
    )

    assert result.ingest_result is not None
    assert result.ingest_result.prefilter_hit_count == 0
    assert result.ingest_result.prefilter_miss_count == 1
    outcome = result.ingest_result.outcomes[0]
    assert outcome.action == "accepted"
    assert result.registry_harness.registry.get_file(sha256=outcome.sha256 or "") is not None
