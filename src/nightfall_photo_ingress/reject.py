"""Operator rejection workflows for CLI and trash-triggered processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .domain.registry import Registry, RegistryError
from .domain.storage import (
    are_on_same_filesystem,
    choose_collision_safe_destination,
    commit_pending_to_accepted,
    ensure_within_root,
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
        pending_root=app_config.core.pending_path,
        accepted_root=app_config.core.accepted_path,
        rejected_root=app_config.core.rejected_path,
        rejected_storage_template=app_config.core.storage_template,
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

    context = registry.get_accept_context(sha256=normalized_sha)
    if context is None:
        raise RejectFlowError(
            f"Cannot accept sha256 without origin context: {sha256}"
        )

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
    _require_path_within_root(
        path=source_path,
        root=app_config.core.pending_path,
        error_message=(
            f"Unsafe accept source outside pending root: {source_path} "
            f"(pending_root={app_config.core.pending_path})"
        ),
    )
    relative = render_storage_relative_path(
        storage_template=app_config.core.accepted_storage_template,
        sha256=normalized_sha,
        original_filename=record.original_filename or normalized_sha,
        modified_time_iso=context.modified_time,
    )
    destination = choose_collision_safe_destination(
        app_config.core.accepted_path / relative
    )
    same_filesystem = are_on_same_filesystem(source_path, destination.parent)
    commit_pending_to_accepted(
        source_path=source_path,
        destination_path=destination,
        same_pool=same_filesystem,
        destination_root=app_config.core.accepted_path,
    )
    registry.finalize_accept_from_pending(
        sha256=normalized_sha,
        new_path=str(destination),
        account=context.account,
        source_path=context.source_path,
        actor=actor,
        reason=reason or "operator_accept",
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
        try:
            ensure_within_root(current, app_config.core.rejected_path)
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RejectFlowError(
                f"Unsafe purge path outside rejected root: {current}"
            ) from exc
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
            pending_root=app_config.core.pending_path,
            accepted_root=app_config.core.accepted_path,
            rejected_root=app_config.core.rejected_path,
            rejected_storage_template=app_config.core.storage_template,
            incoming_path=trash_file,
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
    pending_root: Path,
    accepted_root: Path,
    rejected_root: Path,
    rejected_storage_template: str,
    incoming_path: Path | None = None,
) -> RejectResult:
    """Persist reject transition for known or newly discovered content."""

    record = registry.get_file(sha256=sha256)
    removed_paths: list[str] = []

    if record is None:
        retained_path = _move_physical_to_rejected(
            source_path=incoming_path,
            sha256=sha256,
            original_filename=fallback_original_filename,
            modified_time=_utc_now_iso(),
            rejected_root=rejected_root,
            rejected_storage_template=rejected_storage_template,
        )
        registry.create_or_update_file(
            sha256=sha256,
            size_bytes=fallback_size_bytes,
            status="rejected",
            original_filename=fallback_original_filename,
            current_path=str(retained_path) if retained_path is not None else None,
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
        removed_paths.extend(
            _move_to_rejected_folder(
                registry,
                pair.photo_sha256,
                pending_root,
                accepted_root,
                rejected_root,
                rejected_storage_template,
            )
        )
        removed_paths.extend(
            _move_to_rejected_folder(
                registry,
                pair.video_sha256,
                pending_root,
                accepted_root,
                rejected_root,
                rejected_storage_template,
            )
        )
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

    removed_paths.extend(
        _move_to_rejected_folder(
            registry,
            sha256,
            pending_root,
            accepted_root,
            rejected_root,
            rejected_storage_template,
        )
    )
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


def _move_to_rejected_folder(
    registry: Registry,
    sha256: str,
    pending_root: Path,
    accepted_root: Path,
    rejected_root: Path,
    rejected_storage_template: str,
) -> list[str]:
    """Move current queue file to rejected folder and update stored path pointer."""

    record = registry.get_file(sha256=sha256)
    if record is None or record.current_path is None:
        return []

    source = Path(record.current_path)
    if not source.exists():
        registry.clear_current_path(sha256=sha256)
        return []

    if not _is_within_root(source, pending_root) and not _is_within_root(source, accepted_root):
        raise RejectFlowError(
            "Unsafe reject source outside managed queue roots: "
            f"{source} (pending_root={pending_root}, accepted_root={accepted_root})"
        )

    context = registry.get_accept_context(sha256=sha256)
    modified_time = context.modified_time if context is not None else _utc_now_iso()
    rejected_dest = _move_physical_to_rejected(
        source_path=source,
        sha256=sha256,
        original_filename=record.original_filename,
        modified_time=modified_time,
        rejected_root=rejected_root,
        rejected_storage_template=rejected_storage_template,
    )
    if rejected_dest is None:
        return []
    registry.update_current_path(sha256=sha256, new_path=str(rejected_dest))
    return [str(source)]


def _move_physical_to_rejected(
    *,
    source_path: Path | None,
    sha256: str,
    original_filename: str | None,
    modified_time: str,
    rejected_root: Path,
    rejected_storage_template: str,
) -> Path | None:
    """Move one file into rejected retention path and return final destination."""

    if source_path is None or not source_path.exists():
        return None

    relative = render_storage_relative_path(
        storage_template=rejected_storage_template,
        sha256=sha256,
        original_filename=original_filename or source_path.name,
        modified_time_iso=modified_time,
    )
    destination = choose_collision_safe_destination(rejected_root / relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_path.replace(destination)
    return destination


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        ensure_within_root(path, root)
    except Exception:
        return False
    return True


def _require_path_within_root(*, path: Path, root: Path, error_message: str) -> None:
    try:
        ensure_within_root(path, root)
    except Exception as exc:
        raise RejectFlowError(error_message) from exc