"""E2E Module 1 auth handshake tests (Cases 1-5)."""

from __future__ import annotations

import configparser
import sqlite3
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import verify_api_token
from nightfall_photo_ingress.config import AppConfig, load_config


def _latest_auth_failure(audit_payload: dict) -> list[dict]:
    events = audit_payload.get("events", [])
    return [event for event in events if event.get("action") == "auth_failure"]


def _make_inmemory_registry() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256 TEXT,
            account_name TEXT,
            action TEXT NOT NULL,
            reason TEXT,
            details_json TEXT,
            actor TEXT NOT NULL,
            ts TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _load_config_variant(
    template_path: Path,
    temp_path: Path,
    *,
    include_web: bool,
    api_token_override: str | None,
) -> AppConfig:
    parser = configparser.ConfigParser()
    parser.read(template_path, encoding="utf-8")

    if include_web:
        if not parser.has_section("web"):
            parser.add_section("web")
        if api_token_override is not None:
            parser.set("web", "api_token", api_token_override)
    elif parser.has_section("web"):
        parser.remove_section("web")

    with temp_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)

    return load_config(temp_path)


def _build_local_auth_client(app_config: AppConfig) -> TestClient:
    app = FastAPI()
    app.state.app_config = app_config
    app.state.registry_conn = _make_inmemory_registry()

    @app.get("/api/v1/health")
    async def _health(_: str = Depends(verify_api_token)) -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


@pytest.mark.staging
def test_case_1_valid_bearer_token_returns_200(api_client, base_url: str) -> None:
    """Case 1: valid bearer token is accepted by the health endpoint."""
    response = api_client.get(f"{base_url}/api/v1/health")
    assert response.status_code == 200


@pytest.mark.staging
def test_case_2_missing_authorization_header_returns_401_with_audit(
    unauthenticated_client,
    api_client,
    base_url: str,
) -> None:
    """Case 2: missing auth header returns explicit 401 and writes audit row."""
    response = unauthenticated_client.get(f"{base_url}/api/v1/health")
    assert response.status_code == 401
    assert response.json().get("detail") == "Missing Authorization header"

    audit = api_client.get(f"{base_url}/api/v1/audit/log", params={"action": "auth_failure", "limit": 30})
    assert audit.status_code == 200
    failures = _latest_auth_failure(audit.json())
    assert any(item.get("reason") == "Missing Authorization header" for item in failures)


@pytest.mark.staging
def test_case_3_wrong_bearer_token_returns_401_with_audit(
    unauthenticated_client,
    api_client,
    base_url: str,
) -> None:
    """Case 3: wrong token returns explicit 401 and writes audit row."""
    response = unauthenticated_client.get(
        f"{base_url}/api/v1/health",
        headers={"Authorization": "Bearer wrong-token-value"},
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Invalid token"

    audit = api_client.get(f"{base_url}/api/v1/audit/log", params={"action": "auth_failure", "limit": 30})
    assert audit.status_code == 200
    failures = _latest_auth_failure(audit.json())
    assert any(item.get("reason") == "Invalid token" for item in failures)


def test_case_4_empty_api_token_returns_401_deterministic_fixture(
    tmp_path: Path,
    template_path: Path,
) -> None:
    """Case 4: empty [web] api_token deterministically returns 401."""
    app_config = _load_config_variant(
        template_path,
        tmp_path / "case4-empty-token.conf",
        include_web=True,
        api_token_override="",
    )
    client = _build_local_auth_client(app_config)

    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer any-token"},
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "API token not configured"


def test_case_5_missing_web_section_returns_401_deterministic_fixture(
    tmp_path: Path,
    template_path: Path,
) -> None:
    """Case 5: missing [web] section deterministically returns 401."""
    app_config = _load_config_variant(
        template_path,
        tmp_path / "case5-missing-web.conf",
        include_web=False,
        api_token_override=None,
    )
    client = _build_local_auth_client(app_config)

    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer any-token"},
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "API token not configured"