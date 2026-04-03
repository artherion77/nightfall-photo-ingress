from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_error_state_unauthorized_for_missing_token(api_client) -> None:
    response = await api_client.get("/api/v1/staging")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_spa_fallback_for_client_route(api_client, spa_build_stub) -> None:
    response = await api_client.get("/audit")
    assert response.status_code == 200
    assert "spa-fallback" in response.text


@pytest.mark.anyio
async def test_bearer_undefined_literal_is_rejected(api_client) -> None:
    """Regression: confirms the API rejects the literal string 'Bearer undefined'.

    A mis-compiled SPA bundle (import.meta.env.PUBLIC_API_TOKEN instead of the
    SvelteKit-idiomatic $env/static/public import) produces this exact header value
    at runtime.  Verified on the staging deploy 2026-04-03; fixed by switching to
    $env/static/public in client.ts and health.svelte.js.

    See audit/open-points/chunk3-ui-drift-analysis.md §2 Bug A.
    """
    response = await api_client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer undefined"},
    )
    assert response.status_code == 401
