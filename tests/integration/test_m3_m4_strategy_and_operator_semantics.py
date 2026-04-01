"""Chunk 4 strategy-scenario and operator-semantics integration coverage."""

from __future__ import annotations

import pytest

from nightfall_photo_ingress.adapters.onedrive.errors import DownloadError


def test_rename_as_delete_plus_create_keeps_only_created_candidate(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "old-item",
                        "name": "IMG_RENAME_OLD.HEIC",
                        "deleted": {},
                    },
                    {
                        "id": "new-item",
                        "name": "IMG_RENAME_NEW.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/rename-create-new",
                    },
                ]
            }
        ],
        downloads={"https://download/rename-create-new": {"content": b"abcdef"}},
    )

    assert result.poll_result.candidate_count == 1
    assert result.ingest_result is not None
    assert result.ingest_result.accepted_count == 1
    origins = result.registry_harness.file_origins()
    assert len(origins) == 1
    assert origins[0]["onedrive_id"] == "new-item"


def test_explicit_ghost_item_boundary_is_counted_without_ingest_side_effects(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    item_id = "ghost-item-1"
    metadata_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}"

    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": item_id,
                        "name": "IMG_GHOST.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ghost-item",
                    }
                ]
            }
        ],
        downloads={
            "https://download/ghost-item": {"status_code": 404, "content": b""},
            metadata_url: {"status_code": 404, "content": b"{}"},
        },
        run_ingest=False,
    )

    reasons = dict(result.poll_result.ghost_reason_counts)
    assert result.poll_result.candidate_count == 1
    assert len(result.poll_result.downloaded_paths) == 0
    assert result.poll_result.ghost_item_count >= 1
    assert reasons.get("ghost_item_not_found_on_refresh", 0) >= 1
    assert registry_fixture.accepted_rows() == []


def test_stale_or_resurrected_item_anomaly_is_visible_and_last_event_wins(
    poll_and_ingest_fixture,
) -> None:
    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "resurrect-1",
                        "name": "IMG_OLD.HEIC",
                        "file": {},
                        "size": 4,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/resurrect-old",
                    }
                ]
            },
            {
                "value": [
                    {
                        "id": "resurrect-1",
                        "name": "IMG_NEW.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:22Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/resurrect-new",
                    }
                ]
            },
        ],
        downloads={"https://download/resurrect-new": {"content": b"newest"}},
    )

    anomaly_reasons = dict(result.poll_result.delta_anomaly_reason_counts)
    assert result.poll_result.candidate_count == 1
    assert anomaly_reasons.get("delta_replayed_item_id", 0) >= 1
    assert result.ingest_result is not None
    assert result.ingest_result.outcomes[0].action == "accepted"


def test_corrupted_download_stream_is_distinct_from_truncated_size_mismatch(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    with pytest.raises(RuntimeError, match="corrupted stream"):
        poll_and_ingest_fixture(
            pages=[
                {
                    "value": [
                        {
                            "id": "corrupt-1",
                            "name": "IMG_CORRUPT.HEIC",
                            "file": {},
                            "size": 8,
                            "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                            "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                            "@microsoft.graph.downloadUrl": "https://download/corrupt-1",
                        }
                    ]
                }
            ],
            downloads={
                "https://download/corrupt-1": {
                    "chunks": [b"1234"],
                    "iter_error": RuntimeError("corrupted stream"),
                }
            },
            run_ingest=False,
        )

    with pytest.raises(DownloadError, match="Downloaded byte count did not match expected size"):
        poll_and_ingest_fixture(
            pages=[
                {
                    "value": [
                        {
                            "id": "truncated-distinct-1",
                            "name": "IMG_TRUNC.HEIC",
                            "file": {},
                            "size": 8,
                            "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                            "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                            "@microsoft.graph.downloadUrl": "https://download/truncated-distinct-1",
                        }
                    ]
                }
            ],
            downloads={
                "https://download/truncated-distinct-1": {
                    "chunks": [b"123", b"45"],
                    "repeat": 4,
                }
            },
            run_ingest=False,
        )

    assert registry_fixture.accepted_rows() == []


def test_operator_outcomes_are_distinguishable_and_recovery_summary_reconciles(
    poll_and_ingest_fixture,
    ingest_engine_fixture,
    crash_injection_fixture,
    registry_fixture,
    audit_reader_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "ops-accepted",
                        "name": "OPS_A.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ops-accepted",
                    }
                ]
            }
        ],
        downloads={"https://download/ops-accepted": {"content": b"accept"}},
    )
    accepted_hash = first.ingest_result.outcomes[0].sha256 or ""

    duplicate = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "ops-accepted",
                        "name": "OPS_A.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ops-duplicate",
                    }
                ]
            }
        ],
        downloads={"https://download/ops-duplicate": {"content": b"accept"}},
    )

    registry_fixture.registry.transition_status(
        sha256=accepted_hash,
        new_status="rejected",
        reason="operator_reject",
        actor="test_suite",
    )

    mixed = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "ops-rejected",
                        "name": "OPS_R.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ops-rejected",
                    },
                    {
                        "id": "ops-zero",
                        "name": "OPS_ZERO.HEIC",
                        "file": {},
                        "size": 0,
                        "lastModifiedDateTime": "2026-04-01T10:11:14Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ops-zero",
                    },
                ]
            }
        ],
        downloads={
            "https://download/ops-rejected": {"content": b"accept"},
            "https://download/ops-zero": {"content": b""},
        },
        zero_byte_policy="quarantine",
    )

    polled = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "ops-replay",
                        "name": "OPS_REPLAY.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:15Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/ops-replay",
                    }
                ]
            }
        ],
        downloads={"https://download/ops-replay": {"content": b"recover!"}},
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
    replay_summary = engine.replay_interrupted_operations()

    actions = set(audit_reader_fixture.terminal_actions())
    assert {"accepted", "discard_accepted", "discard_rejected", "quarantine_zero_byte"}.issubset(actions)
    assert all(actor == "ingest_pipeline" for actor in audit_reader_fixture.terminal_actors())

    mixed_events = mixed.registry_harness.terminal_events()
    mixed_batch_id = mixed_events[-1]["batch_run_id"]
    mixed_batch_events = [row for row in mixed_events if row["batch_run_id"] == mixed_batch_id]
    assert len(mixed_batch_events) == len(mixed.ingest_result.outcomes)
    assert {row["action"] for row in mixed_batch_events} == {out.action for out in mixed.ingest_result.outcomes}

    assert replay_summary["interrupted_total"] >= 1
    assert len(replay_summary["unresolved_op_ids"]) == replay_summary["interrupted_total"]
    assert replay_summary["quarantined_destinations"] >= 1
    assert duplicate.ingest_result.outcomes[0].action == "discard_accepted"
