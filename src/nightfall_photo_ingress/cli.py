"""CLI entrypoint for nightfall photo ingress.

Module 0 exposes command stubs only. Business logic is intentionally deferred
to later modules in the approved implementation roadmap.
"""

from __future__ import annotations

import argparse
import configparser
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import httpx

from . import __version__
from .config import AccountConfig, AppConfig, load_config, validate_config_file
from .logging_bootstrap import configure_logging
from .adapters.onedrive.auth import AuthError, OneDriveAuthClient
from .adapters.onedrive.client import (
    GraphError,
    detect_account_locale,
    load_boundary_handoff_candidates,
    poll_accounts,
    resolve_camera_roll_path_for_onboarding,
)
from .domain.ingest import IngestDecisionEngine, IngestError, StagedCandidate
from .domain.registry import Registry, RegistryError
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
    auth.add_argument("--verbose", action="store_true", help="Show detailed Graph API calls and debug info.")
    auth.add_argument("--skip-discovery", action="store_true", help="Skip OneDrive path auto-discovery after auth.")
    auth.set_defaults(handler=_cmd_auth_setup)

    discover = subparsers.add_parser("discover-paths", help="Auto-discover OneDrive storage paths using cached token.")
    discover.add_argument("--account", help="Optional account name.", default=None)
    discover.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    discover.add_argument("--verbose", action="store_true", help="Show detailed Graph API calls and debug info.")
    discover.set_defaults(handler=_cmd_discover_paths)

    poll = subparsers.add_parser("poll", help="Run one poll cycle.")
    poll.add_argument("--account", help="Optional account name.", default=None)
    poll.add_argument("--path", default="/etc/nightfall/photo-ingress.conf")
    poll.add_argument("--verbose", action="store_true", help="Show detailed Graph API calls and progress trace info.")
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
        auth_client = OneDriveAuthClient()
        verbose = getattr(args, "verbose", False)
        
        token = auth_client.auth_setup(account)

        skip_discovery = getattr(args, "skip_discovery", False)
        if skip_discovery:
            LOGGER.info("auth setup completed (discovery skipped)", extra={"account": account.name})
            return 0

        return _run_discovery(account, auth_client, args.path, token.token, verbose)

    except AuthError as exc:
        # Log full error details including safe_hint for debugging
        LOGGER.error(str(exc), extra=exc.as_log_dict())
        return 2
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 2


def _cmd_discover_paths(args: argparse.Namespace) -> int:
    """Auto-discover OneDrive paths using a cached token for one account."""

    try:
        app_config = load_config(args.path)
        account = _resolve_target_account(app_config, args.account)
        auth_client = OneDriveAuthClient()
        verbose = getattr(args, "verbose", False)
        
        # Acquire token from cache (no interactive auth)
        token = auth_client.acquire_access_token(account)
        
        return _run_discovery(account, auth_client, args.path, token.token, verbose)
    except AuthError as exc:
        LOGGER.error(str(exc), extra=exc.as_log_dict())
        return 2
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 2


def _run_discovery(
    account: AccountConfig,
    auth_client: OneDriveAuthClient,
    config_path: str,
    access_token: str,
    verbose: bool,
) -> int:
    """Run path auto-discovery using a cached or fresh access token."""

    try:
        with httpx.Client() as client:
            detected_locale = detect_account_locale(
                account=account,
                access_token=access_token,
                http_client=client,
            )
        if detected_locale is not None:
            log_level = logging.INFO if verbose else logging.DEBUG
            LOGGER.log(
                log_level,
                "onedrive locale auto-detected",
                extra={"account": account.name, "locale": detected_locale},
            )
    except GraphError as exc:
        LOGGER.warning(
            "onedrive locale auto-detect failed",
            extra={
                "account": account.name,
                "error_code": exc.code,
            },
        )

    try:
        with httpx.Client() as client:
            path_resolution = resolve_camera_roll_path_for_onboarding(
                account=account,
                access_token=access_token,
                http_client=client,
            )

        if path_resolution.reason is not None:
            log_level = logging.INFO if verbose else logging.DEBUG
            LOGGER.log(
                log_level,
                "configured onedrive_root invalid; auto-discovery used",
                extra={
                    "account": account.name,
                    "configured_path": path_resolution.configured_path,
                    "configured_exists": path_resolution.configured_exists,
                    "configured_media_count": path_resolution.configured_media_count,
                    "reason": path_resolution.reason,
                },
            )

        if path_resolution.suggested_path is not None:
            log_level = logging.INFO if verbose else logging.DEBUG
            LOGGER.log(
                log_level,
                "auto-discovery suggested onedrive_root",
                extra={
                    "account": account.name,
                    "suggested_path": path_resolution.suggested_path,
                    "media_count": path_resolution.suggested_media_count,
                },
            )

        effective_root = path_resolution.effective_path
        auth_client.persist_onboarding_root(account, effective_root)

        if path_resolution.suggested_path is not None and _confirm_config_writeback(path_resolution.suggested_path):
            if _write_account_onedrive_root(config_path, account.name, path_resolution.suggested_path):
                LOGGER.info(
                    "wrote discovered onedrive_root to config",
                    extra={"account": account.name, "path": path_resolution.suggested_path},
                )
            else:
                LOGGER.warning(
                    "unable to write discovered onedrive_root to config",
                    extra={"account": account.name, "path": path_resolution.suggested_path},
                )
    except GraphError as exc:
        LOGGER.warning(
            "camera-roll auto-discovery failed",
            extra={
                "account": account.name,
                "error_code": exc.code,
            },
        )

    LOGGER.info("discovery completed", extra={"account": account.name})
    return 0


def _cmd_poll(args: argparse.Namespace) -> int:
    """Run OneDrive account polling and staging download for the OneDrive client."""

    try:
        app_config = load_config(args.path)
        results = poll_accounts(app_config, account_name=args.account)
        registry = Registry(app_config.core.registry_path)
        registry.initialize()
        ingest_engine = IngestDecisionEngine(registry)

        ingest_candidate_count = 0
        ingest_outcome_count = 0
        ingest_accepted_count = 0
        ingest_discarded_count = 0

        for result in results:
            handoff_candidates = load_boundary_handoff_candidates(result.payload.handoff_manifest_path)
            ingest_candidates = [
                StagedCandidate(
                    account_name=row.account_name,
                    onedrive_id=row.onedrive_id,
                    original_filename=row.original_filename,
                    relative_path=row.relative_path,
                    modified_time=row.modified_time,
                    size_bytes=row.size_bytes,
                    staging_path=row.staging_path,
                )
                for row in handoff_candidates
            ]
            ingest_candidate_count += len(ingest_candidates)

            ingest_result = ingest_engine.process_batch(
                candidates=ingest_candidates,
                accepted_root=app_config.core.accepted_path,
                storage_template=app_config.core.storage_template,
                staging_on_same_pool=app_config.core.staging_on_same_pool,
            )
            ingest_outcome_count += len(ingest_result.outcomes)
            ingest_accepted_count += ingest_result.accepted_count
            ingest_discarded_count += ingest_result.discarded_count

            LOGGER.info(
                "poll completed",
                extra={
                    "account": result.account_name,
                    "candidates": result.candidate_count,
                    "downloaded": len(result.downloaded_paths),
                    "ingest_candidates": len(ingest_candidates),
                    "ingest_accepted": ingest_result.accepted_count,
                    "ingest_discarded": ingest_result.discarded_count,
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
                "ingest_candidate_count": ingest_candidate_count,
                "ingest_outcome_count": ingest_outcome_count,
                "ingest_accepted_count": ingest_accepted_count,
                "ingest_discarded_count": ingest_discarded_count,
            },
        )
        return 0
    except (GraphError, AuthError, IngestError, RegistryError, ValueError) as exc:
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


def _confirm_config_writeback(suggested_path: str | None = None) -> bool:
    """Ask operator consent before modifying config file."""

    prompt_policy = os.getenv("NIGHTFALL_PROMPT_POLICY", "").strip().lower()

    if prompt_policy == "assume-yes":
        if suggested_path:
            print(f"\nDiscovered OneDrive root: {suggested_path}\n")
        print("Assume-yes: Write discovered onedrive_root back to config file? -> yes")
        return True

    if prompt_policy == "assume-no":
        if suggested_path:
            print(f"\nDiscovered OneDrive root: {suggested_path}\n")
        print("Assume-no: Write discovered onedrive_root back to config file? -> no")
        return False

    if prompt_policy == "assume-default":
        if suggested_path:
            print(f"\nDiscovered OneDrive root: {suggested_path}\n")
        print("Assume-default: Write discovered onedrive_root back to config file? -> no")
        return False

    if not sys.stdin.isatty():
        return False

    if suggested_path:
        print(f"\nDiscovered OneDrive root: {suggested_path}\n")
    
    answer = input("Write discovered onedrive_root back to config file? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _write_account_onedrive_root(config_path: str, account_name: str, discovered_path: str) -> bool:
    """Best-effort update of [account.NAME] onedrive_root in config file."""

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError:
        return False

    section_name = f"account.{account_name}"
    if section_name not in parser:
        return False

    parser[section_name]["onedrive_root"] = discovered_path

    try:
        with open(config_path, "w", encoding="utf-8") as handle:
            parser.write(handle)
    except OSError:
        return False

    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code."""

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    # Determine if verbose mode is requested (for auth-setup command)
    verbose = getattr(args, "verbose", False)

    # Set up file logging for auth-setup operations
    log_file_path = None
    if args.command == "auth-setup":
        log_dir = Path("/var/lib/ingress/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir / f"auth-setup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"

    configure_logging(args.log_mode, verbose=verbose, log_file_path=log_file_path)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return int(handler(args))
