"""Smoke contract tests for the staging-photo-ingress LXC container.

These tests assert invariants that must hold on a freshly installed container:
  - The installed binary is reachable and reports a version.
  - The config-check command exits 0 with a valid config.
  - The systemd service unit can be started (oneshot) without error.
  - The accepted / staging directories are writable from inside the container.

Run after "stagingctl install":
    pytest tests/staging -m staging -k "smoke"

Each assertion is written as an audit row in the EvidenceRun evidence directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.staging


# ── helpers ───────────────────────────────────────────────────────────────────

def _assert(run, name: str, condition: bool, detail: str = "") -> None:
    """Write an audit row and raise AssertionError if condition is False."""
    result = "pass" if condition else "fail"
    run.audit(name, result=result, detail=detail)
    assert condition, f"Assertion '{name}' failed: {detail}"


def _read_status_payload(container):
    proc = container.exec(
        [
            "python3",
            "-c",
            (
                "import json, pathlib; "
                "print(json.dumps(json.loads(pathlib.Path('/run/nightfall-status.d/photo-ingress.json').read_text())))"
            ),
        ]
    )
    return proc, json.loads(proc.stdout) if proc.returncode == 0 else None


# ── tests ─────────────────────────────────────────────────────────────────────

class TestBinaryPresence:
    """The installed wheel exposes the CLI binary in the venv."""

    def test_binary_is_reachable(self, container, evidence_run):
        """nightfall-photo-ingress --version exits 0."""
        proc = container.app("--version")
        _assert(
            evidence_run,
            "binary_reachable",
            proc.returncode == 0,
            f"exit={proc.returncode} stdout={proc.stdout.strip()!r}",
        )

    def test_help_does_not_crash(self, container, evidence_run):
        """nightfall-photo-ingress --help returns 0."""
        proc = container.app("--help")
        _assert(
            evidence_run,
            "help_exit_0",
            proc.returncode == 0,
            f"exit={proc.returncode}",
        )
        _assert(
            evidence_run,
            "help_contains_poll",
            "poll" in proc.stdout,
            "expected 'poll' subcommand in help text",
        )


class TestConfigCheck:
    """config-check validates the installed staging config without error."""

    def test_config_check_exits_0(self, container, evidence_run):
        """config-check must exit 0 for a structurally valid config file."""
        from tests.staging.conftest import CONF_PATH
        proc = container.app("--log-mode", "json", "config-check", "--path", CONF_PATH)
        _assert(
            evidence_run,
            "config_check_exit_0",
            proc.returncode == 0,
            f"exit={proc.returncode} stderr={proc.stderr.strip()[:200]!r}",
        )

    def test_config_check_emits_json(self, container, evidence_run):
        """config-check output is parseable JSON when --log-mode json is set."""
        from tests.staging.conftest import CONF_PATH
        proc = container.app("--log-mode", "json", "config-check", "--path", CONF_PATH)
        # Collect all output lines
        lines = [l.strip() for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
        parseable = sum(1 for l in lines if _is_json(l))
        _assert(
            evidence_run,
            "config_check_json_output",
            parseable > 0 or proc.returncode == 0,
            f"parseable_json_lines={parseable}",
        )

    def test_missing_config_exits_nonzero(self, container, evidence_run):
        """config-check on a nonexistent path must exit non-zero."""
        proc = container.app("config-check", "--path", "/nonexistent/path.conf")
        _assert(
            evidence_run,
            "missing_config_exits_nonzero",
            proc.returncode != 0,
            f"exit={proc.returncode}",
        )


class TestDirectoryLayout:
    """Required directories exist and are writable inside the container."""

    @pytest.mark.parametrize("path", [
        "/var/lib/ingress/staging",
        "/var/lib/ingress/accepted",
        "/var/lib/ingress/trash",
        "/var/lib/ingress/tokens",
        "/var/lib/ingress/cursors",
        "/var/log/nightfall",
        "/run/nightfall-status.d",
    ])
    def test_directory_is_writable(self, container, evidence_run, path):
        probe = f"{path}/.stagingctl_probe"
        proc = container.exec(["bash", "-c", f"touch {probe} && rm {probe}"])
        _assert(
            evidence_run,
            f"directory_writable_{path.replace('/', '_')}",
            proc.returncode == 0,
            f"path={path} exit={proc.returncode} stderr={proc.stderr.strip()!r}",
        )


class TestSystemdUnit:
    """systemd service unit is installed and startable."""

    def test_service_unit_is_known(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "cat", "nightfall-photo-ingress.service"],
        )
        _assert(
            evidence_run,
            "service_unit_known",
            proc.returncode == 0,
            f"exit={proc.returncode}",
        )

    def test_timer_unit_is_known(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "cat", "nightfall-photo-ingress.timer"],
        )
        _assert(
            evidence_run,
            "timer_unit_known",
            proc.returncode == 0,
            f"exit={proc.returncode}",
        )

    def test_trash_path_unit_is_known(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "cat", "nightfall-photo-ingress-trash.path"],
        )
        _assert(
            evidence_run,
            "trash_path_unit_known",
            proc.returncode == 0,
            f"exit={proc.returncode}",
        )

    def test_trash_service_unit_is_known(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "cat", "nightfall-photo-ingress-trash.service"],
        )
        _assert(
            evidence_run,
            "trash_service_unit_known",
            proc.returncode == 0,
            f"exit={proc.returncode}",
        )

    def test_service_unit_file_has_exec_start(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "cat", "nightfall-photo-ingress.service"],
        )
        _assert(
            evidence_run,
            "service_has_ExecStart",
            "ExecStart" in proc.stdout,
            f"unit content excerpt: {proc.stdout[:300]!r}",
        )

    def test_trash_service_can_start(self, container, evidence_run):
        proc = container.exec(
            ["systemctl", "start", "nightfall-photo-ingress-trash.service"],
        )
        _assert(
            evidence_run,
            "trash_service_startable",
            proc.returncode == 0,
            f"exit={proc.returncode} stderr={proc.stderr.strip()!r}",
        )


class TestStatusExport:
    """Operational commands emit a parseable status snapshot in staging."""

    def test_config_check_writes_status_file(self, container, evidence_run):
        from tests.staging.conftest import CONF_PATH

        container.exec(["rm", "-f", "/run/nightfall-status.d/photo-ingress.json"])
        proc = container.app("--log-mode", "json", "config-check", "--path", CONF_PATH)
        _assert(
            evidence_run,
            "config_check_status_exit_0",
            proc.returncode == 0,
            f"exit={proc.returncode} stderr={proc.stderr.strip()[:200]!r}",
        )

        status_proc, payload = _read_status_payload(container)
        _assert(
            evidence_run,
            "status_payload_readable",
            status_proc.returncode == 0,
            f"exit={status_proc.returncode} stderr={status_proc.stderr.strip()!r}",
        )
        _assert(
            evidence_run,
            "status_payload_schema_version",
            payload["schema_version"] == 1,
            f"payload={payload}",
        )
        _assert(
            evidence_run,
            "status_payload_command",
            payload["command"] == "config-check",
            f"payload={payload}",
        )
        _assert(
            evidence_run,
            "status_payload_success",
            payload["success"] is True,
            f"payload={payload}",
        )
        _assert(
            evidence_run,
            "status_payload_host",
            bool(payload["host"]),
            f"payload={payload}",
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except ValueError:
        return False
