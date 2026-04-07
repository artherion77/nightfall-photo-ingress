"""Thumbnail API integration tests for Phase 1.5 Chunk P1.5-2."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests.integration.api.support import auth_headers


def _thumb_headers(api_token: str) -> dict[str, str]:
    return auth_headers(api_token)


def _cache_path(cache_root: Path, sha256: str) -> Path:
    return cache_root / sha256[:2] / sha256[:4] / f"{sha256}.webp"


def _write_image(path: Path, *, fmt: str, color: tuple[int, int, int] = (20, 40, 200)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 800), color=color)
    image.save(path, format=fmt)


@pytest.mark.anyio
async def test_thumbnail_returns_webp_for_pending_jpeg(api_client, api_token: str, registry_conn, app_config) -> None:
    source = app_config.core.thumbnail_cache_path.parent / "sources" / "test_photo.jpg"
    _write_image(source, fmt="JPEG")
    registry_conn.execute(
        "UPDATE files SET current_path = ?, status = 'pending' WHERE sha256 = ?",
        (str(source), "abc123def456"),
    )
    registry_conn.commit()

    response = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=86400, immutable"
    assert response.headers["etag"] == '"thumb-abc123def456"'
    assert len(response.content) > 0


@pytest.mark.anyio
async def test_thumbnail_cache_hit_uses_existing_file(api_client, api_token: str, registry_conn, app_config) -> None:
    source = app_config.core.thumbnail_cache_path.parent / "sources" / "cache_hit.png"
    _write_image(source, fmt="PNG")
    registry_conn.execute(
        "UPDATE files SET current_path = ?, status = 'pending' WHERE sha256 = ?",
        (str(source), "abc123def456"),
    )
    registry_conn.commit()

    first = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )
    assert first.status_code == 200

    cache_path = _cache_path(app_config.core.thumbnail_cache_path, "abc123def456")
    assert cache_path.exists()
    first_mtime = cache_path.stat().st_mtime_ns

    second = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )
    assert second.status_code == 200
    assert second.content == first.content
    assert cache_path.stat().st_mtime_ns == first_mtime


@pytest.mark.anyio
async def test_thumbnail_404_for_missing_sha(api_client, api_token: str) -> None:
    response = await api_client.get(
        "/api/v1/thumbnails/not-found-sha",
        headers=_thumb_headers(api_token),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_thumbnail_404_for_non_pending_item(api_client, api_token: str, registry_conn, app_config) -> None:
    source = app_config.core.thumbnail_cache_path.parent / "sources" / "accepted.jpg"
    _write_image(source, fmt="JPEG")
    registry_conn.execute(
        "UPDATE files SET current_path = ?, status = 'accepted' WHERE sha256 = ?",
        (str(source), "abc123def456"),
    )
    registry_conn.commit()

    response = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_thumbnail_non_image_creates_marker_and_replays_404(api_client, api_token: str, registry_conn, app_config) -> None:
    source = app_config.core.thumbnail_cache_path.parent / "sources" / "not_image.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("not an image", encoding="utf-8")

    registry_conn.execute(
        "UPDATE files SET current_path = ?, status = 'pending' WHERE sha256 = ?",
        (str(source), "abc123def456"),
    )
    registry_conn.commit()

    first = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )
    assert first.status_code == 404

    marker_path = _cache_path(app_config.core.thumbnail_cache_path, "abc123def456")
    assert marker_path.exists()
    assert marker_path.stat().st_size == 0
    marker_mtime = marker_path.stat().st_mtime_ns

    second = await api_client.get(
        "/api/v1/thumbnails/abc123def456",
        headers=_thumb_headers(api_token),
    )
    assert second.status_code == 404
    assert marker_path.stat().st_mtime_ns == marker_mtime


@pytest.mark.anyio
async def test_thumbnail_requires_auth(api_client) -> None:
    response = await api_client.get("/api/v1/thumbnails/abc123def456")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_thumbnail_purged_on_accept_and_reject(api_client, api_token: str, app_config) -> None:
    accept_sha = "abc123def456"
    reject_sha = "xyz789uvw012"

    accept_cache = _cache_path(app_config.core.thumbnail_cache_path, accept_sha)
    reject_cache = _cache_path(app_config.core.thumbnail_cache_path, reject_sha)
    accept_cache.parent.mkdir(parents=True, exist_ok=True)
    reject_cache.parent.mkdir(parents=True, exist_ok=True)
    accept_cache.write_bytes(b"thumbnail-bytes")
    reject_cache.write_bytes(b"thumbnail-bytes")

    accept_headers = _thumb_headers(api_token)
    accept_headers["X-Idempotency-Key"] = "thumb-purge-accept-1"
    reject_headers = _thumb_headers(api_token)
    reject_headers["X-Idempotency-Key"] = "thumb-purge-reject-1"

    accept_response = await api_client.post(
        f"/api/v1/triage/{accept_sha}/accept",
        headers=accept_headers,
        json={"reason": "operator_accept"},
    )
    reject_response = await api_client.post(
        f"/api/v1/triage/{reject_sha}/reject",
        headers=reject_headers,
        json={"reason": "operator_reject"},
    )

    assert accept_response.status_code == 200
    assert reject_response.status_code == 200
    assert not accept_cache.exists()
    assert not reject_cache.exists()


@pytest.mark.anyio
async def test_thumbnail_gc_removes_orphans(registry_conn, app_config) -> None:
    from api.services.thumbnail_service import ThumbnailService

    pending_sha = "abc123def456"
    orphan_sha = "deadbeef0000"

    pending_cache = _cache_path(app_config.core.thumbnail_cache_path, pending_sha)
    orphan_cache = _cache_path(app_config.core.thumbnail_cache_path, orphan_sha)
    pending_cache.parent.mkdir(parents=True, exist_ok=True)
    orphan_cache.parent.mkdir(parents=True, exist_ok=True)
    pending_cache.write_bytes(b"ok")
    orphan_cache.write_bytes(b"stale")

    service = ThumbnailService(registry_conn, app_config.core.thumbnail_cache_path)
    result = service.garbage_collect()

    assert result["scanned"] >= 2
    assert result["removed"] >= 1
    assert pending_cache.exists()
    assert not orphan_cache.exists()
