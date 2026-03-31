"""Logging bootstrap helpers for the CLI.

Module 0 provides only logger setup and output mode selection. Structured context
and domain-specific logging fields are introduced in later modules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

LogMode = Literal["json", "human"]


class JsonFormatter(logging.Formatter):
    """Format log records into compact JSON objects for machine processing."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, sort_keys=True)


def configure_logging(mode: LogMode) -> None:
    """Configure root logging for CLI execution.

    Args:
        mode: Either "json" for structured logs or "human" for plain output.
    """

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    if mode == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
