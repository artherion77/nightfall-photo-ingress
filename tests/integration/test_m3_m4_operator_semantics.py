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

    second_actions = [outcome.action for outcome in second.ingest_result.outcomes]
    assert second.ingest_result.accepted_count == 0
    assert second.ingest_result.discarded_count >= 1
    assert second.ingest_result.zero_byte_quarantine_count == 1
    assert "discard_rejected" in second_actions
    assert "quarantine_zero_byte" in second_actions
    assert second.registry_harness.accepted_rows() == [
        {
            "sha256": accepted_hash,
            "account": "lisa",
            "source_path": "/Camera Roll/2026",
        }
    ]
    terminal_events = second.registry_harness.terminal_events()
    assert len(terminal_events) == 3
    batch_ids = {
        row["batch_run_id"]
        for row in terminal_events
        if row["action"] in {"discard_rejected", "quarantine_zero_byte"}
    }
    assert len(batch_ids) == 1
    assert all(row["actor"] == "ingest_pipeline" for row in terminal_events)
    assert {row["action"] for row in terminal_events} >= {
        "accepted",
        "discard_rejected",
        "quarantine_zero_byte",
    }
    assert any(path for path in second.quarantine_root.rglob("*") if path.is_file())
    assert len([p for p in second.accepted_root.rglob("*") if p.is_file()]) == 1
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
