"""CLI entrypoint for nightfall photo ingress.

Module 0 exposes command stubs only. Business logic is intentionally deferred
to later modules in the approved implementation roadmap.
"""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from . import __version__
from .config import AppConfig, load_config, validate_config_file
from .logging_bootstrap import configure_logging
from .adapters.onedrive.auth import AuthError, OneDriveAuthClient
from .adapters.onedrive.client import GraphError, poll_accounts
from .reject import RejectFlowError, process_trash, reject_sha256
from .status import write_status_snapshot
from .sync_import import SyncImportError, run_sync_import

LOGGER = logging.getLogger(__name__)


def _emit_status_snapshot(*, state: str, command: str, success: bool, details: dict[str, object]) -> None:
    """Best-effort status export that must never break the CLI."""

    try:
        write_status_snapshot(
            state=state,
            command=command,
            success=success,
            details=details,
        )
    except OSError as exc:
        LOGGER.warning("status snapshot write failed", extra={"error": str(exc), "command": command})


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""

    parser = argparse.ArgumentParser(prog="nightfall-photo-ingress")
    parser.add_argument(
        "--log-mode",
        choices=["json", "human"],
        default="human",
        help="Select output logging format.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    auth = subparsers.add_parser("auth-setup", help="Initialize account authentication.")
    auth.add_argument("--account", help="Optional account name.", default=None)
    auth.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    auth.set_defaults(handler=_cmd_auth_setup)

    poll = subparsers.add_parser("poll", help="Run one poll cycle.")
    poll.add_argument("--account", help="Optional account name.", default=None)
    poll.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    poll.set_defaults(handler=_cmd_poll)

    reject = subparsers.add_parser("reject", help="Reject a hash permanently.")
    reject.add_argument("sha256", nargs="?", help="SHA-256 to reject.")
    reject.add_argument("--reason", default=None)
    reject.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    reject.set_defaults(handler=_cmd_reject)

    process_trash = subparsers.add_parser("process-trash", help="Process trash directory.")
    process_trash.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    process_trash.set_defaults(handler=_cmd_process_trash)

    sync_import = subparsers.add_parser(
        "sync-import",
        help="Import advisory hashes from a library share.",
    )
    sync_import.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    sync_import.add_argument("--dry-run", action="store_true", help="Show what would be imported.")
    sync_import.set_defaults(handler=_cmd_sync_import)

    config_check = subparsers.add_parser("config-check", help="Validate configuration file.")
    config_check.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    config_check.set_defaults(handler=_cmd_config_check)

    return parser


def _cmd_auth_setup(args: argparse.Namespace) -> int:
    """Run OneDrive device-code authentication setup for one account."""

    try:
        app_config = load_config(args.path)
        account = _resolve_target_account(app_config, args.account)
        OneDriveAuthClient().auth_setup(account)
        LOGGER.info("auth setup completed", extra={"account": account.name})
        return 0
    except (AuthError, ValueError) as exc:
        LOGGER.error(str(exc))
        return 2


def _cmd_poll(args: argparse.Namespace) -> int:
    """Run OneDrive account polling and staging download for the OneDrive client."""

    try:
        app_config = load_config(args.path)
        results = poll_accounts(app_config, account_name=args.account)
        for result in results:
            LOGGER.info(
                "poll completed",
                extra={
                    "account": result.account_name,
                    "candidates": result.candidate_count,
                    "downloaded": len(result.downloaded_paths),
                },
            )
        _emit_status_snapshot(
            state="healthy",
            command="poll",
            success=True,
            details={
                "accounts": [result.account_name for result in results],
                "candidate_count": sum(result.candidate_count for result in results),
                "downloaded_count": sum(len(result.downloaded_paths) for result in results),
            },
        )
        return 0
    except (GraphError, AuthError, ValueError) as exc:
        LOGGER.error(str(exc))
        _emit_status_snapshot(
            state="ingest_error",
            command="poll",
            success=False,
            details={"error": str(exc)},
        )
        return 2


def _cmd_reject(args: argparse.Namespace) -> int:
    """Reject one known or newly supplied file hash permanently."""

    try:
        app_config = load_config(args.path)
        result = reject_sha256(
            app_config,
            sha256=args.sha256 or "",
            reason=args.reason,
            actor="cli",
        )
        LOGGER.info(
            "reject completed",
            extra={
                "sha256": result.sha256,
                "action": result.action,
                "removed_paths": list(result.removed_paths),
            },
        )
        _emit_status_snapshot(
            state="healthy",
            command="reject",
            success=True,
            details={"sha256": result.sha256, "action": result.action},
        )
        return 0
    except (RejectFlowError, ValueError) as exc:
        LOGGER.error(str(exc))
        _emit_status_snapshot(
            state="ingest_error",
            command="reject",
            success=False,
            details={"error": str(exc)},
        )
        return 2


def _cmd_process_trash(args: argparse.Namespace) -> int:
    """Process all files currently present in configured trash path."""

    try:
        app_config = load_config(args.path)
        result = process_trash(app_config)
        LOGGER.info(
            "process-trash completed",
            extra={
                "processed_files": result.processed_files,
                "rejected_files": result.rejected_files,
                "noop_files": result.noop_files,
                "unknown_files": result.unknown_files,
                "removed_paths": list(result.removed_paths),
            },
        )
        _emit_status_snapshot(
            state="healthy",
            command="process-trash",
            success=True,
            details={
                "processed_files": result.processed_files,
                "rejected_files": result.rejected_files,
                "noop_files": result.noop_files,
                "unknown_files": result.unknown_files,
            },
        )
        return 0
    except (RejectFlowError, ValueError) as exc:
        LOGGER.error(str(exc))
        _emit_status_snapshot(
            state="ingest_error",
            command="process-trash",
            success=False,
            details={"error": str(exc)},
        )
        return 2


def _cmd_sync_import(args: argparse.Namespace) -> int:
    """Import advisory permanent-library hashes into the registry cache."""

    try:
        app_config = load_config(args.path)
        summary = run_sync_import(app_config, dry_run=args.dry_run)
        LOGGER.info(
            "sync-import completed",
            extra={
                "dry_run": summary.dry_run,
                "directories_scanned": summary.directories_scanned,
                "cache_files_used": summary.cache_files_used,
                "directories_rehashed": summary.directories_rehashed,
                "imported_rows": summary.imported_rows,
                "skipped_rows": summary.skipped_rows,
                "invalid_lines": summary.invalid_lines,
            },
        )
        _emit_status_snapshot(
            state="healthy",
            command="sync-import",
            success=True,
            details={
                "dry_run": summary.dry_run,
                "directories_scanned": summary.directories_scanned,
                "cache_files_used": summary.cache_files_used,
                "directories_rehashed": summary.directories_rehashed,
                "imported_rows": summary.imported_rows,
                "skipped_rows": summary.skipped_rows,
                "invalid_lines": summary.invalid_lines,
            },
        )
        return 0
    except (SyncImportError, ValueError) as exc:
        LOGGER.error(str(exc))
        _emit_status_snapshot(
            state="ingest_error",
            command="sync-import",
            success=False,
            details={"error": str(exc)},
        )
        return 2


def _cmd_config_check(args: argparse.Namespace) -> int:
    """Validate the configuration file and print diagnostics on failure."""

    errors = validate_config_file(args.path)
    if not errors:
        LOGGER.info("config file validation successful", extra={"path": args.path})
        _emit_status_snapshot(
            state="healthy",
            command="config-check",
            success=True,
            details={"path": args.path},
        )
        return 0

    LOGGER.error("config file validation failed", extra={"path": args.path})
    for err in errors:
        print(f"ERROR: {err}")
    _emit_status_snapshot(
        state="degraded",
        command="config-check",
        success=False,
        details={"path": args.path, "errors": errors},
    )
    return 2


def _resolve_target_account(app_config: AppConfig, requested_name: str | None):
    """Resolve the account target for auth setup.

    If no account is requested, exactly one enabled account must exist.
    """

    enabled = app_config.ordered_enabled_accounts()
    if requested_name:
        for account in enabled:
            if account.name == requested_name:
                return account
        raise ValueError(f"Enabled account not found: {requested_name}")

    if len(enabled) == 1:
        return enabled[0]

    raise ValueError("Multiple enabled accounts found; pass --account")


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code."""

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    configure_logging(args.log_mode)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return int(handler(args))
