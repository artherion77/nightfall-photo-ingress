# Nightfall Photo Ingress: App Registration (Operator Guide)

This document covers the operator procedures for registering and configuring the
Microsoft Entra app required by `nightfall-photo-ingress`.

For design-level documentation (authentication principles, MSAL integration, error
detection design, scope normalization, and token cache security), see
`design/auth-design.md`.

---

## Design Principles

### Personal Accounts as Default

The `nightfall-photo-ingress` service uses **personal Microsoft accounts** (MSA) as the primary integration model:

- **Authority**: `https://login.microsoftonline.com/consumers`
- **Supported account types**: Personal Microsoft accounts only
- **Scope**: Delegated read-only access to the signed-in user's own OneDrive Camera Roll
- **Authentication**: Interactive device-code flow for initial setup; MSAL refresh token for subsequent unattended polls

Work/school accounts use a tenant-specific authority (`https://login.microsoftonline.com/<tenant-id>`). See `design/auth-design.md` for design rationale and scope normalization rules.

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
