# Operations Runbook

**Status:** navigation index — content extracted to topic documents  

> This document is retained as a navigation index. All major sections have been extracted
> to focused operator documents. Refer to those documents for authoritative content.

---

## Document Map

| Topic | Document |
|---|---|
| Routine workflows (accept, reject, purge, sync-import, status) | [docs/operator/operational-playbook.md](operator/operational-playbook.md) |
| CLI setup (auth, Entra app registration, poll, packaged units) | [docs/operator/cli-guide.md](operator/cli-guide.md) |
| Failure handling, recovery, troubleshooting | [docs/operator/troubleshooting.md](operator/troubleshooting.md) |
| Install, runtime layout, environment setup | [docs/deployment/environment-setup.md](deployment/environment-setup.md) |
| Staging flows (P2 auth, P3 live poll, smoke tests) | [docs/operator/maintenance.md](operator/maintenance.md) |
| Development container lifecycle and scaffold | [docs/deployment/dev-container-workflow.md](deployment/dev-container-workflow.md) |

---

This runbook covers the production operational surface for `nightfall-photo-ingress`: status export, packaged systemd units, install flow, Entra app registration, and staging-container smoke validation.

## Runtime layout

> **Extracted** → [docs/deployment/environment-setup.md](deployment/environment-setup.md)

- Status snapshot: `/run/nightfall-status.d/photo-ingress.json`
- Config: `/etc/nightfall/photo-ingress.conf`
- Working state: `/var/lib/ingress`
- Logs: journald for systemd units and `/var/log/nightfall` for file outputs if configured

## Status file contract

> **Extracted** → [docs/operator/operational-playbook.md](operator/operational-playbook.md#status-file-interpretation)

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

> **Extracted** → [docs/operator/cli-guide.md](operator/cli-guide.md#packaged-systemd-units)

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

> **Extracted** → [docs/deployment/environment-setup.md](deployment/environment-setup.md#install-and-uninstall)

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

> **Extracted** → [docs/operator/cli-guide.md](operator/cli-guide.md#how-to-register-an-entra-app-for-graph)

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

> **Extracted** → [docs/operator/cli-guide.md](operator/cli-guide.md#registered-application-instance)

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

> **Extracted** → [docs/operator/troubleshooting.md](operator/troubleshooting.md)

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

## Staging Flow: P2 Interactive Authentication (Device-Code Flow)

> **Extracted** → [docs/operator/maintenance.md](operator/maintenance.md#staging-flow-p2--interactive-authentication-device-code-flow)

The staging test flow validates authentication and polling before production deployment. **P2** tests one-time interactive device-code setup.

### Prerequisites

- Staging container running (`./dev/bin/stagingctl create`)
- Wheel package built (`python -m build --wheel`)
- Real Azure app registration client ID (see *How To: Register Entra App for Graph*)
- Personal Microsoft account to authenticate with

### Run P2 Authentication Flow

```bash
export STAGING_CLIENT_ID="58996ba4-b840-498f-8ccc-7d1a98c071a0"  # your app client ID
./dev/bin/stagingctl install dist/nightfall_photo_ingress-0.1.0-py3-none-any.whl

tests/staging-flow/flowctl run --phase p2
```

### What P2 Validates

The flow will:
1. **P2.1**: Initiate device-code auth (`stagingctl auth-setup`)
2. Display a Microsoft sign-in URL and one-time code
3. User opens URL in browser, signs in with personal Microsoft account, completes consent
4. **P2.2**: Verify token cache file created (`/var/lib/ingress/tokens/staging.json`)
5. **P2.3**: Verify token cache has secure permissions (mode 0600)
6. **P2.4**: Check for account identity sidecar (written on first poll)

### Expected Output

```
── P2  Interactive authentication  [OPERATOR ACTION REQUIRED] ───

Open https://www.microsoft.com/link and enter code: XXXXXXXX

[stagingctl] OK: auth-setup completed for account 'staging'. Token cache written inside container.

[flowctl] PASS  P2.1:auth_setup_exit — stagingctl auth-setup completed (exit 0)
[flowctl] PASS  P2.2:token_cache_written — /var/lib/ingress/tokens/staging.json present
[flowctl] PASS  P2.3:token_cache_permissions — token file mode 0600 (secure)
[flowctl] All phases PASSED
```

### Troubleshooting P2 Failures

**Error: "Application with identifier '...' was not found in the directory"**

Root cause: App registration misconfigured. Check in Azure portal:
- [ ] Verify Application (client) ID matches config
- [ ] Verify "Supported account types" is set to "Personal Microsoft accounts only"
- [ ] Verify API token version is set to 2 (in Authentication → Advanced settings)

Fix: Update app registration, then rerun P2.

**Error: "Device-code flow did not return verification details"**

Root cause: MSAL cannot communicate with the auth endpoint. Check:
- [ ] Container has network access (`curl https://login.microsoftonline.com >/dev/null`)
- [ ] Config client_id is not a placeholder (check inside container: `cat /etc/nightfall/photo-ingress.conf | grep client_id`)

**Error: User cancels sign-in or consent**

User action required: Run P2 again and complete the full sign-in and consent flow.

## Staging Flow: P3 Live Authenticated Poll

> **Extracted** → [docs/operator/maintenance.md](operator/maintenance.md#staging-flow-p3--live-authenticated-poll)

**P3** validates that the cached token works and the application can access OneDrive files.

### Prerequisites

- P2 passed (token cache written)
- Application has `Files.Read` permission granted

### Run P3 Poll Flow

```bash
tests/staging-flow/flowctl run --phase p3
```

### What P3 Validates

The flow will:
1. **P3.1**: Verify token cache exists and is readable
2. **P3.2**: Run authenticated poll
   - Acquire token silently from cache (MSAL refresh token flow)
   - Enumerate OneDrive delta for Camera Roll / Bilder folder
   - Download file metadata and candidates
3. **P3.3**: Run ingest decision engine on downloaded candidates
4. **P3.4**: Verify no credentials leaked in logs (secret scan)

### Expected Output

```
── P3  Live authenticated poll  ──────────────────────────────

[stagingctl] Starting smoke-live: poll + secret scan ...

[flowctl] PASS  P3.1:token_cache_readable — /var/lib/ingress/tokens/staging.json readable
[flowctl] PASS  P3.2:poll_success — poll completed (exit 0)
[flowctl] PASS  P3.3:ingest_executed — ingest decision engine ran
[flowctl] PASS  P3.4:no_secrets_leaked — secret scan found no credentials
[flowctl] All phases PASSED
```

### Troubleshooting P3 Failures

**Error: "No cached account found for 'staging'. Run auth-setup first."**

Token cache is missing or not signed in. Run P2 again.

**Error: "Graph request returned error status"**

OneDrive path is incorrect or user lacks permission. Check:
- [ ] Configured `onedrive_root` exists in user's OneDrive (e.g., "/Camera Roll" or "/Bilder/Eigene Aufnahmen")
- [ ] User has read access to the folder
- [ ] Permission Files.Read is granted (check in Azure portal: App registration → API permissions)

**Error: Secret scan failed (credentials detected in logs)**

Review log files in `/mnt/ssd/staging/photo-ingress/logs/<run-id>` for leaked tokens or client IDs. Do not commit sensitive data.

## Controlled-environment validation

> **Extracted** → [docs/operator/maintenance.md](operator/maintenance.md#controlled-environment-validation)

Live systemd smoke testing must run in the staging container, not on the host. Use the staging workflow:

```bash
./dev/bin/stagingctl create
./dev/bin/stagingctl install
pytest tests/staging/test_smoke_contracts.py -m staging
```

These smoke checks should validate:

- the binary is installed and responds to `--version`
- `config-check` succeeds with the staging config
- poll and trash units are known to systemd inside the container

---

## Operator Workflows

> **Extracted** → [docs/operator/operational-playbook.md](operator/operational-playbook.md)

This section covers the routine CLI commands used to manage the ingest service.

### Config check

Validates the configuration file format, required keys, account sections, and path accessibility. Run this any time the config is modified.

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

A passing run exits 0 and prints a summary of all validated accounts. A failing run exits non-zero and prints actionable messages identifying which key or section is invalid.

### Accepting a file

Accept a file by its SHA-256 hash. This moves it from the pending queue to the accepted queue in the registry and writes an `accepted_records` row.

```bash
nightfall-photo-ingress accept <sha256> --path /etc/nightfall/photo-ingress.conf
```

Use when inspecting the pending queue and explicitly approving an item for permanent library inclusion. Accepted files are not moved to permanent storage by this command — a separate operator step moves the accepted queue to `/nightfall/media/photo-ingress/accepted/`.

### Rejecting a file

Reject a file by its SHA-256 hash. This marks the file as rejected in the registry with an audit record. Rejected files are blocked from re-download if OneDrive serves them again.

```bash
nightfall-photo-ingress reject <sha256> --reason "<description>" --path /etc/nightfall/photo-ingress.conf
```

The `--reason` flag is optional but strongly recommended for audit clarity. The actor recorded in the audit row will be `operator-cli`.

### Purging a file

Purge a file by its SHA-256 hash. This transitions the registry record to `purged` state and removes the physical staging copy if present.

```bash
nightfall-photo-ingress purge <sha256> --path /etc/nightfall/photo-ingress.conf
```

Purge is intended for records that are confirmed unwanted and should be completely removed from tracking. The audit history is retained.

### Processing the trash queue

Drain files placed in the trash directory by the operator. This command reads all items in `trash_path`, creates rejected registry records for each, removes the physical files, and emits audit rows.

```bash
nightfall-photo-ingress process-trash --path /etc/nightfall/photo-ingress.conf
```

This command is also triggered automatically by the `nightfall-photo-ingress-trash.path` systemd unit whenever files are dropped into the trash directory. The path unit watches `trash_path` and starts `nightfall-photo-ingress-trash.service` on change.

**Trash workflow:**
1. Operator drops a file into the configured `trash_path` directory.
2. `nightfall-photo-ingress-trash.path` detects the change.
3. `nightfall-photo-ingress-trash.service` runs `process-trash` automatically.
4. Audit log records the rejection with actor `trash-processor`.

To process manually (for example, when debugging the path unit):
```bash
systemctl start nightfall-photo-ingress-trash.service
```

### Sync-import from permanent library

Populate the registry with SHA-1 hashes from existing `.hashes.sha1` files in the permanent library. This prevents re-downloading files that are already in the library.

```bash
nightfall-photo-ingress sync-import --path /etc/nightfall/photo-ingress.conf
```

Run this once after initial deployment against an existing library. Also run it after bulk additions to the permanent library to keep the advisory hash index current. The command is read-only with respect to the library — it never modifies `.hashes.sha1` files.

Use `--dry-run` to preview the import without writing to the registry:

```bash
nightfall-photo-ingress sync-import --dry-run --path /etc/nightfall/photo-ingress.conf
```

---

## Status File Interpretation

> **Extracted** → [docs/operator/operational-playbook.md](operator/operational-playbook.md#status-file-interpretation)

The status file at `/run/nightfall-status.d/photo-ingress.json` is written atomically after each command run. Each `state` value indicates a specific condition and implies a specific operator action.

| State | Meaning | Operator action |
|-------|---------|----------------|
| `healthy` | Last command completed successfully with no anomalies | None required |
| `degraded` | Command completed but encountered recoverable issues (for example, partial poll due to runtime limit) | Check `details` field for specifics; monitor next poll result |
| `auth_failed` | MSAL token refresh failed; account cannot be polled | Run `nightfall-photo-ingress auth-setup --account <name>` to re-authenticate; check token cache permissions |
| `disk_full` | Staging or accepted path is below the configured minimum free space threshold | Free space on the relevant volume; poll will resume automatically |
| `ingest_error` | Ingest decision engine encountered an unexpected error processing one or more candidates | Inspect journald logs for the failed run ID; check staging directory for stale `.tmp` files |
| `registry_corrupt` | Registry integrity check failed (for example, WAL recovery failure) | Stop the service immediately; run SQLite integrity check (`PRAGMA integrity_check`); restore from last ZFS snapshot |

To read the status file:

```bash
jq . /run/nightfall-status.d/photo-ingress.json
jq .state /run/nightfall-status.d/photo-ingress.json
jq '{state, updated_at, command}' /run/nightfall-status.d/photo-ingress.json
```

If the status file is absent after a run, confirm that `/run/nightfall-status.d/` exists and is writable by the service user, then check journald output.

---

## Staged File Recovery

> **Extracted** → [docs/operator/troubleshooting.md](operator/troubleshooting.md#staged-file-recovery)

If the poll service crashes or is killed mid-run, follow this procedure to return to a consistent state.

### When recovery is needed

Signs that a partial poll run occurred:
- Status file shows `ingest_error` or is absent
- Stale `.tmp` files present in the `staging_path` directory
- Registry and journal are out of sync (pending rows without corresponding journal entries)

### Recovery procedure

**Step 1: Stop the poll timer to prevent overlapping runs**

```bash
systemctl stop nightfall-photo-ingress.timer
```

**Step 2: Inspect the staging directory**

```bash
find /var/lib/ingress/staging -name "*.tmp" -ls
find /var/lib/ingress/staging -type f -ls
```

`.tmp` files are incomplete downloads. They are safe to delete. Any non-`.tmp` file in staging that has a corresponding `pending` registry record was downloaded successfully but not finalized.

**Step 3: Run config-check to verify the service can start**

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

**Step 4: Remove stale `.tmp` files**

```bash
find /var/lib/ingress/staging -name "*.tmp" -delete
```

The next poll run will re-download any files that were only partially downloaded.

**Step 5: Restart the timer**

```bash
systemctl start nightfall-photo-ingress.timer
```

The next triggered poll will re-enumerate the delta from the last committed cursor position. Because all registry writes are idempotent, any files already recorded as `pending` will be recognized as known and will not be re-ingested.

**Note on working state path:** Inside the deployed LXC container, the working state directory is `/var/lib/ingress/`. This is the correct path for staging, tokens, cursors, and the registry database. The configuration example (`conf/photo-ingress.conf.example`) uses `/mnt/ssd/photo-ingress/` as a host-relative path example — that applies only to non-containerized deployments.
- the status file is created and parseable inside the container