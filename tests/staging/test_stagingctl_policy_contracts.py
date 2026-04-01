"""Policy contract tests for stagingctl and setup scripts.

These tests are static contract checks: they only read workspace files and never
invoke LXC or modify host/container state.
"""

from __future__ import annotations

from pathlib import Path

import pytest


STAGINGCTL_PATH = Path(__file__).resolve().parents[2] / "staging" / "stagingctl"
SETUP_PATH = Path(__file__).resolve().parents[2] / "staging" / "container" / "setup.sh"
README_PATH = Path(__file__).resolve().parents[2] / "staging" / "README.md"


@pytest.fixture(scope="module")
def stagingctl_text() -> str:
    return STAGINGCTL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def setup_text() -> str:
    return SETUP_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


class TestLaunchProfiles:
    def test_launch_uses_default_and_staging_profiles(self, stagingctl_text: str) -> None:
        assert "lxc launch ubuntu:24.04 \"$CONTAINER\" -p \"$PROFILE_DEFAULT\" -p \"$PROFILE_STAGING\"" in stagingctl_text

    def test_profile_constants_are_defined(self, stagingctl_text: str) -> None:
        assert 'PROFILE_DEFAULT="default"' in stagingctl_text
        assert 'PROFILE_STAGING="staging"' in stagingctl_text


class TestBridgePolicy:
    def test_network_policy_check_includes_type_nic(self, stagingctl_text: str) -> None:
        assert 'type: nic' in stagingctl_text

    def test_network_policy_check_includes_br_staging_parent(self, stagingctl_text: str) -> None:
        assert 'parent: br-staging' in stagingctl_text

    def test_network_policy_check_includes_bridged_nictype(self, stagingctl_text: str) -> None:
        assert 'nictype: bridged' in stagingctl_text

    def test_script_does_not_create_host_networks(self, stagingctl_text: str) -> None:
        forbidden = [
            "lxc network create",
            "ip link add",
            "brctl addbr",
            "netplan apply",
        ]
        for token in forbidden:
            assert token not in stagingctl_text


class TestStorageModes:
    def test_persistent_defaults_match_policy(self, stagingctl_text: str) -> None:
        assert "/mnt/ssd/staging/photo-ingress/evidence" in stagingctl_text
        assert "/mnt/ssd/staging/photo-ingress/logs" in stagingctl_text

    def test_volatile_defaults_match_policy(self, stagingctl_text: str) -> None:
        assert "/run/staging-photo-ingress/evidence" in stagingctl_text
        assert "/run/staging-photo-ingress/logs" in stagingctl_text

    def test_staging_volatile_flag_is_supported(self, stagingctl_text: str) -> None:
        assert 'STAGING_VOLATILE="${STAGING_VOLATILE:-0}"' in stagingctl_text


class TestUninstallPurge:
    def test_uninstall_accepts_purge_flag(self, stagingctl_text: str) -> None:
        assert 'if [[ "${1:-}" == "--purge" ]]; then' in stagingctl_text

    def test_uninstall_purge_removes_evidence_and_logs(self, stagingctl_text: str) -> None:
        assert 'rm -rf "$HOST_EVIDENCE_BASE" "$HOST_LOG_BASE"' in stagingctl_text


class TestTmpfsBoundaries:
    def test_tmpfs_devices_added_in_create(self, stagingctl_text: str) -> None:
           assert 'source=none path=/tmp' in stagingctl_text
           assert 'source=none path=/var/tmp' in stagingctl_text
           assert 'source=none path=/var/cache/nightfall-photo-ingress' in stagingctl_text

    def test_setup_prepares_cache_directory(self, setup_text: str) -> None:
        assert 'mkdir -p /var/cache/nightfall-photo-ingress' in setup_text

    def test_setup_prepares_volatile_run_paths(self, setup_text: str) -> None:
        assert 'mkdir -p /run/staging-photo-ingress/{evidence,logs}' in setup_text


class TestDocumentationCoverage:
    def test_readme_mentions_br_staging(self, readme_text: str) -> None:
        assert 'br-staging' in readme_text

    def test_readme_mentions_vlan1_and_no_host_ip(self, readme_text: str) -> None:
        assert 'VLAN1' in readme_text
        assert 'Host IP on bridge: none' in readme_text

    def test_readme_mentions_purge_behavior(self, readme_text: str) -> None:
        assert 'uninstall --purge' in readme_text

    def test_readme_mentions_profiles_and_image(self, readme_text: str) -> None:
        assert 'ubuntu:24.04' in readme_text
        assert '-p default -p staging' in readme_text
