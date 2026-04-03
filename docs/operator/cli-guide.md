# CLI Guide

**Status:** active  
**Source:** extracted from `docs/operations-runbook.md` §How To: Register Entra App for Graph, §Registered Application Instance, §Operator Workflows (config-check), §Packaged units  
**See also:** [operational-playbook.md](operational-playbook.md), [troubleshooting.md](troubleshooting.md), [deployment/environment-setup.md](../deployment/environment-setup.md)

---

## Overview

This guide covers the CLI commands for initial setup (Entra app registration, auth bootstrap) and regular operational use (config check, poll, status inspection).

For queue management commands (accept, reject, purge, sync-import), see [operational-playbook.md](operational-playbook.md).

---

## How To: Register an Entra App for Graph

The service uses delegated Microsoft Graph access with device-code authentication. No client secret is required.

### Prerequisites

- Access to Microsoft Entra admin center for the owning tenant.
- Rights to register applications (e.g. Application Developer role).
- Know whether the source account is a personal Microsoft account or a work/school account.

### Register the App

1. Open Microsoft Entra admin center: `https://entra.microsoft.com`.
2. Go to **Entra ID → App registrations → New registration**.
3. Name: choose a clear operator name such as `nightfall-photo-ingress`.
4. Supported account types:
   - Personal OneDrive (`authority = https://login.microsoftonline.com/consumers`): select **Personal Microsoft accounts only**.
   - Work/school tenant: select the tenant option matching your policy.
5. Redirect URI: not required for device-code flow.
6. Select **Register**.
7. Copy and store the **Application (client) ID**.

### Configure Graph Delegated Permissions

1. Open the app registration → **API permissions**.
2. **Add a permission → Microsoft Graph → Delegated permissions**.
3. Add `Files.Read`.
4. Keep least privilege; do not add broader file scopes unless required by an approved change.
5. `offline_access` is requested by the runtime and must be available for delegated consent flows.
6. If your tenant policy requires admin consent, complete admin consent in API permissions.

### Apply to Config

1. Edit `/etc/nightfall/photo-ingress.conf`.
2. In `[account.<name>]`:
   ```ini
   provider = onedrive
   authority = https://login.microsoftonline.com/consumers
   client_id = <Application (client) ID>
   ```
3. Validate:
   ```bash
   nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
   ```

### Bootstrap Token Cache (Device Code, One-Time)

```bash
nightfall-photo-ingress auth-setup --account <account-name> --path /etc/nightfall/photo-ingress.conf
```

The command prints a verification URL and code. Complete sign-in in a browser, then return. Expected result:
- Account-scoped token cache file is created at configured `token_cache`.
- File mode is hardened to `0600` by the auth client.

### Verify Graph Access

```bash
nightfall-photo-ingress --log-mode json poll --account <account-name> --path /etc/nightfall/photo-ingress.conf
```

If auth and permissions are correct, the run proceeds without authentication errors and updates the account cursor file.

### References

- App registration quickstart: `https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app`
- Graph permissions reference: `https://learn.microsoft.com/en-us/graph/permissions-reference`
- OIDC/offline_access behavior: `https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc`

---

## Registered Application Instance

This section records the live Entra app registration provisioned for this service.

| Field | Value |
|---|---|
| Display name | Nightfall Photo Ingress |
| Application (client) ID | 58996ba4-b840-498f-8ccc-7d1a98c071a0 |
| Object ID | 00579402-4440-4515-a7e5-36b6b41cff86 |
| Tenant | a5b95c9c-7a31-4337-9193-517a9646430e |
| Publisher domain | christopherpohlsrvgmail.onmicrosoft.com |
| Sign-in audience | AzureADMyOrg (single tenant) |
| Platform type | Mobile and desktop application (public client) |
| Redirect URI | http://localhost |
| Homepage URL | http://npi.pohl-family.org |
| Created | 2026-04-02 |
| Client secret | None (public client — no secret required or assigned) |

### Assigned API Permissions

| API | Permission | Type | Purpose |
|---|---|---|---|
| Microsoft Graph | User.Read | Delegated | Sign-in identity baseline required by delegated flows |
| Microsoft Graph | Files.Read | Delegated | Read files in signed-in user's own OneDrive (Camera Roll) |
| Microsoft Graph | offline_access | Delegated | Allow MSAL refresh token persistence for unattended polling |

No admin consent required. All permissions are user-consentable.

### Config for this Registration

```ini
[account.<name>]
provider = onedrive
authority = https://login.microsoftonline.com/a5b95c9c-7a31-4337-9193-517a9646430e
client_id = 58996ba4-b840-498f-8ccc-7d1a98c071a0
```

### Portal Deep Link

```
https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Overview/appId/58996ba4-b840-498f-8ccc-7d1a98c071a0/isMSAApp~/false
```

---

## Packaged systemd Units

| Unit | Purpose |
|---|---|
| `nightfall-photo-ingress.service` | Runs a single poll |
| `nightfall-photo-ingress.timer` | Schedules periodic polls |
| `nightfall-photo-ingress-trash.path` | Watches the trash queue directory |
| `nightfall-photo-ingress-trash.service` | Drains queued rejection requests |

Common inspection commands:

```bash
systemctl status nightfall-photo-ingress.timer
systemctl status nightfall-photo-ingress.service
systemctl status nightfall-photo-ingress-trash.path
systemctl status nightfall-photo-ingress-trash.service
systemctl cat nightfall-photo-ingress.service
systemctl cat nightfall-photo-ingress-trash.service
journalctl -u nightfall-photo-ingress.service -n 50 --no-pager
journalctl -u nightfall-photo-ingress-trash.service -n 50 --no-pager
```

---

*For queue management workflows, see [operational-playbook.md](operational-playbook.md).*  
*For failure handling, see [troubleshooting.md](troubleshooting.md).*  
*For install and runtime layout, see [deployment/environment-setup.md](../deployment/environment-setup.md).*
