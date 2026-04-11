"""Helpers for running Playwright specs inside the staging container."""

from __future__ import annotations

import subprocess
from pathlib import Path


RUNNER_ROOT = "/opt/nightfall-webui-runner"
CA_CERT_IN_STAGING = "/etc/caddy/tls/nightfall-staging-ca.crt"


def container_is_running(name: str) -> bool:
    proc = subprocess.run(["lxc", "info", name], capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    return "status: running" in proc.stdout.lower()


def ensure_staging_playwright_runner_ready(staging_container: str, repo_root: Path) -> None:
    sync_cmd = (
        f"cd {repo_root}/webui && "
        "tar -czf - package.json package-lock.json playwright.config.ts tests/e2e tests/playwright-shim.d.ts "
        f"| lxc exec {staging_container} -- bash -lc \"set -e; mkdir -p {RUNNER_ROOT}; tar -xzf - -C {RUNNER_ROOT}\""
    )
    sync = subprocess.run(["bash", "-lc", sync_cmd], capture_output=True, text=True)
    if sync.returncode != 0:
        raise AssertionError(
            "failed to sync Playwright runner files into staging container:\n"
            f"stdout:\n{sync.stdout}\n\n"
            f"stderr:\n{sync.stderr}"
        )

    bootstrap_cmd = (
        "set -euo pipefail; "
        "if ! command -v node >/dev/null 2>&1; then "
        "  apt-get update >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs npm >/dev/null; "
        "fi; "
        f"cp -f {CA_CERT_IN_STAGING} /usr/local/share/ca-certificates/nightfall-staging-ca.crt; "
        "update-ca-certificates >/dev/null; "
        f"cd {RUNNER_ROOT}; "
        "if [[ ! -d node_modules ]]; then npm ci >/dev/null; fi; "
        "npx playwright install --with-deps chromium >/dev/null"
    )
    bootstrap = subprocess.run(
        ["lxc", "exec", staging_container, "--", "bash", "-lc", bootstrap_cmd],
        capture_output=True,
        text=True,
    )
    if bootstrap.returncode != 0:
        raise AssertionError(
            "failed to prepare Playwright runtime in staging container:\n"
            f"stdout:\n{bootstrap.stdout}\n\n"
            f"stderr:\n{bootstrap.stderr}"
        )


def run_playwright_spec_in_staging(staging_container: str, spec: str, base_url: str) -> None:
    cmd = (
        "set -euo pipefail; "
        f"cd {RUNNER_ROOT}; "
        f"NODE_EXTRA_CA_CERTS={CA_CERT_IN_STAGING} "
        f"STAGING_CA_BUNDLE={CA_CERT_IN_STAGING} "
        "PLAYWRIGHT_IGNORE_HTTPS_ERRORS=1 "
        f"STAGING_BASE_URL={base_url} "
        f"npx playwright test {spec} --reporter=line"
    )
    proc = subprocess.run(
        ["lxc", "exec", staging_container, "--", "bash", "-lc", cmd],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "playwright checks failed in staging container:\n"
            f"stdout:\n{proc.stdout}\n\n"
            f"stderr:\n{proc.stderr}"
        )
