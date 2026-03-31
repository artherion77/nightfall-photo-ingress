"""Storage helpers for ingest pipeline workflows.

This module handles destination path rendering and durable staging-to-accepted
commit behavior for both same-pool and cross-pool cases.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class StorageError(RuntimeError):
    """Raised when file persistence operations fail."""


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


@dataclass(frozen=True)
class CommitResult:
    """Result object returned by durable commit operations."""

    destination_path: Path
    bytes_written: int
    method: str


def sha256_file(path: Path, chunk_size: int = 64 * 1024) -> str:
    """Return SHA-256 for a file using streaming reads."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_filename(value: str) -> str:
    """Normalize potentially unsafe filenames for queue storage."""

    cleaned = _SAFE_NAME_RE.sub("_", value).strip("._ ")
    return cleaned or "unnamed"


def render_storage_relative_path(
    *,
    storage_template: str,
    sha256: str,
    original_filename: str,
    modified_time_iso: str,
) -> Path:
    """Render a relative path from storage template placeholders.

    Supported placeholders:
    - {yyyy}
    - {mm}
    - {sha8}
    - {original}
    """

    timestamp = _parse_timestamp(modified_time_iso)
    safe_name = sanitize_filename(original_filename)
    rendered = storage_template
    rendered = rendered.replace("{yyyy}", f"{timestamp.year:04d}")
    rendered = rendered.replace("{mm}", f"{timestamp.month:02d}")
    rendered = rendered.replace("{sha8}", sha256[:8])
    rendered = rendered.replace("{original}", safe_name)

    path = Path(rendered)
    if path.is_absolute():
        raise StorageError("Storage template must render a relative path")
    if any(part in {"..", ""} for part in path.parts):
        raise StorageError("Storage template renders unsafe path components")
    return path


def choose_collision_safe_destination(base_path: Path) -> Path:
    """Return a unique destination path by adding numeric suffix on conflicts."""

    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    for index in range(1, 10_000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise StorageError(f"Unable to find collision-safe destination for {base_path}")


def commit_staging_to_accepted(
    *,
    source_path: Path,
    destination_path: Path,
    staging_on_same_pool: bool,
    destination_root: Path | None = None,
) -> CommitResult:
    """Persist one staged file into accepted queue storage safely.

    On same pool, uses atomic rename. On cross-pool, copies metadata, verifies
    byte count and SHA-256, then unlinks source only after verification.
    """

    if not source_path.exists():
        raise StorageError(f"Staged source missing: {source_path}")

    if destination_root is not None:
        _ensure_within_root(destination_path, destination_root)

    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if staging_on_same_pool:
        source_path.replace(destination_path)
        _fsync_path(destination_path)
        _fsync_parent_dir(destination_path)
        written = destination_path.stat().st_size
        return CommitResult(
            destination_path=destination_path,
            bytes_written=written,
            method="rename",
        )

    tmp_destination = destination_path.with_suffix(destination_path.suffix + ".tmp")
    shutil.copy2(source_path, tmp_destination)

    source_size = source_path.stat().st_size
    copied_size = tmp_destination.stat().st_size
    if source_size != copied_size:
        tmp_destination.unlink(missing_ok=True)
        raise StorageError(
            f"Cross-pool copy size mismatch: source={source_size} copied={copied_size}"
        )

    source_hash = sha256_file(source_path)
    copied_hash = sha256_file(tmp_destination)
    if source_hash != copied_hash:
        tmp_destination.unlink(missing_ok=True)
        raise StorageError("Cross-pool copy hash mismatch")

    _fsync_path(tmp_destination)
    tmp_destination.replace(destination_path)
    _fsync_parent_dir(destination_path)
    source_path.unlink(missing_ok=True)
    return CommitResult(
        destination_path=destination_path,
        bytes_written=copied_size,
        method="copy_verify_unlink",
    )


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO timestamp values with safe UTC fallback."""

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.now(timezone.utc)


def _ensure_within_root(destination_path: Path, destination_root: Path) -> None:
    """Reject destination paths that escape the configured accepted root."""

    resolved_root = destination_root.resolve()
    resolved_destination = destination_path.resolve(strict=False)
    if not str(resolved_destination).startswith(str(resolved_root) + os.sep) and resolved_destination != resolved_root:
        raise StorageError(
            f"Destination escapes accepted root: destination={resolved_destination} root={resolved_root}"
        )


def _fsync_path(path: Path) -> None:
    """Flush file contents and metadata to disk for durability."""

    try:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StorageError(f"Failed to fsync file: {path}: {exc}") from exc


def _fsync_parent_dir(path: Path) -> None:
    """Flush parent directory metadata for rename/copy durability."""

    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise StorageError(f"Failed to fsync parent directory: {path.parent}: {exc}") from exc
