"""Packaging artifact presence tests for the operations surface."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_systemd_units_exist() -> None:
    systemd_dir = PROJECT_ROOT / "systemd"
    assert (systemd_dir / "nightfall-photo-ingress.service").exists()
    assert (systemd_dir / "nightfall-photo-ingress.timer").exists()
    assert (systemd_dir / "nightfall-photo-ingress-trash.path").exists()
    assert (systemd_dir / "nightfall-photo-ingress-trash.service").exists()


def test_install_scripts_exist() -> None:
    install_dir = PROJECT_ROOT / "install"
    assert (install_dir / "install.sh").exists()
    assert (install_dir / "uninstall.sh").exists()
    assert (install_dir / "container" / "setup.sh").exists()


def test_operator_runbook_exists() -> None:
    docs_dir = PROJECT_ROOT / "docs"
    assert (docs_dir / "operations-runbook.md").exists()
