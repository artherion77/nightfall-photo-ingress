"""Operator-facing summary and audit integration tests for the OneDrive client to ingest boundary."""

from __future__ import annotations


def test_operator_summary_matches_registry_storage_and_audit_counts(
    poll_and_ingest_fixture,
    registry_fixture,
    caplog,
) -> None:
    caplog.set_level("INFO")
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "summary-accepted",
                        "name": "accept.heic",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/summary-accepted",
                    }
                ]
            }
        ],
        downloads={"https://download/summary-accepted": {"content": b"accept"}},
    )
    accepted_hash = first.ingest_result.outcomes[0].sha256
    registry_fixture.registry.transition_status(
        sha256=accepted_hash or "",
        new_status="rejected",
        reason="operator_reject",
        actor="test_suite",
    )
    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "summary-accepted",
                        "name": "accept.heic",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/summary-rejected",
                    },
                    {
                        "id": "summary-zero",
                        "name": "zero.heic",
                        "file": {},
                        "size": 0,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/summary-zero",
                    },
                ]
            }
        ],
        downloads={
            "https://download/summary-rejected": {"content": b"accept"},
            "https://download/summary-zero": {"content": b""},
        },
        zero_byte_policy="quarantine",
    )

    assert second.ingest_result.accepted_count == 0
    assert second.ingest_result.discarded_count >= 1
    assert second.ingest_result.zero_byte_quarantine_count == 1
    assert len(second.registry_harness.terminal_events()) >= 3
    assert any(record.msg == "onedrive_trace" for record in caplog.records)


def test_terminal_audit_sequence_is_monotonic_per_batch(
    poll_and_ingest_fixture,
    audit_reader_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "audit-1",
                        "name": "one.heic",
                        "file": {},
                        "size": 3,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/audit-1",
                    },
                    {
                        "id": "audit-2",
                        "name": "two.heic",
                        "file": {},
                        "size": 3,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/audit-2",
                    },
                ]
            }
        ],
        downloads={
            "https://download/audit-1": {"content": b"one"},
            "https://download/audit-2": {"content": b"two"},
        },
    )

    events = audit_reader_fixture.terminal_events()
    assert len(events) == 2
    assert [row["sequence_no"] for row in events] == sorted(row["sequence_no"] for row in events)
    assert len({row["batch_run_id"] for row in events}) == 1
