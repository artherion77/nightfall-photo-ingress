"""Logging bootstrap helpers for the CLI.

Module 0 provides only logger setup and output mode selection. Structured context
and domain-specific logging fields are introduced in later modules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

LogMode = Literal["json", "human"]


class JsonFormatter(logging.Formatter):
    """Format log records into compact JSON objects for machine processing."""

    _RESERVED_FIELDS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def _to_json_value(self, value: object) -> object:
        """Convert common runtime values to JSON-safe forms."""

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [self._to_json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._to_json_value(item)
                for key, item in value.items()
            }
        return str(value)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: self._to_json_value(value)
            for key, value in record.__dict__.items()
            if key not in self._RESERVED_FIELDS and not key.startswith("_")
        }
        payload.update(extras)
        return json.dumps(payload, sort_keys=True)


def configure_logging(
    mode: LogMode,
    verbose: bool = False,
    log_file_path: Path | None = None,
) -> None:
    """Configure root logging for CLI execution.

    Args:
        mode: Either "json" for structured logs or "human" for plain output.
        verbose: If True, set console handler to DEBUG level to show all details.
                If False, set to INFO level but suppress specific noisy loggers.
        log_file_path: Optional path to write all log details to a file.
    """

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Console handler: verbose shows all, non-verbose hides noisy Graph/httpx details
    handler = logging.StreamHandler()
    if verbose:
        handler.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        # Suppress verbose debug logging from external libraries in non-verbose mode
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("nightfall_photo_ingress.adapters.onedrive.client").setLevel(logging.WARNING)

    if mode == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)

    # File handler: always logs everything at DEBUG level for troubleshooting
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        if mode == "json":
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        root.addHandler(file_handler)
