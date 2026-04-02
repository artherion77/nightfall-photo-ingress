"""Integration coverage for the full pending->accepted/rejected->purged lifecycle."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.reject import accept_sha256, purge_sha256, reject_sha256


def test_full_lifecycle_pending_accept_reject_purge(poll_and_ingest_fixture) -> None:
    cycle = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "lifecycle-1",
                        "name": "IMG_LIFECYCLE.HEIC",
                        "file": {},
                        "size": 9,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/lifecycle-1",
                    }
                ]
            }
        ],
        downloads={"https://download/lifecycle-1": {"content": b"lifecycle"}},
    )

    assert cycle.ingest_result is not None
    assert cycle.ingest_result.pending_count == 1
    first = cycle.ingest_result.outcomes[0]
    assert first.action == "pending"
    sha = first.sha256 or ""

    accept_result = accept_sha256(
        cycle.app_config,
        sha256=sha,
        reason="operator_accept",
        actor="integration_test",
    )
    accepted_path = Path(accept_result.destination_path)
    assert accept_result.action == "accepted"
    assert accepted_path.exists()
    assert accepted_path.is_file()
    assert str(accepted_path).startswith(str(cycle.app_config.core.accepted_path))
    assert cycle.registry_harness.registry.acceptance_count(sha256=sha) == 1

    reject_result = reject_sha256(
        cycle.app_config,
        sha256=sha,
        reason="operator_reject",
        actor="integration_test",
    )
    assert reject_result.action in {"rejected_existing", "rejected_pair"}
    row_after_reject = cycle.registry_harness.registry.get_file(sha256=sha)
    assert row_after_reject is not None
    assert row_after_reject.status == "rejected"
    assert row_after_reject.current_path is not None
    rejected_path = Path(row_after_reject.current_path)
    assert rejected_path.exists()
    assert str(rejected_path).startswith(str(cycle.app_config.core.rejected_path))

    purge_result = purge_sha256(
        cycle.app_config,
        sha256=sha,
        reason="operator_purge",
        actor="integration_test",
    )
    assert purge_result.action == "purged"
    if purge_result.purged_path is not None:
        assert not Path(purge_result.purged_path).exists()

    row_after_purge = cycle.registry_harness.registry.get_file(sha256=sha)
    assert row_after_purge is not None
    assert row_after_purge.status == "purged"
    assert row_after_purge.current_path is None
