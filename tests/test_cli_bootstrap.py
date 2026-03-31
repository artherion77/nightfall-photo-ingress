"""CLI bootstrap tests for Module 0."""

from __future__ import annotations

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
        "poll",
        "reject",
        "process-trash",
        "sync-import",
        "config-check",
    }


def test_main_help_exit_code_zero() -> None:
    """Calling main with no subcommand should print help and return zero."""

    assert cli.main([]) == 0
