# Operations Runbook

This runbook covers the production operational surface for `nightfall-photo-ingress`: status export, packaged systemd units, install flow, Entra app registration, and staging-container smoke validation.

## Runtime layout

- Status snapshot: `/run/nightfall-status.d/photo-ingress.json`
- Config: `/etc/nightfall/photo-ingress.conf`
- Working state: `/var/lib/ingress`
- Logs: journald for systemd units and `/var/log/nightfall` for file outputs if configured

## Status file contract

The status file is written atomically by CLI commands and systemd-triggered runs.

Expected top-level fields:

- `schema_version`
- `service`
- `version`
- `host`
- `state`
- `success`
- `command`
- `updated_at`
- `details`

Expected state values for operator triage:

- `healthy`
- `degraded`
- `auth_failed`
- `disk_full`
- `ingest_error`
- `registry_corrupt`

Quick inspection:

```bash
sudo cat /run/nightfall-status.d/photo-ingress.json
jq . /run/nightfall-status.d/photo-ingress.json
```

## Packaged units

The packaged unit set is:

- `nightfall-photo-ingress.service`: runs a single poll
- `nightfall-photo-ingress.timer`: schedules periodic polls
- `nightfall-photo-ingress-trash.path`: watches the trash queue directory
- `nightfall-photo-ingress-trash.service`: drains queued rejection requests

Common checks:

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

## Install and uninstall

Production deployment targets an LXC container on the host. By default, the installer creates or updates a container named `photo-ingress` using the `ubuntu:24.04` image and the LXD `default` profile only.

Operator-visible install options:

- `--container <name>`: override the target LXC container name
- `--image <image>`: override the LXC image used when the container must be created
- `--profile <name>`: override the LXC profile used when the container must be created

The same container override can also be supplied through `TARGET_CONTAINER=<name>`.

Inside the container, the service is installed into `/opt/nightfall-photo-ingress`, packaged units are installed under `/etc/systemd/system`, and the operator documentation is installed under `/opt/nightfall-photo-ingress/share/doc/nightfall-photo-ingress`.

```bash
sudo ./install/install.sh
```

Override the default container name:

```bash
sudo ./install/install.sh --container my-photo-ingress
```

Override the launch image when creating a new container:

```bash
sudo ./install/install.sh --image ubuntu:24.04
```

Override the launch profile when creating a new container:

```bash
sudo ./install/install.sh --profile default
```

Override container name, image, and profile together:

```bash
sudo ./install/install.sh \
  --container my-photo-ingress \
  --image ubuntu:24.04 \
  --profile default
```

Remove the production LXC container:

```bash
sudo ./install/uninstall.sh
```

Remove a non-default container:

```bash
sudo ./install/uninstall.sh --container my-photo-ingress
```

## How To: Register Entra App for Graph

This service uses delegated Microsoft Graph access with device-code authentication. No client secret is required for the V1 flow.

### Prerequisites

- You can sign in to Microsoft Entra admin center for the tenant that will own the app registration.
- Your account has rights to register applications (for example Application Developer).
- You know whether your source account is a personal Microsoft account or a work/school account.

### Register the app

1. Open Microsoft Entra admin center: `https://entra.microsoft.com`.
2. Go to Entra ID -> App registrations -> New registration.
3. Name: choose a clear operator name such as `nightfall-photo-ingress`.
4. Supported account types:
   - For personal OneDrive (`authority = https://login.microsoftonline.com/consumers`): select `Personal Microsoft accounts only`.
   - For work/school tenant usage: select the tenant option matching your policy and set `authority` accordingly in config.
5. Redirect URI is not required for device-code flow in this project.
6. Select Register.
7. Copy and store Application (client) ID.

### Configure Graph delegated permissions

1. Open the app registration -> API permissions.
2. Add a permission -> Microsoft Graph -> Delegated permissions.
3. Add `Files.Read`.
4. Keep least privilege; do not add broader file scopes unless required by an approved change.
5. `offline_access` is requested by the runtime and should be available for delegated consent flows.
6. If your tenant policy requires admin consent, complete admin consent in API permissions.

### Apply to photo-ingress config

1. Edit `/etc/nightfall/photo-ingress.conf`.
2. In `[account.<name>]`, set:
   - `provider = onedrive`
   - `authority = https://login.microsoftonline.com/consumers` (or tenant authority for org usage)
   - `client_id = <Application (client) ID>`
3. Save and run:

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

### Bootstrap token cache (device code)

Run one-time auth setup for each account section:

```bash
nightfall-photo-ingress auth-setup --account <account-name> --path /etc/nightfall/photo-ingress.conf
```

The command prints a verification URL and code. Complete sign-in in a browser, then return to the terminal.

Expected result:

- Account-scoped token cache file is created at configured `token_cache`.
- File mode is hardened to `0600` by the auth client.

### Verify Graph access

Run a bounded poll cycle:

```bash
nightfall-photo-ingress --log-mode json poll --account <account-name> --path /etc/nightfall/photo-ingress.conf
```

If auth and permissions are correct, the run should proceed without authentication errors and update the account cursor file.

### References

- App registration quickstart: `https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app`
- Graph permissions reference: `https://learn.microsoft.com/en-us/graph/permissions-reference`
- OIDC/offline_access behavior: `https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc`

## Registered Application Instance (Tenant: christopherpohlsrvgmail.onmicrosoft.com)

This section records the live Entra app registration provisioned for this service. It serves as the operator source of truth for the registration identity.

### Registration details

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

### Assigned API permissions

All permissions are delegated (user context). No application permissions are granted.

| API | Permission | Type | Purpose |
|---|---|---|---|
| Microsoft Graph | User.Read | Delegated | Sign-in identity baseline required by delegated flows |
| Microsoft Graph | Files.Read | Delegated | Read files in signed-in user's own OneDrive (Camera Roll) |
| Microsoft Graph | offline_access | Delegated | Allow MSAL refresh token persistence for unattended polling |

No admin consent required. All permissions are user-consentable.

### Purpose

This app registration grants the `nightfall-photo-ingress` service on the `nightfall` home server read-only, delegated access to the OneDrive Camera Roll of the authenticating user account. Access is scoped to the signed-in user's own OneDrive only — no cross-user, no SharePoint, no mail or calendar access.

Initial authentication is performed via one-time interactive device-code flow (`nightfall-photo-ingress auth-setup`). Subsequent unattended runs use the MSAL refresh token stored in the account-scoped token cache.

### How to use this registration in config

In `/etc/nightfall/photo-ingress.conf` inside the production container:

```ini
[account.<name>]
provider = onedrive
authority = https://login.microsoftonline.com/a5b95c9c-7a31-4337-9193-517a9646430e
client_id = 58996ba4-b840-498f-8ccc-7d1a98c071a0
```

### Portal deep link

Direct link to this registration in Entra portal:

```
https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Overview/appId/58996ba4-b840-498f-8ccc-7d1a98c071a0/isMSAApp~/false
```

### How this registration was provisioned

Provisioned on 2026-04-02 via Azure CLI from the `nightfall` remote host using the directory administrator account:

```bash
# 1. Create app registration (public client)
az ad app create \
  --display-name "Nightfall Photo Ingress" \
  --sign-in-audience AzureADMyOrg \
  --is-fallback-public-client true \
  --public-client-redirect-uris "http://localhost" \
  --web-home-page-url "http://npi.pohl-family.org"

# 2. Assign delegated Graph permissions
#    User.Read, Files.Read, offline_access
az ad app permission add \
  --id 58996ba4-b840-498f-8ccc-7d1a98c071a0 \
  --api 00000003-0000-0000-c000-000000000000 \
  --api-permissions \
    e1fe6dd8-ba31-4d61-89e7-88639da4683d=Scope \
    10465720-29dd-4523-a11a-6a75c743c9d5=Scope \
    7427e0e9-2fba-42fe-b0c0-848c9e6a8182=Scope
```

The deletion of a stale legacy service principal (`azure-cli-2021-11-14-15-03-15`, provisioned 2021 for Terraform, secret expired 2022, no role assignments) was performed in the same session as a prerequisite cleanup step.

## Failure handling

If the timer or path unit is not active:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nightfall-photo-ingress.timer
sudo systemctl enable --now nightfall-photo-ingress-trash.path
```

If the status file is missing after a run:

- Confirm `/run/nightfall-status.d` exists and is writable by the service.
- Run `nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf` manually.
- Inspect journald output for serialization or permission failures.

If trash processing does not trigger:

- Confirm queue files land in `/var/lib/ingress/trash`.
- Check `systemctl status nightfall-photo-ingress-trash.path`.
- Start the processor directly with `systemctl start nightfall-photo-ingress-trash.service` to separate path-watch failures from processor failures.

## Controlled-environment validation

Live systemd smoke testing must run in the staging container, not on the host. Use the staging workflow:

```bash
./staging/stagingctl create
./staging/stagingctl install
pytest tests/staging/test_smoke_contracts.py -m staging
```

These smoke checks should validate:

- the binary is installed and responds to `--version`
- `config-check` succeeds with the staging config
- poll and trash units are known to systemd inside the container
- the status file is created and parseable inside the container