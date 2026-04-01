"""Shared fixtures for the staging test suite.

These tests require a live "staging-photo-ingress" LXC container.
They are intentionally excluded from the default pytest testpaths
(tests/unit, tests/integration) and must be run explicitly:

    pytest tests/staging -m staging

Each test that performs an assertion writes a row to the EvidenceRun audit log
so every assertion is traceable to a run-id and timestamp.

Environment variables consumed by fixtures:
  STAGING_CONTAINER     LXC container name (default: staging-photo-ingress)
  STAGING_VENV          venv root inside container (default: /opt/ingress)
  STAGING_CONF          config path inside container (default: /etc/nightfall/photo-ingress.conf)
  STAGING_ACCOUNT       account name for live poll tests (default: staging)
  STAGING_EVIDENCE_BASE host-side evidence directory
                        (default: /var/lib/staging-photo-ingress/evidence)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Generator

import pytest

# Add staging/ to path so we can import evidence helpers without installing them
_STAGING_DIR = Path(__file__).parent.parent.parent / "staging"
if str(_STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_STAGING_DIR))

from evidence.capture import EvidenceRun  # noqa: E402


# ── configuration ─────────────────────────────────────────────────────────────

CONTAINER     = os.environ.get("STAGING_CONTAINER",     "staging-photo-ingress")
VENV_ROOT     = os.environ.get("STAGING_VENV",          "/opt/ingress")
CONF_PATH     = os.environ.get("STAGING_CONF",          "/etc/nightfall/photo-ingress.conf")
ACCOUNT       = os.environ.get("STAGING_ACCOUNT",       "staging")
EVIDENCE_BASE = os.environ.get("STAGING_EVIDENCE_BASE", "/mnt/ssd/staging/photo-ingress/evidence")


# ── container helper ──────────────────────────────────────────────────────────

class ContainerHandle:
    """Thin wrapper around `lxc exec` for running commands in the staging container."""

    def __init__(self, name: str, venv: str) -> None:
        self.name = name
        self.venv = venv

    def exec(
        self,
        cmd: list[str],
        *,
        check: bool = False,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        full = ["lxc", "exec", self.name, "--"] + cmd
        return subprocess.run(
            full,
            capture_output=capture,
            text=True,
            check=check,
        )

    def app(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the installed app binary with the given arguments."""
        return self.exec(
            [f"{self.venv}/bin/nightfall-photo-ingress"] + list(args),
            capture=True,
        )

    def is_running(self) -> bool:
        result = subprocess.run(
            ["lxc", "info", self.name],
            capture_output=True,
            text=True,
        )
        return "Status: Running" in result.stdout


def _require_container(container_name: str) -> None:
    result = subprocess.run(
        ["lxc", "info", container_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(
            f"Staging container '{container_name}' not available. "
            "Run: stagingctl create && stagingctl install"
        )
    if "Status: Running" not in result.stdout:
        pytest.skip(
            f"Staging container '{container_name}' exists but is not running."
        )


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def container() -> ContainerHandle:
    """Session-scoped handle to the staging LXC container."""
    _require_container(CONTAINER)
    return ContainerHandle(name=CONTAINER, venv=VENV_ROOT)


@pytest.fixture
def evidence_run(tmp_path: Path) -> Generator[EvidenceRun, None, None]:
    """Per-test EvidenceRun written to the configured evidence base directory.

    Falls back to tmp_path if the host evidence directory is not writable.
    """
    base = Path(EVIDENCE_BASE)
    if not base.exists():
        try:
            base.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            base = tmp_path / "evidence"
            base.mkdir(parents=True, exist_ok=True)

    with EvidenceRun(base_dir=base) as run:
        yield run
