"""Module 5 registry tests for live photo pairs."""

from __future__ import annotations

from pathlib import Path

from nightfall_photo_ingress.domain.registry import Registry


def _new_registry(tmp_path: Path) -> Registry:
    reg = Registry(tmp_path / "registry.db")
    reg.initialize()
    return reg


def test_live_photo_pair_upsert_and_get(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    photo_sha = "a" * 64
    video_sha = "b" * 64
    reg.create_or_update_file(sha256=photo_sha, size_bytes=100, status="accepted")
    reg.create_or_update_file(sha256=video_sha, size_bytes=200, status="accepted")

    reg.upsert_live_photo_pair(
        pair_id="pair-1",
        account="primary",
        stem="IMG_0001",
        photo_sha256=photo_sha,
        video_sha256=video_sha,
        status="paired",
    )

    row = reg.get_live_photo_pair(pair_id="pair-1")
    assert row is not None
    assert row.account == "primary"
    assert row.stem == "IMG_0001"
    assert row.status == "paired"


def test_rejection_propagates_across_pair_members(tmp_path: Path) -> None:
    reg = _new_registry(tmp_path)

    photo_sha = "c" * 64
    video_sha = "d" * 64
    reg.create_or_update_file(sha256=photo_sha, size_bytes=100, status="accepted")
    reg.create_or_update_file(sha256=video_sha, size_bytes=200, status="accepted")
    reg.upsert_live_photo_pair(
        pair_id="pair-2",
        account="primary",
        stem="IMG_0010",
        photo_sha256=photo_sha,
        video_sha256=video_sha,
    )

    reg.apply_live_photo_pair_status(
        pair_id="pair-2",
        new_status="rejected",
        reason="operator_live_photo_reject",
        actor="cli",
    )

    photo = reg.get_file(sha256=photo_sha)
    video = reg.get_file(sha256=video_sha)
    pair = reg.get_live_photo_pair(pair_id="pair-2")

    assert photo is not None
    assert video is not None
    assert pair is not None
    assert photo.status == "rejected"
    assert video.status == "rejected"
    assert pair.status == "rejected"
