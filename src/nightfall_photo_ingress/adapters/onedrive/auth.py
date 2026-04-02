"""Authentication helpers for the OneDrive client.

OneDrive client scope:
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
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import stat

import msal

from nightfall_photo_ingress.config import AccountConfig
from .cache_lock import cache_file_lock
from .errors import AuthError  # noqa: F401  re-export so existing imports work

DEFAULT_SCOPES = ["Files.Read"]
RESERVED_SCOPES = frozenset({"openid", "profile", "offline_access"})

__all__ = ["AuthError", "AccessToken", "OneDriveAuthClient"]


@dataclass(frozen=True)
class AccessToken:
    """Container for access token responses used by the adapter."""

    token: str


class OneDriveAuthClient:
    """MSAL wrapper with strict, account-scoped token cache handling."""

    def __init__(self, scopes: list[str] | None = None) -> None:
        self._scopes = self._normalize_scopes(scopes or DEFAULT_SCOPES)

    @staticmethod
    def _normalize_scopes(scopes: list[str]) -> list[str]:
        """Drop reserved OIDC scopes and de-duplicate while preserving order."""

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_scope in scopes:
            scope = raw_scope.strip()
            if not scope:
                continue
            if scope.lower() in RESERVED_SCOPES:
                continue
            lowered = scope.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(scope)

        if not normalized:
            raise AuthError(
                "No valid non-reserved scopes configured for token acquisition.",
                operation="scope_normalize",
            )

        return normalized

    def auth_setup(self, account: AccountConfig) -> AccessToken:
        """Run interactive device-code flow and persist cache securely."""
        with cache_file_lock(account.token_cache):
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
            self._persist_account_identity(account, app.get_accounts())
            return AccessToken(token=token)

    def acquire_access_token(self, account: AccountConfig) -> AccessToken:
        """Acquire a token using cached accounts and silent refresh."""
        with cache_file_lock(account.token_cache):
            app, cache = self._build_app(account)
            accounts = app.get_accounts()

            if not accounts:
                raise AuthError(
                    f"No cached account found for '{account.name}'. Run auth-setup first.",
                    account=account.name,
                    operation="acquire_silent",
                )

            expected_identity = self._load_expected_identity(account)
            selected_account = self._select_account(accounts, expected_identity, account)

            result = app.acquire_token_silently(self._scopes, account=selected_account)
            token = self._extract_token(result, account=account.name)
            self._save_cache(account.token_cache, cache)
            self._persist_account_identity(account, accounts)
            return AccessToken(token=token)

    def _build_app(
        self,
        account: AccountConfig,
    ) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
        """Create a PublicClientApplication seeded from account cache file."""

        self._ensure_cache_parent(account.token_cache)
        self._validate_secure_parent_dir(account.token_cache.parent)
        if account.token_cache.exists():
            self._validate_secure_file(account.token_cache, 0o600)

        cache = msal.SerializableTokenCache()
        if account.token_cache.exists():
            try:
                cache.deserialize(account.token_cache.read_text(encoding="utf-8"))
            except Exception as exc:
                quarantined = self._quarantine_corrupt_cache(account.token_cache)
                raise AuthError(
                    (
                        f"Token cache is corrupted for '{account.name}'. "
                        f"Run auth-setup again. Corrupt cache moved to '{quarantined.name}'."
                    ),
                    account=account.name,
                    operation="cache_deserialize",
                    safe_hint=f"Cache deserialize failed: {type(exc).__name__}",
                ) from exc

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
    def _identity_path(cache_path: Path) -> Path:
        """Return sidecar identity path bound to this cache path."""

        if cache_path.suffix:
            return cache_path.with_suffix(cache_path.suffix + ".identity.json")
        return Path(str(cache_path) + ".identity.json")

    def _load_expected_identity(self, account: AccountConfig) -> dict[str, str] | None:
        """Load expected identity sidecar for silent-token account binding."""

        identity_path = self._identity_path(account.token_cache)
        if not identity_path.exists():
            return None

        self._validate_secure_parent_dir(identity_path.parent)
        self._validate_secure_file(identity_path, 0o600)

        try:
            payload = json.loads(identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthError(
                (
                    f"Identity metadata is unreadable for '{account.name}'. "
                    "Run auth-setup to refresh token binding."
                ),
                account=account.name,
                operation="identity_load",
                safe_hint=f"Identity metadata read failed: {type(exc).__name__}",
            ) from exc

        if not isinstance(payload, dict):
            raise AuthError(
                (
                    f"Identity metadata format invalid for '{account.name}'. "
                    "Run auth-setup to refresh token binding."
                ),
                account=account.name,
                operation="identity_load",
            )

        self._validate_identity_integrity(payload, account)

        identity: dict[str, str] = {}
        for key in ("home_account_id", "username"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                identity[key] = value
        return identity or None

    def _persist_account_identity(
        self,
        account: AccountConfig,
        accounts: list[dict[str, object]],
    ) -> None:
        """Persist account identity fields used for future silent binding."""

        if not accounts:
            return

        selected = accounts[0]
        payload: dict[str, str] = {
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        for key in ("home_account_id", "username", "local_account_id"):
            value = selected.get(key)
            if isinstance(value, str) and value:
                payload[key] = value

        payload["integrity_sha256"] = self._identity_integrity_hash(payload, account)

        identity_path = self._identity_path(account.token_cache)
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.chmod(identity_path, 0o600)

    @staticmethod
    def _select_account(
        available_accounts: list[dict[str, object]],
        expected_identity: dict[str, str] | None,
        account: AccountConfig,
    ) -> dict[str, object]:
        """Select and validate silent-token account identity.

        Selection policy:
        - If identity metadata exists, match by home_account_id or username.
        - If identity metadata is missing and only one cached account exists, use it.
        - If identity metadata is missing and multiple accounts exist, fail closed.
        """

        if expected_identity:
            expected_home = expected_identity.get("home_account_id")
            expected_user = expected_identity.get("username")
            for candidate in available_accounts:
                candidate_home = candidate.get("home_account_id")
                candidate_user = candidate.get("username")
                if expected_home and candidate_home == expected_home:
                    return candidate
                if expected_user and candidate_user == expected_user:
                    return candidate
            raise AuthError(
                (
                    f"Cached token identity mismatch for '{account.name}'. "
                    "Run auth-setup to rebind the account cache."
                ),
                account=account.name,
                operation="identity_bind",
                safe_hint=(
                    "No cached MSAL account matched persisted "
                    "home_account_id/username"
                ),
            )

        if len(available_accounts) == 1:
            return available_accounts[0]

        raise AuthError(
            (
                f"Multiple cached identities found for '{account.name}' without binding metadata. "
                "Run auth-setup to pin account identity."
            ),
            account=account.name,
            operation="identity_bind",
        )

    @staticmethod
    def _quarantine_corrupt_cache(cache_path: Path) -> Path:
        """Move a corrupted cache file aside and return the new path."""

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantined = cache_path.with_suffix(cache_path.suffix + f".corrupt.{timestamp}")
        cache_path.replace(quarantined)
        return quarantined

    @staticmethod
    def _ensure_cache_parent(cache_path: Path) -> None:
        """Create parent directory with owner-only permissions."""

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(cache_path.parent, 0o700)

    @staticmethod
    def _validate_secure_parent_dir(path: Path) -> None:
        """Validate parent directory is owner-only (0700)."""

        if not path.exists():
            return

        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != 0o700:
            raise AuthError(
                f"Insecure permissions on '{path}'. Expected 0700.",
                operation="permission_check",
                safe_hint=f"directory mode={oct(mode)}",
            )

    @staticmethod
    def _validate_secure_file(path: Path, expected_mode: int) -> None:
        """Validate file is owner-only (0600 by default)."""

        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != expected_mode:
            raise AuthError(
                f"Insecure permissions on '{path}'. Expected {oct(expected_mode)}.",
                operation="permission_check",
                safe_hint=f"file mode={oct(mode)}",
            )

    @staticmethod
    def _identity_integrity_hash(payload: dict[str, str], account: AccountConfig) -> str:
        """Compute deterministic integrity hash for identity sidecar payload."""

        canonical = {
            "account": account.name,
            "client_id": account.client_id,
            "home_account_id": payload.get("home_account_id", ""),
            "username": payload.get("username", ""),
            "local_account_id": payload.get("local_account_id", ""),
        }
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _validate_identity_integrity(
        self,
        payload: dict[str, object],
        account: AccountConfig,
    ) -> None:
        """Validate identity sidecar integrity attestation."""

        expected = payload.get("integrity_sha256")
        if not isinstance(expected, str) or not expected:
            raise AuthError(
                (
                    f"Identity metadata integrity missing for '{account.name}'. "
                    "Run auth-setup to rebind token identity."
                ),
                account=account.name,
                operation="identity_load",
                safe_hint="missing integrity_sha256",
            )

        source: dict[str, str] = {}
        for key in ("home_account_id", "username", "local_account_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                source[key] = value

        actual = self._identity_integrity_hash(source, account)
        if actual != expected:
            raise AuthError(
                (
                    f"Identity metadata integrity mismatch for '{account.name}'. "
                    "Run auth-setup to rebind token identity."
                ),
                account=account.name,
                operation="identity_load",
                safe_hint="identity sidecar hash mismatch",
            )

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
