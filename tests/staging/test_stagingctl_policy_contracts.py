"""Policy contract tests for stagingctl and setup scripts.

These tests are static contract checks: they only read workspace files and never
invoke LXC or modify host/container state.
"""

from __future__ import annotations

from pathlib import Path

import pytest


STAGINGCTL_PATH = Path(__file__).resolve().parents[2] / "dev" / "bin" / "stagingctl"
SETUP_PATH = Path(__file__).resolve().parents[2] / "staging" / "container" / "setup.sh"
README_PATH = Path(__file__).resolve().parents[2] / "staging" / "README.md"
CADDYFILE_PATH = Path(__file__).resolve().parents[2] / "staging" / "container" / "Caddyfile"


@pytest.fixture(scope="module")
def stagingctl_text() -> str:
    return STAGINGCTL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def setup_text() -> str:
    return SETUP_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def caddyfile_text() -> str:
    return CADDYFILE_PATH.read_text(encoding="utf-8")


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

    def test_volatile_host_tmpfs_mode_removed(self, stagingctl_text: str) -> None:
        assert "STAGING_VOLATILE" not in stagingctl_text
        assert "/run/staging-photo-ingress/evidence" not in stagingctl_text
        assert "/run/staging-photo-ingress/logs" not in stagingctl_text


class TestUninstallPurge:
    def test_uninstall_accepts_purge_flag(self, stagingctl_text: str) -> None:
        assert 'if [[ "${1:-}" == "--purge" ]]; then' in stagingctl_text

    def test_uninstall_purge_preserves_evidence_and_logs(self, stagingctl_text: str) -> None:
        assert "preserves host-persistent evidence/log directories" in stagingctl_text
        assert 'rm -rf "$HOST_EVIDENCE_BASE" "$HOST_LOG_BASE"' not in stagingctl_text


class TestTmpfsBoundaries:
    def test_container_local_tmpfs_helper_configures_fstab(self, stagingctl_text: str) -> None:
        assert "_configure_container_local_tmpfs" in stagingctl_text
        assert "tmpfs /tmp tmpfs" in stagingctl_text
        assert "tmpfs /var/tmp tmpfs" in stagingctl_text
        assert "tmpfs /var/cache/nightfall-photo-ingress tmpfs" in stagingctl_text

    def test_create_does_not_add_host_backed_tmp_devices(self, stagingctl_text: str) -> None:
        assert "lxc config device add \"$CONTAINER\" tmpfs-tmp" not in stagingctl_text
        assert "lxc config device add \"$CONTAINER\" tmpfs-var-tmp" not in stagingctl_text
        assert "lxc config device add \"$CONTAINER\" tmpfs-nightfall-cache" not in stagingctl_text

    def test_host_tmpfs_resolver_removed(self, stagingctl_text: str) -> None:
        assert "_resolve_tmpfs_host_base" not in stagingctl_text

    def test_setup_prepares_cache_directory(self, setup_text: str) -> None:
        assert 'mkdir -p /var/cache/nightfall-photo-ingress' in setup_text

    def test_setup_does_not_prepare_volatile_run_paths(self, setup_text: str) -> None:
        assert '/run/staging-photo-ingress/{evidence,logs}' not in setup_text


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


class TestAuthSetup:
    def test_auth_setup_command_dispatched(self, stagingctl_text: str) -> None:
        assert "auth-setup)" in stagingctl_text
        assert "cmd_auth_setup" in stagingctl_text

    def test_auth_setup_uses_tty_for_lxc_exec(self, stagingctl_text: str) -> None:
        # -t allocates a PTY so the device-code prompt renders in the operator's terminal
        assert "lxc exec -t \"$CONTAINER\" --" in stagingctl_text

    def test_auth_setup_uses_staging_account_variable(self, stagingctl_text: str) -> None:
        assert 'account="${STAGING_ACCOUNT:-staging}"' in stagingctl_text

    def test_auth_setup_calls_auth_setup_subcommand(self, stagingctl_text: str) -> None:
        assert "auth-setup --account" in stagingctl_text
        assert "--path \"$CONF_DEST\"" in stagingctl_text


class TestInstallClientIdPreservation:
    def test_install_reads_existing_client_id_from_container_config(self, stagingctl_text: str) -> None:
        assert "existing_client_id" in stagingctl_text
        assert "client_id" in stagingctl_text
        assert "STAGING_CLIENT_ID_PLACEHOLDER" in stagingctl_text

    def test_install_warns_when_existing_client_id_is_overwritten(self, stagingctl_text: str) -> None:
        assert "Existing STAGING_CLIENT_ID" in stagingctl_text
        assert "overwritten with new ID" in stagingctl_text

    def test_install_preserves_existing_client_id_when_host_env_unset(self, stagingctl_text: str) -> None:
        assert "Preserved the existing STAGING_CLIENT_ID in the container." in stagingctl_text

    def test_install_force_reinstalls_same_version_wheels(self, stagingctl_text: str) -> None:
        assert "install --quiet --upgrade --force-reinstall" in stagingctl_text


class TestSmokeLive:
    def test_smoke_live_command_dispatched(self, stagingctl_text: str) -> None:
        assert "smoke-live)" in stagingctl_text
        assert "cmd_smoke_live" in stagingctl_text

    def test_smoke_live_checks_token_cache_before_poll(self, stagingctl_text: str) -> None:
        # Must gate on token cache presence before attempting live poll
        assert "token_path=" in stagingctl_text
        assert "token_cache_exists" in stagingctl_text

    def test_smoke_live_runs_live_poll(self, stagingctl_text: str) -> None:
        assert "live_poll_exit_0" in stagingctl_text
        assert "live_poll_warning" in stagingctl_text
        assert "poll-live.log" in stagingctl_text

    def test_smoke_live_classifies_runtime_and_drift_as_warnings(self, stagingctl_text: str) -> None:
        assert "polling took longer than configured staging timeout" in stagingctl_text
        assert "schema drift threshold reached" in stagingctl_text
        assert "Live smoke completed with warnings" in stagingctl_text

    def test_smoke_live_records_warning_count_in_manifest(self, stagingctl_text: str) -> None:
        assert "warning_count" in stagingctl_text

    def test_smoke_live_uses_human_mode_when_interactive(self, stagingctl_text: str) -> None:
        assert "Interactive terminal detected; using human-mode poll progress renderer." in stagingctl_text
        assert "script -qefc" in stagingctl_text
        assert "--log-mode human poll --verbose" in stagingctl_text

    def test_smoke_live_emits_traversal_summary_line(self, stagingctl_text: str) -> None:
        assert "Poll traversal summary:" in stagingctl_text
        assert "traversal pages=" in stagingctl_text

    def test_smoke_live_pulls_detailed_poll_log_into_evidence(self, stagingctl_text: str) -> None:
        assert "poll-live-detailed.log" in stagingctl_text
        assert "Detailed poll trace saved" in stagingctl_text

    def test_smoke_live_runs_secret_scan(self, stagingctl_text: str) -> None:
        assert "secret_scan_clean" in stagingctl_text

    def test_smoke_live_collects_evidence(self, stagingctl_text: str) -> None:
        assert "smoke_live_started" in stagingctl_text
        assert "smoke_live_finished" in stagingctl_text


class TestDeprecations:
    def test_staging_token_json_has_deprecation_warning(self, stagingctl_text: str) -> None:
        assert "DEPRECATED" in stagingctl_text
        assert "STAGING_TOKEN_JSON" in stagingctl_text

    def test_deprecation_directs_to_auth_setup(self, stagingctl_text: str) -> None:
        # Warning must point the operator to the correct replacement command
        assert "stagingctl auth-setup" in stagingctl_text


class TestReverseProxyC1:
    def test_setup_installs_caddy_package(self, setup_text: str) -> None:
        assert "caddy" in setup_text

    def test_stagingctl_pushes_caddyfile(self, stagingctl_text: str) -> None:
        assert 'CADDYFILE_SOURCE="$STAGING_ROOT/container/Caddyfile"' in stagingctl_text
        assert 'lxc file push "$CADDYFILE_SOURCE" "$CONTAINER$CADDYFILE_DEST"' in stagingctl_text

    def test_stagingctl_enables_caddy_service(self, stagingctl_text: str) -> None:
        assert 'CADDY_SERVICE_NAME="caddy.service"' in stagingctl_text
        assert 'systemctl enable "$CADDY_SERVICE_NAME"' in stagingctl_text
        assert 'systemctl restart "$CADDY_SERVICE_NAME"' in stagingctl_text


class TestTlsC2:
    def test_setup_installs_openssl_for_certificate_generation(self, setup_text: str) -> None:
        assert "openssl" in setup_text

    def test_stagingctl_defines_container_local_tls_paths(self, stagingctl_text: str) -> None:
        assert 'TLS_DIR="/etc/caddy/tls"' in stagingctl_text
        assert 'TLS_CA_CERT="$TLS_DIR/ca.pem"' in stagingctl_text
        assert 'TLS_SERVER_CERT="$TLS_DIR/staging-photo-ingress.crt"' in stagingctl_text

    def test_stagingctl_exports_ca_to_tests_path(self, stagingctl_text: str) -> None:
        assert 'EXPORTED_CA_PATH="$PROJECT_ROOT/tests/ca/staging-ca.pem"' in stagingctl_text
        assert "cmd_export_ca" in stagingctl_text
        assert "lxc file pull \"$CONTAINER$TLS_CA_CERT\" \"$EXPORTED_CA_PATH\"" in stagingctl_text

    def test_stagingctl_provisions_internal_ca_and_server_cert(self, stagingctl_text: str) -> None:
        assert "_provision_container_tls_material" in stagingctl_text
        assert "Nightfall Staging Internal CA" in stagingctl_text
        assert "subjectAltName" in stagingctl_text

    def test_stagingctl_validates_caddy_config_before_restart(self, stagingctl_text: str) -> None:
        assert 'caddy validate --config "$CADDYFILE_DEST"' in stagingctl_text

    def test_stagingctl_smoke_asserts_https_only_ingress(self, stagingctl_text: str) -> None:
        assert "tls_https_only" in stagingctl_text
        assert "curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://127.0.0.1/" in stagingctl_text
        assert "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1/" in stagingctl_text

    def test_caddyfile_is_https_only(self, caddyfile_text: str) -> None:
        assert "auto_https disable_redirects" in caddyfile_text
        assert ":443" in caddyfile_text
        assert "\n:80" not in caddyfile_text


class TestCloudflareTunnel:
    def test_stagingctl_defines_token_mount_paths(self, stagingctl_text: str) -> None:
        assert 'CF_TUNNEL_ORIGINCERT_HOST_PATH="/home/chris/.cloudflare-secrets/npi-staging/origincert.pem"' in stagingctl_text
        assert 'CF_TUNNEL_ORIGINCERT_CT_PATH="/etc/cloudflared/origincert.pem"' in stagingctl_text
        assert 'CF_TUNNEL_CREDENTIALS_HOST_PATH="/home/chris/.cloudflare-secrets/npi-staging/tunnel-credentials.json"' in stagingctl_text
        assert 'CF_TUNNEL_CREDENTIALS_CT_PATH="/etc/cloudflared/tunnel-credentials.json"' in stagingctl_text

    def test_stagingctl_adds_read_only_lxd_disk_mount(self, stagingctl_text: str) -> None:
        assert 'lxc config device add "$CONTAINER" "$CF_TUNNEL_ORIGINCERT_DEVICE_NAME" disk' in stagingctl_text
        assert 'lxc config device add "$CONTAINER" "$CF_TUNNEL_CREDENTIALS_DEVICE_NAME" disk' in stagingctl_text
        assert 'readonly=true' in stagingctl_text

    def test_stagingctl_installs_and_manages_cloudflared_service(self, stagingctl_text: str) -> None:
        assert 'apt-get install -y cloudflared' in stagingctl_text
        assert 'CF_TUNNEL_SERVICE_NAME="cloudflared-tunnel.service"' in stagingctl_text
        assert 'cloudflared --config $CF_CLOUDFLARED_CONFIG_PATH tunnel run' in stagingctl_text
        assert '--token' not in stagingctl_text
        assert 'systemctl disable --now "$CF_TUNNEL_SERVICE_NAME"' in stagingctl_text

    def test_stagingctl_enforces_default_off_after_install(self, stagingctl_text: str) -> None:
        assert "Cloudflare tunnel must default to OFF after install" in stagingctl_text
        assert "Cloudflare tunnel unit is provisioned and defaulted to OFF." in stagingctl_text

    def test_cloudflared_status_command_is_dispatched(self, stagingctl_text: str) -> None:
        assert 'cloudflared-status)' in stagingctl_text
        assert 'cmd_cloudflared_status' in stagingctl_text

    def test_cloudflared_start_stop_commands_are_dispatched(self, stagingctl_text: str) -> None:
        assert 'cloudflared.start)' in stagingctl_text
        assert 'cloudflared.stop)' in stagingctl_text
        assert 'cmd_cloudflared_start' in stagingctl_text
        assert 'cmd_cloudflared_stop' in stagingctl_text

    def test_caddyfile_uses_explicit_tls_material_paths(self, caddyfile_text: str) -> None:
        assert "tls /etc/caddy/tls/staging-photo-ingress.crt /etc/caddy/tls/staging-photo-ingress.key" in caddyfile_text


class TestReleaseVersioningC4:
    def test_stagingctl_defines_release_directory_structure(self, stagingctl_text: str) -> None:
        assert 'RELEASES_ROOT="$PROJECT_ROOT/artifacts/releases"' in stagingctl_text
        assert 'RELEASES_DIR="$RELEASES_ROOT/versions"' in stagingctl_text
        assert 'RELEASE_ACTIVE_LINK="$RELEASES_ROOT/active"' in stagingctl_text
        assert 'RELEASE_AUDIT_LOG="$RELEASES_ROOT/release-events.jsonl"' in stagingctl_text

    def test_install_materializes_versioned_release(self, stagingctl_text: str) -> None:
        assert "_release_materialize" in stagingctl_text
        assert "manifest.json" in stagingctl_text
        assert "release_created" in stagingctl_text

    def test_install_deploys_from_release_directory(self, stagingctl_text: str) -> None:
        assert "_deploy_release_to_container" in stagingctl_text
        assert 'release_dir="$RELEASES_DIR/$release_id"' in stagingctl_text
        assert 'lxc file push "$release_wheel"' in stagingctl_text
        assert 'lxc file push --recursive "$release_dir/webui/build"' in stagingctl_text

    def test_release_mapping_has_active_symlink(self, stagingctl_text: str) -> None:
        assert "_release_set_active" in stagingctl_text
        assert 'ln -sfn "versions/$release_id" "$RELEASE_ACTIVE_LINK"' in stagingctl_text
        assert "active_release_switched" in stagingctl_text

    def test_rollback_path_switches_release_and_validates(self, stagingctl_text: str) -> None:
        assert "cmd_rollback" in stagingctl_text
        assert 'Usage: stagingctl rollback <release-id>' in stagingctl_text
        assert "rollback_started" in stagingctl_text
        assert "rollback_validated" in stagingctl_text
        assert "systemctl is-active --quiet" in stagingctl_text

    def test_usage_exposes_release_and_rollback_commands(self, stagingctl_text: str) -> None:
        assert "releases            List versioned releases" in stagingctl_text
        assert "rollback <id>       Switch active release" in stagingctl_text
