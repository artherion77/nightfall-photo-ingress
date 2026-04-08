"""E2E Module 1 staging health tests (Cases 12-15)."""

from __future__ import annotations

import configparser
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest


CASE13_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/staging"),
    ("GET", "/api/v1/audit/log"),
    ("GET", "/api/v1/config/effective"),
    ("GET", "/api/v1/health"),
)


@pytest.mark.staging
def test_case_12_api_systemd_service_is_active(staging_container_name: str) -> None:
    """Case 12: API systemd service is active in staging container."""
    proc = subprocess.run(
        [
            "lxc",
            "exec",
            staging_container_name,
            "--",
            "systemctl",
            "is-active",
            "nightfall-photo-ingress-api.service",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr.strip()
    assert proc.stdout.strip() == "active"


@pytest.mark.staging
def test_case_13_all_four_spa_gateway_endpoints_return_200(
    api_client,
    base_url: str,
) -> None:
    """Case 13: canonical gateway endpoint set returns 200 with JSON payloads."""
    evidence: list[dict[str, str | int]] = []

    for method, path in CASE13_ENDPOINTS:
        response = api_client.request(method, f"{base_url}{path}")
        evidence.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": method,
                "url": f"{base_url}{path}",
                "status_code": response.status_code,
            }
        )

        assert response.status_code == 200, f"{method} {path} returned {response.status_code}"
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, f"{method} {path} returned non-JSON content"

    assert len(evidence) == 4


@pytest.mark.staging
def test_case_14_spa_static_files_served(
    unauthenticated_client,
    base_url: str,
) -> None:
    """Case 14: GET / returns SPA HTML fallback with HTTP 200."""
    response = unauthenticated_client.get(f"{base_url}/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.staging
def test_case_15_config_template_sections_complete(template_path: Path) -> None:
    """Case 15: staging template contains required sections and web keys."""
    assert template_path.exists(), "staging template is missing"

    parser = configparser.ConfigParser()
    parser.read(template_path, encoding="utf-8")

    required_sections = ("core", "account.staging", "logging", "web")
    for section in required_sections:
        assert parser.has_section(section), f"missing section [{section}]"

    required_web_keys = ("api_token", "bind_host", "bind_port", "cors_allowed_origins")
    for key in required_web_keys:
        value = parser.get("web", key, fallback="").strip()
        assert value, f"missing or empty [web] {key}"
