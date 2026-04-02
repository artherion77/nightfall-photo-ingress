"""CLI bootstrap tests for Module 0."""

from __future__ import annotations

import io

from nightfall_photo_ingress import cli


def test_cli_commands_are_registered() -> None:
    """Verify the expected Module 0 stub commands exist."""

    parser = cli._build_parser()
    subparsers_action = next(
        action
        for action in parser._actions
        if action.__class__.__name__ == "_SubParsersAction"
    )
    commands = set(subparsers_action.choices.keys())

    assert commands == {
        "auth-setup",
        "discover-paths",
        "poll",
        "reject",
        "process-trash",
        "sync-import",
        "config-check",
    }


def test_main_help_exit_code_zero() -> None:
    """Calling main with no subcommand should print help and return zero."""

    assert cli.main([]) == 0


def test_global_debug_httpx_transport_flag_is_parsed() -> None:
    """Top-level debug transport flag should parse before subcommands."""

    parser = cli._build_parser()
    args = parser.parse_args(["--debug-httpx-transport", "poll"])

    assert args.debug_httpx_transport is True
    assert args.command == "poll"


def test_confirm_config_writeback_respects_assume_yes(monkeypatch, capsys) -> None:
    monkeypatch.setenv("NIGHTFALL_PROMPT_POLICY", "assume-yes")

    assert cli._confirm_config_writeback("/Bilder/Eigene Aufnahmen") is True

    out = capsys.readouterr().out
    assert "Discovered OneDrive root: /Bilder/Eigene Aufnahmen" in out
    assert "Assume-yes: Write discovered onedrive_root back to config file? -> yes" in out


def test_confirm_config_writeback_respects_assume_default(monkeypatch, capsys) -> None:
    monkeypatch.setenv("NIGHTFALL_PROMPT_POLICY", "assume-default")

    assert cli._confirm_config_writeback("/Bilder") is False

    out = capsys.readouterr().out
    assert "Assume-default: Write discovered onedrive_root back to config file? -> no" in out


def test_confirm_config_writeback_non_tty_defaults_to_no(monkeypatch) -> None:
    monkeypatch.delenv("NIGHTFALL_PROMPT_POLICY", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(""))

    assert cli._confirm_config_writeback("/Bilder") is False
