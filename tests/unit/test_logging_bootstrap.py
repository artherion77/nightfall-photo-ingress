"""Logging bootstrap tests for Module 0."""

from __future__ import annotations

import io
import logging

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
    assert "poll alice p2 items=50 files=44 del=1 +" in output
    assert output.endswith("INFO test.interactive.trace: discovery completed\n")
