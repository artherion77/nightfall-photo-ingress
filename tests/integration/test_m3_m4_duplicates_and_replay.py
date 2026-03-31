"""Duplicate delta, replay, and multi-cycle idempotency integration tests."""

from __future__ import annotations


def test_duplicate_delta_items_reduce_to_single_ingest_effect(
    poll_and_ingest_fixture,
) -> None:
    duplicate_item = {
        "id": "dup-1",
        "name": "IMG_DUP.HEIC",
        "file": {},
        "size": 4,
        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
        "@microsoft.graph.downloadUrl": "https://download/dup-1",
    }
    result = poll_and_ingest_fixture(
        pages=[{"value": [duplicate_item, duplicate_item]}],
        downloads={"https://download/dup-1": {"content": b"data"}},
    )

    assert result.poll_result.candidate_count == 1
    assert result.ingest_result.accepted_count == 1
    assert len(result.registry_harness.accepted_rows()) == 1
    assert len(result.registry_harness.terminal_events()) == 1


def test_replayed_delta_page_on_next_poll_does_not_duplicate_accepted_content(
    poll_and_ingest_fixture,
) -> None:
    pages = [
        {
            "value": [
                {
                    "id": "replay-1",
                    "name": "IMG_REPLAY.HEIC",
                    "file": {},
                    "size": 6,
                    "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                    "@microsoft.graph.downloadUrl": "https://download/replay-1-a",
                }
            ]
        }
    ]
    first = poll_and_ingest_fixture(
        pages=pages,
        downloads={"https://download/replay-1-a": {"content": b"repeat"}},
    )
    second = poll_and_ingest_fixture(
        pages=pages,
        downloads={"https://download/replay-1-a": {"content": b"repeat"}},
    )

    assert first.ingest_result.accepted_count == 1
    assert second.ingest_result.accepted_count == 0
    assert second.ingest_result.outcomes[0].action in {"discard_accepted", "discard_rejected", "discard_purged"}
