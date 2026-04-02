"""Operator rejection workflows for CLI and trash-triggered processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .domain.registry import Registry, RegistryError
from .domain.storage import (
    choose_collision_safe_destination,
    commit_pending_to_accepted,
    render_storage_relative_path,
    sha256_file,
)

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


@dataclass(frozen=True)
class AcceptResult:
    """Result for a single explicit accept action."""

    sha256: str
    action: str
    destination_path: str


@dataclass(frozen=True)
class PurgeResult:
    """Result for a single explicit purge action."""

    sha256: str
    action: str
    purged_path: str | None

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
        rejected_root=app_config.core.rejected_path,
    )


def accept_sha256(
    app_config: AppConfig,
    *,
    sha256: str,
    reason: str | None,
    actor: str,
) -> AcceptResult:
    """Move a pending file to accepted and update registry."""

    normalized_sha = sha256.strip().lower()
    if len(normalized_sha) != 64 or any(char not in "0123456789abcdef" for char in normalized_sha):
        raise RejectFlowError(f"Invalid SHA-256: {sha256}")

    registry = Registry(app_config.core.registry_path)
    registry.initialize()

    record = registry.get_file(sha256=normalized_sha)
    if record is None:
        raise RejectFlowError(f"Unknown SHA-256: {sha256}")
    if record.status != "pending":
        raise RejectFlowError(
            f"Cannot accept sha256 with status '{record.status}': expected 'pending'"
        )
    if record.current_path is None:
        raise RejectFlowError(f"No current_path for pending sha256: {sha256}")

    source_path = Path(record.current_path)
    relative = render_storage_relative_path(
        storage_template=app_config.core.accepted_storage_template,
        sha256=normalized_sha,
        original_filename=record.original_filename or normalized_sha,
        modified_time_iso="1970-01-01T00:00:00+00:00",
    )
    destination = choose_collision_safe_destination(
        app_config.core.accepted_path / relative
    )
    commit_pending_to_accepted(
        source_path=source_path,
        destination_path=destination,
        same_pool=app_config.core.staging_on_same_pool,
        destination_root=app_config.core.accepted_path,
    )
    registry.finalize_accept_from_pending(
        sha256=normalized_sha,
        current_path=str(destination),
        reason=reason or "operator_accept",
        actor=actor,
    )
    return AcceptResult(
        sha256=normalized_sha,
        action="accepted",
        destination_path=str(destination),
    )


def purge_sha256(
    app_config: AppConfig,
    *,
    sha256: str,
    reason: str | None,
    actor: str,
) -> PurgeResult:
    """Delete a rejected file and transition registry to purged."""

    normalized_sha = sha256.strip().lower()
    if len(normalized_sha) != 64 or any(char not in "0123456789abcdef" for char in normalized_sha):
        raise RejectFlowError(f"Invalid SHA-256: {sha256}")

    registry = Registry(app_config.core.registry_path)
    registry.initialize()

    record = registry.get_file(sha256=normalized_sha)
    if record is None:
        raise RejectFlowError(f"Unknown SHA-256: {sha256}")
    if record.status != "rejected":
        raise RejectFlowError(
            f"Cannot purge sha256 with status '{record.status}': expected 'rejected'"
        )

    purged_path: str | None = None
    if record.current_path is not None:
        current = Path(record.current_path)
        if current.exists():
            current.unlink(missing_ok=True)
            purged_path = str(current)

    try:
        registry.finalize_purge_from_rejected(
            sha256=normalized_sha,
            reason=reason or "cli_purge",
            actor=actor,
        )
    except RegistryError as exc:
        raise RejectFlowError(str(exc)) from exc

    return PurgeResult(
        sha256=normalized_sha,
        action="purged",
        purged_path=purged_path,
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
            rejected_root=app_config.core.rejected_path,
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
    rejected_root: Path,
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
        removed_paths.extend(_move_to_rejected_folder(registry, pair.photo_sha256, rejected_root))
        removed_paths.extend(_move_to_rejected_folder(registry, pair.video_sha256, rejected_root))
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

    removed_paths.extend(_move_to_rejected_folder(registry, sha256, rejected_root))
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


def _move_to_rejected_folder(registry: Registry, sha256: str, rejected_root: Path) -> list[str]:
    """Move current queue file to rejected folder and update stored path pointer."""

    record = registry.get_file(sha256=sha256)
    if record is None or record.current_path is None:
        return []

    source = Path(record.current_path)
    if not source.exists():
        registry.clear_current_path(sha256=sha256)
        return []

    original_filename = record.original_filename or sha256[:8]
    rejected_filename = f"{sha256[:8]}-{original_filename}"
    rejected_dest = choose_collision_safe_destination(rejected_root / rejected_filename)
    rejected_dest.parent.mkdir(parents=True, exist_ok=True)
    source.replace(rejected_dest)
    registry.update_current_path(sha256=sha256, new_path=str(rejected_dest))
    return [str(source)]