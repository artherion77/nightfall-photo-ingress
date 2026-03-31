"""Authentication helpers for OneDrive adapter.

Module 3 scope:
- account-scoped token cache management
- device-code auth setup
- silent token refresh for polling

Chunk 1 change:
- AuthError consolidated in errors.py; imported here for backwards compatibility.
- All raise sites use structured AuthError with safe_hint; raw MSAL error
  descriptions are stored as hints only, never in the primary exception message.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import msal

from ..config import AccountConfig
from .errors import AuthError  # noqa: F401  re-export so existing imports work

DEFAULT_SCOPES = ["Files.Read", "offline_access"]

__all__ = ["AuthError", "AccessToken", "OneDriveAuthClient"]


@dataclass(frozen=True)
class AccessToken:
    """Container for access token responses used by the adapter."""

    token: str


class OneDriveAuthClient:
    """MSAL wrapper with strict, account-scoped token cache handling."""

    def __init__(self, scopes: list[str] | None = None) -> None:
        self._scopes = scopes or DEFAULT_SCOPES

    def auth_setup(self, account: AccountConfig) -> AccessToken:
        """Run interactive device-code flow and persist cache securely."""

        app, cache = self._build_app(account)

        flow = app.initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow or "verification_uri" not in flow:
            raise AuthError(
                "Device-code flow did not return verification details",
                account=account.name,
                operation="device_code_initiate",
            )

        print(
            "Open {uri} and enter code: {code}".format(
                uri=flow["verification_uri"],
                code=flow["user_code"],
            )
        )

        result = app.acquire_token_by_device_flow(flow)
        token = self._extract_token(result, account=account.name)
        self._save_cache(account.token_cache, cache)
        return AccessToken(token=token)

    def acquire_access_token(self, account: AccountConfig) -> AccessToken:
        """Acquire a token using cached accounts and silent refresh."""

        app, cache = self._build_app(account)
        accounts = app.get_accounts()

        if not accounts:
            raise AuthError(
                f"No cached account found for '{account.name}'. Run auth-setup first.",
                account=account.name,
                operation="acquire_silent",
            )

        result = app.acquire_token_silent(self._scopes, account=accounts[0])
        token = self._extract_token(result, account=account.name)
        self._save_cache(account.token_cache, cache)
        return AccessToken(token=token)

    def _build_app(
        self,
        account: AccountConfig,
    ) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
        """Create a PublicClientApplication seeded from account cache file."""

        cache = msal.SerializableTokenCache()
        if account.token_cache.exists():
            cache.deserialize(account.token_cache.read_text(encoding="utf-8"))

        self._ensure_cache_parent(account.token_cache)
        app = msal.PublicClientApplication(
            client_id=account.client_id,
            authority=account.authority,
            token_cache=cache,
        )
        return app, cache

    def _save_cache(
        self,
        cache_path: Path,
        cache: msal.SerializableTokenCache,
    ) -> None:
        """Persist token cache and enforce strict file permissions."""

        if not cache.has_state_changed:
            if cache_path.exists():
                os.chmod(cache_path, 0o600)
            return

        self._ensure_cache_parent(cache_path)
        cache_path.write_text(cache.serialize(), encoding="utf-8")
        os.chmod(cache_path, 0o600)

    @staticmethod
    def _ensure_cache_parent(cache_path: Path) -> None:
        """Create parent directory with owner-only permissions."""

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(cache_path.parent, 0o700)

    @staticmethod
    def _extract_token(
        result: dict[str, object] | None,
        account: str | None = None,
    ) -> str:
        """Extract ``access_token`` from an MSAL response.

        The MSAL ``error_description`` field may contain PII (username, tenant
        hints).  It is stored only as a safe_hint (structured log field) and
        never embedded in the primary exception message.
        """
        if not result or "access_token" not in result:
            error_desc = str(
                (result or {}).get("error_description", "No access token returned")
            )
            raise AuthError(
                "Token acquisition failed \u2013 run auth-setup to re-authenticate",
                account=account,
                operation="extract_token",
                safe_hint=error_desc,
            )
        return str(result["access_token"])
