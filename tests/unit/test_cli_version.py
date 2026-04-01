"""CLI version behavior tests for packaging/smoke compatibility."""

from __future__ import annotations

from nightfall_photo_ingress import __version__, cli


def test_main_version_exit_code_zero(capsys) -> None:
    exit_code = cli.main(["--version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert __version__ in captured.out
