"""E2E Module 1 token consistency tests (Cases 6-8)."""

from __future__ import annotations

import configparser
import json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path("/home/chris/dev/nightfall-photo-ingress")
ENV_PATH = REPO_ROOT / "webui" / ".env"
BUILD_PATH = REPO_ROOT / "webui" / "build"
HOST_ENV_JS_PATH = BUILD_PATH / "_app" / "env.js"
DEV_CONTAINER_BUILD_ROOT = "/opt/nightfall-webui/build"
DEV_CONTAINER_NAME = "dev-photo-ingress"
STAGING_CONTAINER = "staging-photo-ingress"
STAGING_CONF = "/etc/nightfall/photo-ingress.conf"


def _read_public_api_token(env_path: Path) -> str:
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("PUBLIC_API_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
            break
    raise AssertionError("PUBLIC_API_TOKEN is missing or empty in webui/.env")


def _read_ini_token(config_path: Path) -> str:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")
    if not parser.has_section("web"):
        raise AssertionError("staging template is missing [web] section")
    token = parser.get("web", "api_token", fallback="").strip()
    if not token:
        raise AssertionError("staging template [web] api_token is missing or empty")
    return token


def _parse_env_js_token(env_js: str) -> str:
    match = re.search(r"export const env=(\{.*\})", env_js.strip())
    if match is None:
        raise AssertionError("compiled env.js has an unexpected format")

    payload = json.loads(match.group(1))
    token = str(payload.get("PUBLIC_API_TOKEN", "")).strip()
    if not token:
        raise AssertionError("compiled env.js is missing PUBLIC_API_TOKEN")
    return token


def _read_baked_build_token() -> str:
    if HOST_ENV_JS_PATH.exists():
        return _parse_env_js_token(HOST_ENV_JS_PATH.read_text(encoding="utf-8"))

    proc = subprocess.run(
        [
            "lxc",
            "exec",
            DEV_CONTAINER_NAME,
            "--",
            "cat",
            f"{DEV_CONTAINER_BUILD_ROOT}/_app/env.js",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError("unable to read compiled build/_app/env.js from dev container build output")
    return _parse_env_js_token(proc.stdout)


def _read_staging_runtime_token() -> str:
    proc = subprocess.run(
        [
            "lxc",
            "exec",
            STAGING_CONTAINER,
            "--",
            "python3",
            "-c",
            (
                "import configparser; "
                f"p=configparser.ConfigParser(); p.read('{STAGING_CONF}'); "
                "print(p.get('web', 'api_token', fallback='').strip())"
            ),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError("unable to read deployed staging config token")
    token = proc.stdout.strip()
    if not token:
        raise AssertionError("deployed staging config [web] api_token is missing or empty")
    return token


@pytest.mark.staging
def test_case_6_built_spa_contains_template_token(template_path: Path) -> None:
    """Case 6: built SPA artifact contains the same token as the staging template."""
    baked_token = _read_baked_build_token()
    template_token = _read_ini_token(template_path)
    assert baked_token == template_token, "compiled SPA token and staging template token diverge"


@pytest.mark.staging
def test_case_7_webui_env_matches_staging_template(template_path: Path) -> None:
    """Case 7: source token in webui/.env matches the staging template token."""
    source_token = _read_public_api_token(ENV_PATH)
    template_token = _read_ini_token(template_path)
    assert source_token == template_token, "frontend and staging template token sources diverge"


@pytest.mark.staging
def test_case_8_running_staging_api_accepts_deployed_config_token(
    unauthenticated_client,
    base_url: str,
) -> None:
    """Case 8: token read from deployed staging config is accepted by the running API."""
    runtime_token = _read_staging_runtime_token()
    response = unauthenticated_client.get(
        f"{base_url}/api/v1/health",
        headers={"Authorization": f"Bearer {runtime_token}"},
    )
    assert response.status_code == 200, "running API rejected the token from deployed staging config"