"""Schema drift and malformed metadata integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations

import pytest

from nightfall_photo_ingress.domain.ingest import IngestError

def test_missing_required_fields_rejected_at_boundary_before_ingest(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "missing-url-1",
                        "name": "BROKEN.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                    }
                ]
            }
        ],
        downloads={
            "https://graph.microsoft.com/v1.0/me/drive/items/missing-url-1": {
                "status_code": 404,
                "content": b"{}",
            }
        },
        run_ingest=False,
    )

    assert result.poll_result.candidate_count == 1
    assert result.poll_result.ghost_item_count >= 1
    assert result.registry_harness.metadata_rows() == []
    assert result.registry_harness.terminal_events() == []


def test_missing_item_id_rejected_at_boundary_before_ingest(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "name": "BROKEN_NO_ID.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/no-id",
                    }
                ]
            }
        ],
        downloads={},
        run_ingest=False,
    )

    assert result.poll_result.candidate_count == 0
    assert result.poll_result.delta_anomaly_count >= 1
    assert result.registry_harness.metadata_rows() == []
    assert result.registry_harness.terminal_events() == []


def test_invalid_schema_version_is_rejected_before_ingest_processing(
    poll_and_ingest_fixture,
) -> None:
    polled = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "schema-version-1",
                        "name": "SCHEMA.HEIC",
                        "file": {},
                        "size": 5,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/schema-version-1",
                    }
                ]
            }
        ],
        downloads={"https://download/schema-version-1": {"content": b"12345"}},
        run_ingest=False,
    )

    with pytest.raises(IngestError, match="Incompatible ingest input schema version"):
        poll_and_ingest_fixture(
            app_config=polled.app_config,
            pages=[{"value": []}],
            downloads={},
            run_ingest=True,
            input_schema_version=999,
        )


def test_malformed_size_and_timestamp_produce_drift_classification_not_silent_accept(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "drift-1",
                        "name": "BROKEN.HEIC",
                        "file": {},
                        "size": "abc",
                        "lastModifiedDateTime": "not-a-date",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/drift-1",
                    }
                ]
            }
        ],
        downloads={"https://download/drift-1": {"content": b"abc"}},
        run_ingest=False,
    )

    assert result.poll_result.candidate_count == 0
    assert result.poll_result.delta_anomaly_count >= 1
    assert result.registry_harness.file_origins() == []


def test_prefilter_false_positive_protection_sampling_or_policy_path(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "stale-1",
                        "name": "IMG_STALE.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/stale-1-a",
                    }
                ]
            }
        ],
        downloads={"https://download/stale-1-a": {"content": b"aaaaaa"}},
    )
    accepted_hash = first.ingest_result.outcomes[0].sha256
    registry_fixture.registry.upsert_metadata_index(
        account="lisa",
        onedrive_id="stale-1",
        size_bytes=6,
        modified_time="2026-04-01T10:11:12+00:00",
        sha256=accepted_hash or "",
    )

    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "stale-1",
                        "name": "IMG_STALE.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/stale-1-b",
                    }
                ]
            }
        ],
        downloads={"https://download/stale-1-b": {"content": b"bbbbbb"}},
    )

    assert second.ingest_result.outcomes[0].action != "discard_accepted"
