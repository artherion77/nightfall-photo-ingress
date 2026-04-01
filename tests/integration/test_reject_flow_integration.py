"""Integration tests for Module 7 operator reject flows."""

from __future__ import annotations

from nightfall_photo_ingress.reject import reject_sha256, process_trash


def test_reject_then_reupload_blocks_ingest_via_real_reject_path(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "reject-flow-1",
                        "name": "IMG_REJECT.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/reject-flow-1-a",
                    }
                ]
            }
        ],
        downloads={"https://download/reject-flow-1-a": {"content": b"accept"}},
    )

    accepted_hash = first.ingest_result.outcomes[0].sha256
    result = reject_sha256(
        first.app_config,
        sha256=accepted_hash or "",
        reason="operator_reject",
        actor="cli",
    )
    assert result.action == "rejected_existing"

    second = poll_and_ingest_fixture(
        app_config=first.app_config,
        pages=[
            {
                "value": [
                    {
                        "id": "reject-flow-1",
                        "name": "IMG_REJECT.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/reject-flow-1-b",
                    }
                ]
            }
        ],
        downloads={"https://download/reject-flow-1-b": {"content": b"accept"}},
    )

    assert second.ingest_result is not None
    assert second.ingest_result.outcomes[0].action == "discard_rejected"


def test_batch_trash_processing_rejects_multiple_queue_files(
    poll_and_ingest_fixture,
) -> None:
    initial = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "trash-batch-1",
                        "name": "A.HEIC",
                        "file": {},
                        "size": 3,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/trash-batch-1",
                    },
                    {
                        "id": "trash-batch-2",
                        "name": "B.HEIC",
                        "file": {},
                        "size": 3,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/trash-batch-2",
                    },
                ]
            }
        ],
        downloads={
            "https://download/trash-batch-1": {"content": b"one"},
            "https://download/trash-batch-2": {"content": b"two"},
        },
    )

    accepted_files = sorted(path for path in initial.accepted_root.rglob("*") if path.is_file())
    assert len(accepted_files) == 2
    trash_root = initial.app_config.core.trash_path
    trash_root.mkdir(parents=True, exist_ok=True)
    (trash_root / "reject-a.HEIC").write_bytes(b"one")
    (trash_root / "reject-b.HEIC").write_bytes(b"two")

    summary = process_trash(initial.app_config)

    assert summary.processed_files == 2
    assert summary.rejected_files == 2
    assert not any(path for path in initial.accepted_root.rglob("*") if path.is_file())
    assert not any(path for path in trash_root.rglob("*") if path.is_file())
