"""Operator rejection workflows for CLI and trash-triggered processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .domain.registry import Registry, RegistryError
from .domain.storage import sha256_file


class RejectFlowError(RuntimeError):
    """Raised when operator rejection workflows fail."""


@dataclass(frozen=True)
class RejectResult:
    """Result for a single explicit reject action."""

    sha256: str
    action: str
    removed_paths: tuple[str, ...]


@dataclass(frozen=True)
class TrashProcessResult:
    """Summary for one trash processing run."""

    processed_files: int
    rejected_files: int
    noop_files: int
    unknown_files: int
    removed_paths: tuple[str, ...]


def reject_sha256(
    app_config: AppConfig,
    *,
    sha256: str,
    reason: str | None,
    actor: str,
) -> RejectResult:
    """Apply an idempotent reject transition for one SHA-256."""

    normalized_sha = sha256.strip().lower()
    if len(normalized_sha) != 64 or any(char not in "0123456789abcdef" for char in normalized_sha):
        raise RejectFlowError(f"Invalid SHA-256: {sha256}")

    registry = Registry(app_config.core.registry_path)
    registry.initialize()
    return _apply_reject(
        registry,
        sha256=normalized_sha,
        reason=reason or "cli_reject",
        actor=actor,
        fallback_original_filename=None,
        fallback_size_bytes=0,
    )


def process_trash(app_config: AppConfig) -> TrashProcessResult:
    """Hash files from trash path and persist idempotent reject outcomes."""

    registry = Registry(app_config.core.registry_path)
    registry.initialize()

    trash_root = app_config.core.trash_path
    trash_root.mkdir(parents=True, exist_ok=True)

    processed_files = 0
    rejected_files = 0
    noop_files = 0
    unknown_files = 0
    removed_paths: list[str] = []

    for trash_file in sorted(path for path in trash_root.rglob("*") if path.is_file()):
        processed_files += 1
        trash_sha = sha256_file(trash_file)
        result = _apply_reject(
            registry,
            sha256=trash_sha,
            reason="trash_reject",
            actor="trash_watch",
            fallback_original_filename=trash_file.name,
            fallback_size_bytes=trash_file.stat().st_size,
        )
        trash_file.unlink(missing_ok=True)
        removed_paths.append(str(trash_file))
        removed_paths.extend(result.removed_paths)
        if result.action == "rejected_unknown":
            unknown_files += 1
            rejected_files += 1
        elif result.action == "reject_noop_already_rejected":
            noop_files += 1
        else:
            rejected_files += 1

    return TrashProcessResult(
        processed_files=processed_files,
        rejected_files=rejected_files,
        noop_files=noop_files,
        unknown_files=unknown_files,
        removed_paths=tuple(dict.fromkeys(removed_paths)),
    )


def _apply_reject(
    registry: Registry,
    *,
    sha256: str,
    reason: str,
    actor: str,
    fallback_original_filename: str | None,
    fallback_size_bytes: int,
) -> RejectResult:
    """Persist reject transition for known or newly discovered content."""

    record = registry.get_file(sha256=sha256)
    removed_paths: list[str] = []

    if record is None:
        registry.create_or_update_file(
            sha256=sha256,
            size_bytes=fallback_size_bytes,
            status="rejected",
            original_filename=fallback_original_filename,
            current_path=None,
        )
        registry.append_audit_event(
            sha256=sha256,
            action="rejected",
            reason=reason,
            actor=actor,
        )
        return RejectResult(
            sha256=sha256,
            action="rejected_unknown",
            removed_paths=tuple(),
        )

    pair = registry.get_live_photo_pair_for_member(sha256=sha256)
    if pair is not None and pair.status != "rejected":
        removed_paths.extend(_remove_current_path_if_present(registry, pair.photo_sha256))
        removed_paths.extend(_remove_current_path_if_present(registry, pair.video_sha256))
        registry.apply_live_photo_pair_status(
            pair_id=pair.pair_id,
            new_status="rejected",
            reason=reason,
            actor=actor,
        )
        return RejectResult(
            sha256=sha256,
            action="rejected_pair",
            removed_paths=tuple(dict.fromkeys(removed_paths)),
        )

    if record.status == "rejected":
        registry.append_audit_event(
            sha256=sha256,
            action="reject_noop_already_rejected",
            reason=reason,
            actor=actor,
        )
        return RejectResult(
            sha256=sha256,
            action="reject_noop_already_rejected",
            removed_paths=tuple(),
        )

    removed_paths.extend(_remove_current_path_if_present(registry, sha256))
    try:
        registry.transition_status(
            sha256=sha256,
            new_status="rejected",
            reason=reason,
            actor=actor,
        )
    except RegistryError as exc:
        raise RejectFlowError(str(exc)) from exc

    return RejectResult(
        sha256=sha256,
        action="rejected_existing",
        removed_paths=tuple(dict.fromkeys(removed_paths)),
    )


def _remove_current_path_if_present(registry: Registry, sha256: str) -> list[str]:
    """Delete current queue file if it exists and clear stored path pointer."""

    record = registry.get_file(sha256=sha256)
    if record is None or record.current_path is None:
        return []

    current_path = Path(record.current_path)
    if current_path.exists():
        current_path.unlink(missing_ok=True)
    registry.clear_current_path(sha256=sha256)
    return [str(current_path)]