# Auth Design

Status: active
Date: 2026-04-02
Updated: 2026-04-03
Author: Systems Engineering

## Overview

This document describes the design principles governing authentication in
`nightfall-photo-ingress`: account model, MSAL integration, error detection,
token cache security, and scope handling.

For the operator-facing procedures (app registration steps, device-code flow, and the
registered instance record), see `docs/app-registration-design.md`.

For the error hierarchy, retry policy, and resilience design, see
`design/architecture/error-taxonomy-and-resilience.md`.

For diagnostic counters and observability fields emitted by the auth client, see
`design/architecture/observability.md`.

---

## 1. Account Model

The service authenticates on behalf of a human user using the OAuth 2.0 device-code
flow. This is a **delegated** permission model — the service acts as the signed-in user
and has no more access than the user has granted.

**Personal Microsoft accounts (MSA) are the primary integration model.** This is the
correct choice for a single-user home media server:

- Authority: `https://login.microsoftonline.com/consumers`
- Supported account types: Personal Microsoft accounts only
- Scopes: `Files.Read` (user's own OneDrive Camera Roll)
- Authentication: interactive device-code flow for initial setup; MSAL refresh token
  for unattended polling

Work/school accounts are supported via a separately registered app registration using
the tenant-specific authority (`https://login.microsoftonline.com/<tenant-id>`).

---

## 2. MSAL Integration

The OneDrive adapter uses `msal.PublicClientApplication` with a file-backed token cache.
Each account section in the config has its own token cache file.

Key design choices:

- **No client secret**: The app is registered as a public client. No secret is required
  or assigned. The device-code flow does not need a redirect URI to function.
- **Token cache isolation**: Each account's cache is stored at the path configured in
  `token_cache`. Two accounts never share a cache file.
- **Singleton lock**: `runtime/cache_lock.py` implements a per-account singleton lock
  (`account_singleton_lock`) to prevent concurrent poll runs from writing to the same
  token cache. See `design/domain-architecture-overview.md` for the full process-lock
  architecture.
- **Refresh token persistence**: `offline_access` is implicit in delegated flows; MSAL
  manages refresh token storage. The operator does not need to request `offline_access`
  explicitly in the scope list.

---

## 3. Error Detection in the Auth Flow

The auth flow must robustly detect and surface common misconfiguration scenarios.
The following MSAL errors trigger detailed diagnostic hints in `AuthError`:

### AADSTS700016: Application Not Found

**When triggered**: `initiate_device_flow()` returns an error dict instead of
`{user_code, verification_uri}`.

**Root causes**:
- App registration deleted or not found in the directory.
- `signInAudience` mismatch (app configured for work accounts only but personal
  account used).
- `api.requestedAccessTokenVersion` not set to 2 (required for personal account flows).

**Design resolution**:

```python
if "error" in flow and "error_description" in flow:
    error_code = flow.get("error", "unknown")
    if error_code == "unauthorized_client":
        if "700016" in str(flow.get("error_codes")):
            hint = (
                "Application not found in directory. Check:\n"
                "  1. Client ID is correctly copied from Azure portal\n"
                "  2. App 'Supported account types' includes Personal Microsoft accounts\n"
                "  3. API token version is set to 2 (required for device code flow)\n"
                "  Azure portal: App registration → API settings → Requested token version"
            )
```

### AADSTS65001: User Consent Not Granted

**When triggered**: User cancels the consent screen during the device-code sign-in.

**Design resolution**: Surface as a user-actionable message:
`"Sign-in was cancelled. Run auth-setup again and complete the consent prompt."`

---

## 4. Scope Normalization

Reserved OIDC scopes (`openid`, `profile`, `offline_access`) must never be passed
explicitly to `initiate_device_flow()`. MSAL manages these implicitly.

The runtime filters the configured scope list before calling MSAL:

- `Files.Read` — passed to the device flow
- `offline_access` — never passed directly; MSAL adds it automatically
- Scope filtering is performed in `auth.py:_normalize_scopes()` at runtime

Passing reserved scopes explicitly causes MSAL to emit warnings or fail in some
authority configurations. The normalize step prevents this.

---

## 5. Token Cache Security

Token cache files must always be persisted with mode `0600` (owner read/write only):

- Set via `os.chmod(cache_path, 0o600)` immediately after write.
- Validated at load time; if the mode exceeds `0600`, the load is rejected with an
  `AuthError` and a remediation hint.
- The parent directory is expected to be mode `0700`; the auth client does not
  enforce this but the installer and config-check validation do.

**Rationale**: Token cache files contain MSAL refresh tokens. A leaked refresh token
grants full delegated access to OneDrive until revoked. Strict file permissions are the
primary control.

---

## 6. Config Validation at `config-check`

When `config-check` is run, the auth-related config keys are validated:

- `client_id` format is a valid UUID v4.
- `authority` is one of the recognizable forms:
  `https://login.microsoftonline.com/consumers` or a tenant-specific endpoint.
- Token cache path exists and parent directory is accessible.
- Token cache file (if present) has mode `0600`.

See `design/domain-architecture-overview.md` §11 for the full config key reference.

---

## 7. References

- `src/nightfall_photo_ingress/adapters/onedrive/auth.py` — MSAL integration
- `src/nightfall_photo_ingress/adapters/onedrive/cache_lock.py` — singleton lock
- `design/architecture/error-taxonomy-and-resilience.md` — `AuthError` hierarchy and resilience
- `design/architecture/observability.md` — auth diagnostic counter keys
- `design/domain-architecture-overview.md` §13 — error taxonomy summary
- `docs/app-registration-design.md` — operator procedures (app registration, bootstrap)
