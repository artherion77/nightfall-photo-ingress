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
