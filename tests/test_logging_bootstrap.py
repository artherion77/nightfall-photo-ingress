"""Logging bootstrap tests for Module 0."""

from __future__ import annotations

import logging

from nightfall_photo_ingress.logging_bootstrap import JsonFormatter, configure_logging


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
