"""CLI glue for the hash-import command."""

from __future__ import annotations

import argparse
import configparser
import logging
from pathlib import Path
from typing import Callable

from .config import ConfigError
from .domain.registry import Registry, RegistryError
from .hash_import import HashImportError, run_hash_import_command

StatusEmitter = Callable[..., None]


def cmd_hash_import(
    args: argparse.Namespace,
    *,
    logger: logging.Logger,
    emit_status_snapshot: StatusEmitter,
) -> int:
    """Import authoritative permanent-library hashes into the registry cache."""

    try:
        registry_path = resolve_hash_import_registry_path(args.path)
        registry = Registry(registry_path)
        registry.initialize()
        chunk_size = resolve_hash_import_chunk_size(config_path=args.path, cli_chunk_size=args.chunk_size)
        summary = run_hash_import_command(
            root_path=Path(args.root_path),
            registry=registry,
            chunk_size=chunk_size,
            dry_run=args.dry_run,
            quiet=args.quiet,
            stats=args.stats,
        )
        emit_status_snapshot(
            state="healthy",
            command="hash-import",
            success=True,
            details={
                "dry_run": args.dry_run,
                "chunk_size": chunk_size,
                "directories_processed": summary.directories_processed,
                "recomputes_performed": summary.recomputes_performed,
                "valid_caches_consumed": summary.valid_caches_consumed,
                "stale_invalid_caches_replaced": summary.stale_invalid_caches_replaced,
                "total_imported": summary.total_imported,
                "total_skipped": summary.total_skipped,
                "root_path": str(args.root_path),
                "stop_on_error": bool(args.stop_on_error),
            },
        )
        return 0
    except (ConfigError, HashImportError, RegistryError, ValueError) as exc:
        logger.error(str(exc))
        emit_status_snapshot(
            state="ingest_error",
            command="hash-import",
            success=False,
            details={"error": str(exc), "root_path": str(args.root_path)},
        )
        return 2


def resolve_hash_import_registry_path(config_path: str | Path) -> Path:
    """Resolve the registry path from raw config without requiring H7 config model changes."""

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with open(config_path, "r", encoding="utf-8") as handle:
        parser.read_file(handle)

    if not parser.has_section("core") or not parser.has_option("core", "registry_path"):
        raise ConfigError("hash-import requires [core] registry_path")
    return Path(parser.get("core", "registry_path"))


def resolve_hash_import_chunk_size(*, config_path: str | Path, cli_chunk_size: int | None) -> int:
    """Resolve hash-import chunk size using CLI, optional raw config, then default."""

    if cli_chunk_size is not None:
        if cli_chunk_size <= 0:
            raise ValueError("hash-import chunk size must be > 0")
        return cli_chunk_size

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with open(config_path, "r", encoding="utf-8") as handle:
        parser.read_file(handle)

    if parser.has_section("import") and parser.has_option("import", "chunk_size"):
        raw_value = parser.get("import", "chunk_size")
        try:
            chunk_size = int(raw_value)
        except ValueError as exc:
            raise ValueError("hash-import chunk size must be an integer") from exc
        if chunk_size <= 0:
            raise ValueError("hash-import chunk size must be > 0")
        return chunk_size

    return 1000
