"""Import smoke tests for Module 0."""

from __future__ import annotations


def test_import_package() -> None:
    """Package should import without side effects."""

    import nightfall_photo_ingress  # noqa: F401


def test_import_config_module() -> None:
    """Config module should expose the parser entrypoint."""

    from nightfall_photo_ingress.config import load_config

    assert callable(load_config)
