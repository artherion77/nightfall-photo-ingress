# Nightfall Photo Ingress: App Registration Design & Robustness

This document covers the design principles for app registration, error detection, and support for personal Microsoft accounts as the default and primary integration model.

## Design Principles

### Personal Accounts as Default

The `nightfall-photo-ingress` service is designed to integrate with **personal Microsoft accounts** (MSA) by default. This is the primary supported configuration:

- **Authority**: `https://login.microsoftonline.com/consumers`
- **Supported account types**: Personal Microsoft accounts only
- **Scope**: Delegated read-only access to the authenticated user's own OneDrive Camera Roll
- **Authentication**: Interactive device-code flow for initial auth, refresh token for subsequent runs

### Why Personal Accounts First?

1. **Single-user home server use case**: nightfall operates on personal home media server infrastructure
2. **No infrastructure overhead**: No tenant admin, no app-only permissions, no service principal management
3. **User controls access**: User initiates auth, user manages token revocation
4. **Least privilege by design**: Delegated (user context) permissions, no cross-user access

### Multi-Tenant Support (Future, Optional)

Work/school accounts can be supported via parallel app registrations configured with:

- **Authority**: Customer's tenant-specific endpoint (e.g., `https://login.microsoftonline.com/<tenant-id>`)
- **Supported account types**: Accounts in this organizational directory only
- **Requires**: Tenant admin consent for application permissions (if app-only is needed in future)

## Registration Robustness

### Error Detection in Auth Flow

The auth flow must robustly detect and surface common misconfiguration scenarios. The following MSAL errors should trigger detailed diagnostic hints:

#### AADSTS700016: Application Not Found

**When triggered**: MSAL's `initiate_device_flow()` returns error dict instead of `{user_code, verification_uri}`

**Root causes**:
- App registration deleted or not found in the directory
- `signInAudience` mismatch (app configured for work accounts only, but personal account used)
- `api.requestedAccessTokenVersion` not set to 2 (required for personal account flows)

**Current handling**: Caught in `auth.py:auth_setup()` line ~83, raises `AuthError` with generic message

**Improved handling** (design):
```python
if "error" in flow and "error_description" in flow:
    error_code = flow.get("error", "unknown")
    error_desc = flow.get("error_description", "")
    
    # Detect specific issues
    if error_code == "unauthorized_client":
        if "700016" in str(flow.get("error_codes")):
            hint = (
                "Application not found in directory. Check:\n"
                "  1. Client ID is correctly copied from Azure portal\n"
                "  2. App 'Supported account types' includes Personal Microsoft accounts\n"
                "  3. API token version is set to 2 (required for device code flow)\n"
                "  Azure portal: App registration → API settings → Requested token version"
            )
        elif "700022" in str(flow.get("error_codes")):
            hint = "Tenant policy may block this app. Contact admin."
        else:
            hint = f"Unauthorized client. Error: {error_desc[:100]}"
    else:
        hint = f"Device flow failed: {error_code}"
    
    raise AuthError(
        "Device-code flow did not complete",
        operation="device_code_initiate",
        safe_hint=hint
    )
```

#### AADSTS65001: User Consent Not Granted

**When triggered**: User cancels consent screen during device-code flow sign-in

**Current handling**: Propagated as `acquire_token_by_device_flow()` error

**Improved handling**: Surface as user-actionable message: "Sign-in was cancelled. Run auth-setup again and complete the consent prompt."

### Validation Checklist at Config Time

When `config-check` is run, validate:

✅ `client_id` format is valid (UUIDv4)
✅ `authority` is one of:
  - `https://login.microsoftonline.com/consumers` (personal accounts — default)
  - `https://login.microsoftonline.com/<tenant-id>` (org accounts)
  - No typos/misconfigurations

✅ Config file readable and parseable
✅ Token cache directory exists and parent is secure (mode 0700 recommended)

### Scope Normalization

Reserved OIDC scopes (`openid`, `profile`, `offline_access`) must never be passed explicitly to `initiate_device_flow()`. The runtime must filter these before calling MSAL:

- `Files.Read` ✅ passed to device flow
- `offline_access` ❌ never passed directly (MSAL manages refresh token implicitly)
- Scope validation is performed in `auth.py:_normalize_scopes()` at runtime

### Token Cache Security

Token cache must always be persisted with mode `0600` (read/write by owner only):

- Set via `os.chmod(cache_path, 0o600)` after write
- Validated at load time; reject if mode is >0600
- Parent directory must be mode `0700` (no cross-user access)

## Configuration Examples

### Personal Account (Default)

```ini
[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = 58996ba4-b840-498f-8ccc-7d1a98c071a0
onedrive_root = /Camera Roll
token_cache = /mnt/ssd/photo-ingress/tokens/primary.json
delta_cursor = /mnt/ssd/photo-ingress/cursors/primary.cursor
```

### Multi-Account Same Personal Tenant

```ini
[account.primary]
enabled = true
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = 58996ba4-b840-498f-8ccc-7d1a98c071a0
onedrive_root = /Camera Roll
token_cache = /mnt/ssd/photo-ingress/tokens/primary.json
delta_cursor = /mnt/ssd/photo-ingress/cursors/primary.cursor

[account.backup]
enabled = false
provider = onedrive
authority = https://login.microsoftonline.com/consumers
client_id = 58996ba4-b840-498f-8ccc-7d1a98c071a0
onedrive_root = /Camera Roll
token_cache = /mnt/ssd/photo-ingress/tokens/backup.json
delta_cursor = /mnt/ssd/photo-ingress/cursors/backup.cursor
```

## Testing & Validation

### Manual Validation Checklist

- [ ] App registration displays in Azure portal
- [ ] Application (client) ID matches config
- [ ] "Supported account types" is set to "Personal Microsoft accounts only"
- [ ] API token version set to 2
- [ ] Files.Read permission is granted
- [ ] Redirect URI is http://localhost (device flow doesn't require this but should be present)
- [ ] Run `config-check --path /etc/nightfall/photo-ingress.conf` passes
- [ ] Run `auth-setup --account <name>` completes device-code flow
- [ ] Token cache file created at configured path with mode 0600
- [ ] `poll --account <name>` succeeds without auth errors

### Staging Test Flow

Staging container tests validate app registration robustness:

- **P1: Smoke (pre-flight)**: Config validation, paths, schema
- **P2: Interactive auth**: Device-code flow, token cache, permission validation
- **P3: Authenticated poll**: Verify token refresh, Graph API access, file enumeration

## References

- [Microsoft Entra OAuth2 device flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code)
- [MSAL Python PublicClientApplication](https://msal-python.readthedocs.io/)
- [Microsoft Graph Files.Read permission](https://learn.microsoft.com/en-us/graph/permissions-reference#filesread)
- [Offline access and refresh tokens](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc)

## Changelog

### 2026-04-02

- Initial design document
- Personal accounts as primary integration model (no change to implementation, design clarification)
- AADSTS700016 diagnostic hints designed (not yet implemented)
- Token cache security validation checklist added
