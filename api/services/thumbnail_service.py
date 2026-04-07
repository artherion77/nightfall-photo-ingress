"""Thumbnail generation and cache management service."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile


class ThumbnailNotFoundError(LookupError):
    """Raised when a thumbnail cannot be served for a valid 404 condition."""


class ThumbnailGenerationError(RuntimeError):
    """Raised when thumbnail generation fails due to server-side write/runtime errors."""


class ThumbnailService:
    """Provides thumbnail fetch/generate and cache lifecycle operations."""

    def __init__(self, registry_conn: sqlite3.Connection, cache_root: Path):
        self.conn = registry_conn
        self.cache_root = Path(cache_root)

    def get_or_generate(self, sha256: str) -> bytes:
        """Return cached thumbnail bytes or generate them on first request."""

        source_path = self._resolve_pending_source_path(sha256)
        cache_path = self._cache_path_for_sha(sha256)

        if cache_path.exists():
            if cache_path.stat().st_size == 0:
                raise ThumbnailNotFoundError("Thumbnail unavailable for this item")
            return cache_path.read_bytes()

        if not source_path.exists():
            raise ThumbnailNotFoundError("Source file missing")

        return self._generate_thumbnail(sha256=sha256, source_path=source_path, cache_path=cache_path)

    def purge_cache_entry(self, sha256: str) -> bool:
        """Best-effort removal of cached thumbnail or marker for one sha256."""

        cache_path = self._cache_path_for_sha(sha256)
        if not cache_path.exists():
            return False

        cache_path.unlink(missing_ok=True)
        self._prune_empty_parents(cache_path.parent)
        return True

    def garbage_collect(self) -> dict[str, int | str]:
        """Remove cache entries whose sha256 is no longer pending."""

        pending_shas = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT sha256 FROM files WHERE status = 'pending'"
            ).fetchall()
        }

        scanned = 0
        removed = 0
        kept = 0

        if self.cache_root.exists():
            for path in self.cache_root.rglob("*.webp"):
                if not path.is_file():
                    continue
                scanned += 1
                sha256 = path.stem
                if sha256 not in pending_shas:
                    path.unlink(missing_ok=True)
                    self._prune_empty_parents(path.parent)
                    removed += 1
                else:
                    kept += 1

        return {
            "cache_root": str(self.cache_root),
            "scanned": scanned,
            "removed": removed,
            "kept": kept,
        }

    def _resolve_pending_source_path(self, sha256: str) -> Path:
        row = self.conn.execute(
            "SELECT status, current_path FROM files WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if row is None:
            raise ThumbnailNotFoundError("Item not found")

        status_value = row["status"] if isinstance(row, sqlite3.Row) else row[0]
        current_path = row["current_path"] if isinstance(row, sqlite3.Row) else row[1]

        if status_value != "pending":
            raise ThumbnailNotFoundError("Item is not pending")
        if not current_path:
            raise ThumbnailNotFoundError("Pending item has no current_path")

        return Path(str(current_path))

    def _cache_path_for_sha(self, sha256: str) -> Path:
        return self.cache_root / sha256[:2] / sha256[:4] / f"{sha256}.webp"

    def _generate_thumbnail(self, *, sha256: str, source_path: Path, cache_path: Path) -> bytes:
        # Import lazily so CLI commands that do not need imaging do not require PIL import.
        from PIL import Image, ImageOps, UnidentifiedImageError

        try:
            with Image.open(source_path) as src:
                image = ImageOps.exif_transpose(src)
                image.load()

                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")

                resample = (
                    Image.Resampling.LANCZOS
                    if hasattr(Image, "Resampling")
                    else Image.LANCZOS
                )
                image.thumbnail((480, 480), resample)

                cache_path.parent.mkdir(parents=True, exist_ok=True)

                tmp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        prefix=f"{sha256}.",
                        suffix=".tmp",
                        dir=cache_path.parent,
                        delete=False,
                    ) as tmp_file:
                        tmp_path = Path(tmp_file.name)

                    image.save(tmp_path, format="WEBP", quality=80)
                    os.replace(tmp_path, cache_path)
                except OSError as exc:
                    if tmp_path is not None and tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)
                    raise ThumbnailGenerationError("Thumbnail generation failed") from exc

        except (UnidentifiedImageError, ValueError, OSError) as exc:
            self._write_zero_marker(cache_path)
            raise ThumbnailNotFoundError("File is not a decodable image") from exc

        return cache_path.read_bytes()

    def _write_zero_marker(self, cache_path: Path) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(b"")
        except OSError:
            # Marker write is best-effort; serve 404 even if marker cannot be created.
            return

    def _prune_empty_parents(self, start: Path) -> None:
        current = start
        while current != self.cache_root and current != current.parent:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent