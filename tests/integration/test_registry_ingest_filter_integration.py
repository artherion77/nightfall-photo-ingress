"""Registry-ingest filter integration gate criteria.

These tests codify the business boundary agreed in design reviews:
- SHA-256 remains canonical in the registry.
- Advisory SHA1 data is non-canonical until verified.
- Accepted/rejected/purged registry truth drives ingest outcomes.
"""

from __future__ import annotations

import sqlite3

from nightfall_photo_ingress.sync_import import EXTERNAL_HASH_CACHE_SCOPE


def test_known_rejected_metadata_match_discards_without_accepting(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    seed = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "reject-seed-1",
                        "name": "IMG_REJECT.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/reject-seed-1",
                    }
                ]
            }
        ],
        downloads={"https://download/reject-seed-1": {"content": b"seed-000"}},
    )
    seed_hash = seed.ingest_result.outcomes[0].sha256
    assert seed_hash is not None

    registry_fixture.registry.transition_status(
        sha256=seed_hash,
        new_status="rejected",
        reason="integration-test-transition",
        actor="tests",
    )

    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "reject-seed-1",
                        "name": "IMG_REJECT.HEIC",
                        "file": {},
                        "size": 8,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/reject-seed-2",
                    }
                ]
            }
        ],
        downloads={"https://download/reject-seed-2": {"content": b"seed-000"}},
    )

    assert result.ingest_result is not None
    assert result.ingest_result.outcomes[0].action == "discard_rejected"
    assert result.ingest_result.outcomes[0].prefilter_hit is True
    assert result.ingest_result.accepted_count == 0


def test_known_purged_metadata_match_discards_without_accepting(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    seed = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "purged-seed-1",
                        "name": "IMG_PURGED.HEIC",
                        "file": {},
                        "size": 9,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/purged-seed-1",
                    }
                ]
            }
        ],
        downloads={"https://download/purged-seed-1": {"content": b"purged-01"}},
    )
    seed_hash = seed.ingest_result.outcomes[0].sha256
    assert seed_hash is not None

    registry_fixture.registry.transition_status(
        sha256=seed_hash,
        new_status="purged",
        reason="integration-test-transition",
        actor="tests",
    )

    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "purged-seed-1",
                        "name": "IMG_PURGED.HEIC",
                        "file": {},
                        "size": 9,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/purged-seed-2",
                    }
                ]
            }
        ],
        downloads={"https://download/purged-seed-2": {"content": b"purged-01"}},
    )

    assert result.ingest_result is not None
    assert result.ingest_result.outcomes[0].action == "discard_purged"
    assert result.ingest_result.outcomes[0].prefilter_hit is True
    assert result.ingest_result.accepted_count == 0


def test_size_drift_for_same_onedrive_id_forces_prefilter_miss(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "drift-size-1",
                        "name": "IMG_DRIFT.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/drift-size-a",
                    }
                ]
            }
        ],
        downloads={"https://download/drift-size-a": {"content": b"AAAAAA"}},
    )
    assert first.ingest_result is not None

    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "drift-size-1",
                        "name": "IMG_DRIFT.HEIC",
                        "file": {},
                        "size": 7,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/drift-size-b",
                    }
                ]
            }
        ],
        downloads={"https://download/drift-size-b": {"content": b"BBBBBBB"}},
    )

    assert second.ingest_result is not None
    assert second.ingest_result.prefilter_hit_count == 0
    assert second.ingest_result.prefilter_miss_count == 1
    assert second.ingest_result.outcomes[0].prefilter_hit is False


def test_modified_time_drift_for_same_onedrive_id_forces_prefilter_miss(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "drift-mtime-1",
                        "name": "IMG_DRIFT_MTIME.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/drift-mtime-a",
                    }
                ]
            }
        ],
        downloads={"https://download/drift-mtime-a": {"content": b"CCCCCC"}},
    )
    assert first.ingest_result is not None

    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "drift-mtime-1",
                        "name": "IMG_DRIFT_MTIME.HEIC",
                        "file": {},
                        "size": 6,
                        "lastModifiedDateTime": "2026-04-01T10:11:13Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/drift-mtime-b",
                    }
                ]
            }
        ],
        downloads={"https://download/drift-mtime-b": {"content": b"DDDDDD"}},
    )

    assert second.ingest_result is not None
    assert second.ingest_result.prefilter_hit_count == 0
    assert second.ingest_result.prefilter_miss_count == 1
    assert second.ingest_result.outcomes[0].prefilter_hit is False


def test_acceptance_history_blocks_reingest_even_if_queue_file_is_moved(
    poll_and_ingest_fixture,
) -> None:
    first = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "moved-queue-1",
                        "name": "IMG_MOVED_QUEUE.HEIC",
                        "file": {},
                        "size": 11,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/moved-queue-a",
                    }
                ]
            }
        ],
        downloads={"https://download/moved-queue-a": {"content": b"queue-moved"}},
    )

    assert first.ingest_result is not None
    first_outcome = first.ingest_result.outcomes[0]
    assert first_outcome.destination_path is not None
    first_outcome.destination_path.unlink(missing_ok=True)

    second = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "moved-queue-1",
                        "name": "IMG_MOVED_QUEUE.HEIC",
                        "file": {},
                        "size": 11,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/moved-queue-b",
                    }
                ]
            }
        ],
        downloads={"https://download/moved-queue-b": {"content": b"queue-moved"}},
    )

    assert second.ingest_result is not None
    assert second.ingest_result.outcomes[0].action == "discard_accepted"
    assert second.ingest_result.outcomes[0].prefilter_hit is True
    assert second.registry_harness.registry.acceptance_count(
        sha256=first_outcome.sha256 or ""
    ) == 1


def test_advisory_sha1_cache_is_non_canonical_without_verified_sha256(
    poll_and_ingest_fixture,
    registry_fixture,
) -> None:
    # Advisory-only cache seed (no canonical SHA-256 verification).
    registry_fixture.registry.upsert_external_hash_cache(
        account_name=EXTERNAL_HASH_CACHE_SCOPE,
        source_relpath="2026/04/IMG_ADVISORY.HEIC",
        hash_algo="sha1",
        hash_value="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        verified_sha256=None,
    )

    result = poll_and_ingest_fixture(
        pages=[
            {
                "value": [
                    {
                        "id": "advisory-1",
                        "name": "IMG_ADVISORY.HEIC",
                        "file": {},
                        "size": 12,
                        "lastModifiedDateTime": "2026-04-01T10:11:12Z",
                        "parentReference": {"path": "/drive/root:/Camera Roll/2026"},
                        "@microsoft.graph.downloadUrl": "https://download/advisory-1",
                    }
                ]
            }
        ],
        downloads={"https://download/advisory-1": {"content": b"advisory-raw"}},
    )

    assert result.ingest_result is not None
    assert result.ingest_result.outcomes[0].action == "accepted"
    assert result.ingest_result.prefilter_hit_count == 0

    conn = sqlite3.connect(result.registry_harness.db_path)
    try:
        rows = conn.execute(
            """
            SELECT hash_algo, hash_value, verified_sha256
            FROM external_hash_cache
            WHERE account_name = ? AND source_relpath = ?
            ORDER BY hash_algo
            """,
            (EXTERNAL_HASH_CACHE_SCOPE, "2026/04/IMG_ADVISORY.HEIC"),
        ).fetchall()
    finally:
        conn.close()

    # Original advisory row remains advisory and unverified.
    assert rows == [
        ("sha1", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", None),
    ]
