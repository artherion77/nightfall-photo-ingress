# Module 8 Operations Runbook

This runbook covers the Module 8 operational surface for `nightfall-photo-ingress`: status export, packaged systemd units, install flow, and staging-container smoke validation.

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

Install into `/opt/nightfall-photo-ingress` and register the packaged units:

```bash
sudo ./install/install.sh
```

Remove the installed files and units:

```bash
sudo ./install/uninstall.sh
```

## How To: Register Entra App for Graph (Operator Manual)

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
