"""Helpers for isolated web control plane API tests."""

from __future__ import annotations


def auth_headers(api_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_token}"}
