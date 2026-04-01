"""Module 5 live photo pairing tests."""

from __future__ import annotations

import time

import pytest

from nightfall_photo_ingress.live_photo import (
    DeferredPairQueue,
    LivePhotoCandidate,
    LivePhotoError,
    LivePhotoHeuristics,
)


def _candidate(*, onedrive_id: str, filename: str, captured_at: str) -> LivePhotoCandidate:
    return LivePhotoCandidate(
        account="primary",
        onedrive_id=onedrive_id,
        filename=filename,
        captured_at=captured_at,
    )


def test_pair_detection_by_exact_stem_and_tolerance_defaults() -> None:
    queue = DeferredPairQueue(LivePhotoHeuristics())
    photo = _candidate(
        onedrive_id="od-photo",
        filename="IMG_0001.HEIC",
        captured_at="2026-03-31T12:00:00Z",
    )
    video = _candidate(
        onedrive_id="od-video",
        filename="IMG_0001.MOV",
        captured_at="2026-03-31T12:00:02Z",
    )

    assert queue.ingest(photo) is None
    pair = queue.ingest(video)

    assert pair is not None
    assert pair.stem == "IMG_0001"
    assert pair.photo_onedrive_id == "od-photo"
    assert pair.video_onedrive_id == "od-video"


def test_late_arrival_pairing_resolves_deferred_candidate() -> None:
    queue = DeferredPairQueue(LivePhotoHeuristics())
    video_first = _candidate(
        onedrive_id="od-video",
        filename="IMG_0100.MOV",
        captured_at="2026-03-31T12:00:00Z",
    )
    photo_late = _candidate(
        onedrive_id="od-photo",
        filename="IMG_0100.HEIC",
        captured_at="2026-03-31T12:00:01Z",
    )

    assert queue.ingest(video_first) is None
    diagnostics = queue.unresolved_diagnostics()
    assert len(diagnostics) == 1
    assert diagnostics[0].component == "video"

    pair = queue.ingest(photo_late)
    assert pair is not None
    assert pair.photo_onedrive_id == "od-photo"
    assert pair.video_onedrive_id == "od-video"
    assert queue.unresolved_diagnostics() == ()


def test_unresolved_candidate_aging_and_pop() -> None:
    queue = DeferredPairQueue(LivePhotoHeuristics())
    assert (
        queue.ingest(
            _candidate(
                onedrive_id="od-photo",
                filename="IMG_7777.HEIC",
                captured_at="2026-03-31T12:00:00Z",
            )
        )
        is None
    )

    time.sleep(1)
    removed = queue.pop_aged_unresolved(max_age_seconds=1)
    assert len(removed) == 1
    assert removed[0].stem == "IMG_7777"
    assert queue.unresolved_diagnostics() == ()


def test_v1_policy_rejects_non_default_runtime_heuristics() -> None:
    with pytest.raises(LivePhotoError):
        DeferredPairQueue(
            LivePhotoHeuristics(
                capture_tolerance_seconds=5,
            )
        )
