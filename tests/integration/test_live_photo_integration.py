"""Module 5 integration tests for live photo pairing behavior."""

from __future__ import annotations


def test_ingest_mixed_live_photo_and_standalone_assets_creates_pair_record(
    poll_and_ingest_fixture,
) -> None:
    pages = [
        {
            "value": [
                {
                    "id": "lp-photo-1",
                    "name": "IMG_2001.HEIC",
                    "file": {},
                        "size": 8,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/lp-photo-1",
                },
                {
                    "id": "lp-video-1",
                    "name": "IMG_2001.MOV",
                    "file": {},
                    "size": 8,
                    "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/lp-video-1",
                },
                {
                    "id": "standalone-1",
                    "name": "IMG_3001.HEIC",
                    "file": {},
                    "size": 9,
                    "lastModifiedDateTime": "2026-04-01T10:11:14Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/standalone-1",
                },
            ]
        }
    ]

    result = poll_and_ingest_fixture(
        pages=pages,
        downloads={
            "https://download/lp-photo-1": {"content": b"heic-one"},
            "https://download/lp-video-1": {"content": b"mov-one!"},
            "https://download/standalone-1": {"content": b"heic-two!"},
        },
    )

    assert result.ingest_result is not None
    assert result.ingest_result.accepted_count == 3

    pairs = result.registry_harness.query_all(
        "SELECT account, stem, status FROM live_photo_pairs ORDER BY pair_id"
    )
    assert len(pairs) == 1
    assert pairs[0]["account"] == "lisa"
    assert pairs[0]["stem"] == "IMG_2001"
    assert pairs[0]["status"] == "paired"


def test_reupload_of_rejected_live_photo_pair_is_blocked(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "lp-photo-2",
                        "name": "IMG_9001.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/lp-photo-2-a",
                    },
                    {
                        "id": "lp-video-2",
                        "name": "IMG_9001.MOV",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/lp-video-2-a",
                    },
                ]
            }
        ],
        downloads={
            "https://download/lp-photo-2-a": {"content": b"alpha111"},
            "https://download/lp-video-2-a": {"content": b"beta2222"},
        },
    )

    pairs = first.registry_harness.query_all(
        "SELECT pair_id FROM live_photo_pairs ORDER BY pair_id"
    )
    assert len(pairs) == 1

    first.registry_harness.registry.apply_live_photo_pair_status(
        pair_id=pairs[0]["pair_id"],
        new_status="rejected",
        reason="operator_reject_pair",
        actor="integration_test",
    )

    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "lp-photo-2",
                        "name": "IMG_9001.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/lp-photo-2-b",
                    },
                    {
                        "id": "lp-video-2",
                        "name": "IMG_9001.MOV",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/lp-video-2-b",
                    },
                ]
            }
        ],
        downloads={
            "https://download/lp-photo-2-b": {"content": b"alpha111"},
            "https://download/lp-video-2-b": {"content": b"beta2222"},
        },
    )

    assert second.ingest_result is not None
    actions = tuple(outcome.action for outcome in second.ingest_result.outcomes)
    assert actions == ("discard_rejected", "discard_rejected")
    assert second.ingest_result.accepted_count == 0
