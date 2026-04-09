# Operations Runbook

This runbook is the operator source of truth for deployed runtime behavior,
production install and uninstall, packaged services, authentication bootstrap,
and staging validation before production rollout.

For developer workstation setup, dev container lifecycle, test taxonomy, and
promotion flow, use `docs/development-handbook.md`.

## Document map

Use this runbook for deployment and runtime operations. Use the focused operator
documents for task-specific procedures.

| Topic | Primary document |
|---|---|
| Runtime layout, packaged units, install and uninstall | this runbook |
| Routine workflows (accept, reject, purge, sync-import, status) | [docs/operator/operational-playbook.md](operator/operational-playbook.md) |
| CLI setup, auth setup, Entra registration details | [docs/operator/cli-guide.md](operator/cli-guide.md) |
| Failure handling and recovery | [docs/operator/troubleshooting.md](operator/troubleshooting.md) |
| Staging maintenance and validation flows | [docs/operator/maintenance.md](operator/maintenance.md) |

## Environment profiles

The project has three distinct execution environments:

| Environment | Purpose | Canonical entry point |
|---|---|---|
| Development container | build, unit tests, integration tests, local web work | `./dev/bin/govctl run devcontainer.prepare --json` |
| Staging container | packaged-wheel rehearsal, live auth bootstrap, smoke, browser E2E | `./dev/bin/govctl run staging.* --json` and staging flow tooling |
| Production container | unattended operator-managed polling and trash processing | `sudo ./install/install.sh` |

The dev and staging containers are validation environments. They are not the
production runtime.

## Runtime layout

The deployed service runtime is split across standard paths inside the target
LXC container.

| Path | Role |
|---|---|
| `/opt/nightfall-photo-ingress` | installed application payload |
| `/opt/nightfall-photo-ingress/share/doc/nightfall-photo-ingress` | packaged documentation |
| `/etc/nightfall/photo-ingress.conf` | operator-managed configuration |
| `/var/lib/ingress` | runtime working state |
| `/var/lib/ingress/tokens` | account token caches |
| `/var/lib/ingress/trash` | trash queue watched by systemd path unit |
| `/run/nightfall-status.d/photo-ingress.json` | status snapshot written by commands and services |
| `/var/log/nightfall` | optional file-backed logs when configured |

Host-side prerequisites and examples may reference storage locations such as
`/mnt/ssd/photo-ingress/`. Those are host layout examples, not replacements for
the in-container runtime paths above.

## Status file contract

The status file is written atomically by CLI commands and service-triggered
runs. Operators should treat it as the first-line health indicator.

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

Expected state values used for triage:

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

For deeper interpretation rules and operator responses, use
[docs/operator/operational-playbook.md](operator/operational-playbook.md).

## Packaged units

The packaged systemd unit set is:

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

If units are missing or inactive after deployment, consult
[docs/operator/troubleshooting.md](operator/troubleshooting.md).

## Install and uninstall

Production deployment targets an LXC container on the host. By default, the
installer creates or updates a container named `photo-ingress` using the
`ubuntu:24.04` image and the LXD `default` profile.

Operator-visible install options:

- `--container <name>`: override the target LXC container name
- `--image <image>`: override the LXC image used when the container must be created
- `--profile <name>`: override the LXC profile used when the container must be created

The same container override can also be supplied through
`TARGET_CONTAINER=<name>`.

Install or update the default production container:

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

### ZFS prerequisites

The production install path assumes the host-side storage and snapshot model are
prepared before the service is relied on operationally. Where host storage or
dataset layout is involved, verify that prerequisite datasets and mountpoints
exist before running the installer.

If the host storage contract has changed, update this runbook and the installer
documentation together.

## Authentication bootstrap

The service uses delegated Microsoft Graph access with device-code
authentication. No client secret is required for the supported flow.

The interactive bootstrap command is:

```bash
nightfall-photo-ingress auth-setup --account <account-name> --path /etc/nightfall/photo-ingress.conf
```

The command prints a verification URL and code. Complete sign-in in a browser,
then return to the terminal. On success, the account-scoped token cache is
created at the configured `token_cache` path and hardened to mode `0600`.

For app-registration steps, Graph permission requirements, and the current live
registration record, use [docs/operator/cli-guide.md](operator/cli-guide.md).

## Staging validation boundary

Staging is the required validation boundary for packaged runtime behavior. Use
it for wheel install rehearsal, live interactive auth, live poll validation,
and smoke checks before production rollout.

Canonical staging activities include:

- create or refresh the staging container
- install the built wheel into staging
- run interactive auth bootstrap when validating real credentials
- run smoke and live poll validation
- run staging-backed browser E2E when the change touches the web surface

Examples:

```bash
./dev/bin/govctl run staging.create --json
./dev/bin/govctl run staging.install --json
tests/staging-flow/flowctl run --phase p2
tests/staging-flow/flowctl run --phase p3
pytest tests/staging/test_smoke_contracts.py -m staging
```

Important boundary:

- Dev container flows validate developer build and test behavior.
- Staging validates packaged runtime and live integration behavior.
- Production rollout should follow a successful staging rehearsal.

The live auth bootstrap step still requires interactive operator participation.
If the current staging flow uses `stagingctl auth-setup`, continue to use that
interactive command during staging validation.

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

For broader recovery procedures and recurring fault patterns, use
[docs/operator/troubleshooting.md](operator/troubleshooting.md).

## Related documents

| Need | Document |
|---|---|
| developer setup, dev container lifecycle, test taxonomy, promotion flow | `docs/development-handbook.md` |
| routine CLI operations and status interpretation | [docs/operator/operational-playbook.md](operator/operational-playbook.md) |
| auth and Entra app registration details | [docs/operator/cli-guide.md](operator/cli-guide.md) |
| staging maintenance and live validation flows | [docs/operator/maintenance.md](operator/maintenance.md) |
| troubleshooting and recovery | [docs/operator/troubleshooting.md](operator/troubleshooting.md) |
