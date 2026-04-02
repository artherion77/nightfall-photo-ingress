"""Logging bootstrap helpers for the CLI.

Module 0 provides only logger setup and output mode selection. Structured context
and domain-specific logging fields are introduced in later modules.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .adapters.onedrive.errors import redact_url

LogMode = Literal["json", "human"]


_SPINNER_FRAMES = ("|", "/", "-", "\\")
_HTTP_TRANSPORT_LOGGERS = ("httpx", "httpcore")
_QUIET_LIBRARY_LOGGERS = ("urllib3", "msal")
_URL_RE = re.compile(r"https?://[^\s\"')]+", re.IGNORECASE)


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


class HumanFormatter(logging.Formatter):
    """Format human-mode logs, including concise OneDrive trace summaries."""

    def format(self, record: logging.LogRecord) -> str:
        if record.msg == "onedrive_trace":
            return self._format_trace(record)
        return super().format(record)

    def _format_trace(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", "trace")
        account = getattr(record, "account_name", None)
        prefix = f"trace {account}: " if account else "trace: "

        if event == "graph_response_summary":
            return (
                f"{prefix}graph {getattr(record, 'status_code', '?')} "
                f"items={getattr(record, 'value_count', 0)} "
                f"next={'yes' if getattr(record, 'has_next_link', False) else 'no'} "
                f"delta={'yes' if getattr(record, 'has_delta_link', False) else 'no'} "
                f"url={getattr(record, 'url', '?')}"
            )

        if event == "graph_retry_scheduled":
            return (
                f"{prefix}graph retry status={getattr(record, 'status_code', '?')} "
                f"reason={getattr(record, 'reason', '?')} "
                f"delay={getattr(record, 'delay_seconds', '?')}s "
                f"url={getattr(record, 'url', '?')}"
            )

        if event == "download_content_summary":
            return (
                f"{prefix}download {getattr(record, 'bytes_written', 0)}B"
                f"/{getattr(record, 'expected_size', '?')}B "
                f"url={getattr(record, 'url', '?')}"
            )

        if event == "delta_cursor_checkpoint_saved":
            return (
                f"{prefix}checkpoint page={getattr(record, 'page_index', '?')} "
                f"kind={getattr(record, 'checkpoint_kind', '?')}"
            )

        if event == "delta_cursor_start":
            token_state = "yes" if getattr(record, "cursor_has_token", False) else "no"
            return (
                f"{prefix}cursor start source={getattr(record, 'cursor_source', '?')} "
                f"has_token={token_state}"
            )

        if event == "delta_page_progress":
            return (
                f"{prefix}page={getattr(record, 'page_index', '?')} "
                f"items={getattr(record, 'items_total', 0)} "
                f"files={getattr(record, 'file_items', 0)} "
                f"deleted={getattr(record, 'deleted_items', 0)} "
                f"next={'yes' if getattr(record, 'has_next', False) else 'no'}"
            )

        if event == "delta_traversal_summary":
            return (
                f"{prefix}traversal pages={getattr(record, 'pages_walked', 0)} "
                f"elapsed={getattr(record, 'traversal_seconds', 0)}s "
                f"page_eval={getattr(record, 'page_eval_seconds', 0)}s "
                f"avg_files_per_page={getattr(record, 'avg_files_per_page', 0)} "
                f"avg_items_per_page={getattr(record, 'avg_items_per_page', 0)}"
            )

        if event == "delta_chain_completed_cursor_reset":
            return (
                f"{prefix}chain complete, cursor reset to initial "
                f"pages={getattr(record, 'pages_walked', 0)}"
            )

        if event == "account_poll_start":
            return f"{prefix}poll start"

        if event == "account_poll_end":
            return (
                f"{prefix}poll done candidates={getattr(record, 'candidate_count', 0)} "
                f"downloaded={getattr(record, 'downloaded_count', 0)}"
            )

        return f"{prefix}{event}"


class _RedactingFormatter(logging.Formatter):
    """Formatter that redacts raw URLs from transport-library log lines."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return _URL_RE.sub(lambda match: redact_url(match.group(0)), rendered)


class _InteractiveTraceHandler(logging.StreamHandler):
    """Render compact progress updates for trace events in interactive terminals."""

    def __init__(self, *, verbose: bool, stream=None) -> None:
        super().__init__(stream)
        self._verbose = verbose
        self._spinner_index = 0
        self._progress_active = False
        self._last_progress_width = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.msg == "onedrive_trace":
                if self._emit_trace(record):
                    return
            self._flush_progress_line()
            super().emit(record)
        except Exception:
            self.handleError(record)

    def _emit_trace(self, record: logging.LogRecord) -> bool:
        event = getattr(record, "event", "")
        if event == "delta_page_progress":
            self._render_progress(record)
            return True

        if self._verbose:
            self._flush_progress_line()
            super().emit(record)
        return True

    def _render_progress(self, record: logging.LogRecord) -> None:
        frame = _SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)]
        self._spinner_index += 1
        account = getattr(record, "account_name", "?")
        page = getattr(record, "page_index", "?")
        items = getattr(record, "items_total", 0)
        files = getattr(record, "file_items", 0)
        deleted = getattr(record, "deleted_items", 0)
        suffix = "+" if getattr(record, "has_next", False) else "done"
        text = f"{frame} poll {account} p{page} items={items} files={files} del={deleted} {suffix}"
        padded = text.ljust(self._last_progress_width)
        self.stream.write("\r" + padded)
        self.flush()
        self._progress_active = True
        self._last_progress_width = max(self._last_progress_width, len(text))

    def _flush_progress_line(self) -> None:
        if not self._progress_active:
            return
        self.stream.write("\n")
        self.flush()
        self._progress_active = False
        self._last_progress_width = 0


def _reset_transport_loggers() -> None:
    """Remove previously installed Nightfall transport handlers."""

    for logger_name in _HTTP_TRANSPORT_LOGGERS:
        logger = logging.getLogger(logger_name)
        for handler in list(logger.handlers):
            if getattr(handler, "_nightfall_transport_handler", False):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except OSError:
                    pass


def _configure_transport_loggers(
    *,
    debug_httpx_transport: bool,
    httpx_transport_log_path: Path | None,
) -> None:
    """Keep transport-library logs off the console unless explicitly requested."""

    _reset_transport_loggers()

    for logger_name in _HTTP_TRANSPORT_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.propagate = False

        if debug_httpx_transport and httpx_transport_log_path is not None:
            handler = logging.FileHandler(httpx_transport_log_path, mode="a", encoding="utf-8")
            handler._nightfall_transport_handler = True  # type: ignore[attr-defined]
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(
                _RedactingFormatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
            logger.handlers.clear()
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            continue

        logger.handlers.clear()
        null_handler = logging.NullHandler()
        null_handler._nightfall_transport_handler = True  # type: ignore[attr-defined]
        logger.addHandler(null_handler)
        logger.setLevel(logging.WARNING)

    for logger_name in _QUIET_LIBRARY_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.propagate = False
        logger.handlers.clear()
        null_handler = logging.NullHandler()
        null_handler._nightfall_transport_handler = True  # type: ignore[attr-defined]
        logger.addHandler(null_handler)
        logger.setLevel(logging.WARNING)


def configure_logging(
    mode: LogMode,
    verbose: bool = False,
    log_file_path: Path | None = None,
    debug_httpx_transport: bool = False,
    httpx_transport_log_path: Path | None = None,
) -> None:
    """Configure root logging for CLI execution.

    Args:
        mode: Either "json" for structured logs or "human" for plain output.
        verbose: If True, set console handler to DEBUG level to show all details.
                If False, set to INFO level but suppress specific noisy loggers.
        log_file_path: Optional path to write all log details to a file.
        debug_httpx_transport: If True, enable dedicated redacted httpx/httpcore transport logs.
        httpx_transport_log_path: Optional file sink for redacted transport diagnostics.
    """

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    _configure_transport_loggers(
        debug_httpx_transport=debug_httpx_transport,
        httpx_transport_log_path=httpx_transport_log_path,
    )

    # Console handler: verbose shows all, non-verbose hides noisy Graph/httpx details
    interactive_human = mode == "human" and hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    if interactive_human:
        handler = _InteractiveTraceHandler(verbose=verbose)
    else:
        handler = logging.StreamHandler()
    if verbose:
        handler.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)

    if mode == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(HumanFormatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)

    # File handler: always logs everything at DEBUG level for troubleshooting
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        if mode == "json":
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                HumanFormatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        root.addHandler(file_handler)
