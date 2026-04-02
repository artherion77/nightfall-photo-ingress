"""Logging bootstrap tests for Module 0."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from nightfall_photo_ingress.logging_bootstrap import (
    HumanFormatter,
    JsonFormatter,
    _InteractiveTraceHandler,
    configure_logging,
)


def test_configure_logging_json_mode() -> None:
    """JSON mode should install JsonFormatter on the root handler."""

    configure_logging("json")
    root = logging.getLogger()

    assert root.handlers
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_configure_logging_human_mode() -> None:
    """Human mode should install a plain text formatter."""

    configure_logging("human")
    root = logging.getLogger()

    assert root.handlers
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_human_formatter_renders_trace_summary() -> None:
    """Human formatter should turn trace extras into concise operator text."""

    logger = logging.getLogger("test.human.trace")
    record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "graph_response_summary",
            "account_name": "alice",
            "status_code": 200,
            "value_count": 25,
            "has_next_link": True,
            "has_delta_link": False,
            "url": "https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta",
        },
    )

    rendered = HumanFormatter("%(levelname)s %(name)s: %(message)s").format(record)

    assert rendered.startswith("trace alice: graph 200 items=25")
    assert "next=yes" in rendered
    assert "delta=no" in rendered


def test_interactive_trace_handler_renders_progress_and_flushes_before_normal_log() -> None:
    """Interactive human handler should update one line for progress traces."""

    class _FakeTty(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = _FakeTty()
    handler = _InteractiveTraceHandler(verbose=False, stream=stream)
    handler.setFormatter(HumanFormatter("%(levelname)s %(name)s: %(message)s"))

    trace_logger = logging.getLogger("test.interactive.trace")
    progress_record = trace_logger.makeRecord(
        name=trace_logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "delta_page_progress",
            "account_name": "alice",
            "page_index": 2,
            "items_total": 50,
            "file_items": 44,
            "deleted_items": 1,
            "has_next": True,
        },
    )
    info_record = trace_logger.makeRecord(
        name=trace_logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=2,
        msg="discovery completed",
        args=(),
        exc_info=None,
    )

    handler.emit(progress_record)
    handler.emit(info_record)

    output = stream.getvalue()
    assert "\r" in output
    assert "poll alice p2 items=50 files=44 del=1 next=+" in output
    assert output.endswith("INFO test.interactive.trace: discovery completed\n")


def test_interactive_trace_handler_suppresses_graph_trace_chatter() -> None:
    """Verbose interactive mode should keep graph/chk trace in one compact polling line."""

    class _FakeTty(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = _FakeTty()
    handler = _InteractiveTraceHandler(verbose=True, stream=stream)
    handler.setFormatter(HumanFormatter("%(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("test.interactive.compact")

    graph_record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "graph_response_summary",
            "status_code": 200,
        },
    )
    checkpoint_record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=2,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "delta_cursor_checkpoint_saved",
            "checkpoint_kind": "next_link",
        },
    )
    progress_record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=3,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "delta_page_progress",
            "account_name": "alice",
            "page_index": 7,
            "items_total": 206,
            "file_items": 188,
            "deleted_items": 0,
            "has_next": True,
        },
    )

    handler.emit(graph_record)
    handler.emit(checkpoint_record)
    handler.emit(progress_record)

    output = stream.getvalue()
    assert "graph 200" not in output
    assert "checkpoint page=" not in output
    assert "poll alice p7 items=206 files=188 del=0 next=+ http=200 cp=next_link" in output


def test_interactive_trace_handler_renders_download_progress_bar() -> None:
    """Interactive handler should render byte progress for individual file downloads."""

    class _FakeTty(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = _FakeTty()
    handler = _InteractiveTraceHandler(verbose=False, stream=stream)
    handler.setFormatter(HumanFormatter("%(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("test.interactive.download.progress")

    start_record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "download_attempt_start",
            "account_name": "alice",
            "destination": "/tmp/staging/IMG_0001.HEIC",
            "expected_size": 1048576,
        },
    )
    progress_record = logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=2,
        msg="onedrive_trace",
        args=(),
        exc_info=None,
        extra={
            "event": "download_progress",
            "account_name": "alice",
            "destination": "/tmp/staging/IMG_0001.HEIC",
            "bytes_written": 524288,
            "expected_size": 1048576,
        },
    )

    handler.emit(start_record)
    handler.emit(progress_record)

    output = stream.getvalue()
    assert "poll alice dl IMG_0001.HEIC" in output
    assert "( 50%)" in output


def test_configure_logging_suppresses_httpx_console_propagation_by_default() -> None:
    """External library logs should not propagate to operator-visible handlers by default."""

    configure_logging("human", verbose=True)

    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    urllib3_logger = logging.getLogger("urllib3")
    msal_logger = logging.getLogger("msal")

    assert httpx_logger.propagate is False
    assert httpcore_logger.propagate is False
    assert urllib3_logger.propagate is False
    assert msal_logger.propagate is False


def test_debug_httpx_transport_writes_redacted_log_file(tmp_path: Path) -> None:
    """Opt-in transport diagnostics should go to a redacted file sink only."""

    transport_log = tmp_path / "httpx-transport.log"
    configure_logging(
        "human",
        verbose=True,
        debug_httpx_transport=True,
        httpx_transport_log_path=transport_log,
    )

    logging.getLogger("httpx").info(
        'HTTP Request: GET https://graph.microsoft.com/v1.0/me/drive/root:/Camera%20Roll:/delta?token=super-secret "HTTP/1.1 200 OK"'
    )

    rendered = transport_log.read_text(encoding="utf-8")
    assert "super-secret" not in rendered
    assert "token=" not in rendered
    assert "[query redacted]" in rendered
