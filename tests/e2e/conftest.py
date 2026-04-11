"""Session fixtures for E2E staging tests."""

from __future__ import annotations

import configparser
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tempfile

import httpx
import pytest


@dataclass(frozen=True)
class ContainerConfig:
    api_token: str
    bind_host: str
    bind_port: str


CONTAINER_NAME = os.environ.get("STAGING_CONTAINER", "staging-photo-ingress")
CONTAINER_CONF = os.environ.get("STAGING_CONF", "/etc/nightfall/photo-ingress.conf")
BASE_URL = os.environ.get(
    "STAGING_BASE_URL",
    "https://staging-photo-ingress.home.arpa",
)
CA_CERT_PATH = os.environ.get("STAGING_CA_BUNDLE", "")
CA_CERT_CONTAINER_PATH = "/etc/caddy/tls/nightfall-staging-ca.crt"


def _lxc_exec(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["lxc", "exec", CONTAINER_NAME, "--", *args],
        capture_output=True,
        text=True,
    )


def _require_staging_container() -> None:
    info = subprocess.run(["lxc", "info", CONTAINER_NAME], capture_output=True, text=True)
    if info.returncode != 0:
        pytest.skip(f"staging container '{CONTAINER_NAME}' not available")
    if "status: running" not in info.stdout.lower():
        pytest.skip(f"staging container '{CONTAINER_NAME}' is not running")


def _materialize_ca_bundle() -> str:
    if CA_CERT_PATH:
        return CA_CERT_PATH

    _require_staging_container()
    proc = _lxc_exec(["cat", CA_CERT_CONTAINER_PATH])
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip(f"unable to read staging CA cert at {CA_CERT_CONTAINER_PATH}")

    ca_file = Path(tempfile.gettempdir()) / "nightfall-staging-ca.crt"
    ca_file.write_text(proc.stdout, encoding="utf-8")
    return str(ca_file)


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def ca_bundle_path() -> str:
    return _materialize_ca_bundle()


@pytest.fixture(scope="session")
def container_config() -> ContainerConfig:
    _require_staging_container()

    proc = _lxc_exec(["cat", CONTAINER_CONF])
    if proc.returncode != 0:
        pytest.skip(f"unable to read staging config {CONTAINER_CONF}")

    parser = configparser.ConfigParser()
    parser.read_string(proc.stdout)

    if not parser.has_section("web"):
        pytest.skip("staging config missing [web] section")

    token = parser.get("web", "api_token", fallback="").strip()
    if not token:
        pytest.skip("staging config has empty [web] api_token")

    return ContainerConfig(
        api_token=token,
        bind_host=parser.get("web", "bind_host", fallback="").strip(),
        bind_port=parser.get("web", "bind_port", fallback="").strip(),
    )


@pytest.fixture(scope="session")
def api_client(container_config: ContainerConfig, ca_bundle_path: str) -> httpx.Client:
    headers = {"Authorization": f"Bearer {container_config.api_token}"}
    with httpx.Client(
        headers=headers,
        timeout=20.0,
        follow_redirects=True,
        verify=ca_bundle_path,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def unauthenticated_client(ca_bundle_path: str) -> httpx.Client:
    with httpx.Client(timeout=20.0, follow_redirects=True, verify=ca_bundle_path) as client:
        yield client


@pytest.fixture(scope="session")
def staging_container_name() -> str:
    return CONTAINER_NAME


@pytest.fixture(scope="session")
def template_path() -> Path:
    return Path("/home/chris/dev/nightfall-photo-ingress/staging/container/photo-ingress.conf")
