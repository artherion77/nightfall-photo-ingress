# staging — Nightfall LXC staging subsystem

This directory contains the policy-compliant staging subsystem for
`nightfall-photo-ingress`.

Staging does not own the product unit definitions. Canonical deployable units live in `../systemd/`; this directory only carries container-specific systemd drop-in overrides so staging validates the same unit names and base contracts that production installs.

The subsystem is intentionally minimal and non-invasive:

- uses one LXC container (`staging-photo-ingress`)
- does not modify host network definitions
- does not modify host Python, host systemd, or host packages
- keeps rollback deterministic via snapshot `clean`

## Launch contract and profiles

Container creation uses the existing LXD profiles only:

```bash
lxc launch ubuntu:24.04 staging-photo-ingress -p default -p staging
```

No host network creation or host bridge mutation is performed.

## Network architecture

- Bridge: `br-staging`
- Bridge manager: Netplan (host-managed)
- Host IP on bridge: none
- VLAN mode: untagged native VLAN1
- VLAN20/Citadel: never used for staging containers

Expected NIC attributes on the container:

- `type: nic`
- `nictype: bridged`
- `parent: br-staging`

`stagingctl create` validates this container-side network policy.

## Storage modes

### Persistent mode (default)

- Host evidence: `/mnt/ssd/staging/photo-ingress/evidence`
- Host logs: `/mnt/ssd/staging/photo-ingress/logs`
- Container evidence mount point: `/var/lib/ingress/evidence`
- Container logs mount point: `/var/log/nightfall`

### Volatile mode (`STAGING_VOLATILE=1`)

- Host evidence: `/run/staging-photo-ingress/evidence` (tmpfs)
- Host logs: `/run/staging-photo-ingress/logs` (tmpfs)
- Container evidence mount point: `/run/staging-photo-ingress/evidence`
- Container logs mount point: `/run/staging-photo-ingress/logs`

## tmpfs boundaries inside the container

To prevent uncontrolled rootfs writes, `stagingctl create` mounts tmpfs on:

- `/tmp`
- `/var/tmp`
- `/var/cache/nightfall-photo-ingress`

These mounts are recreated by `create` and naturally reset by snapshot restore.

## Lifecycle commands

- `stagingctl create`
  creates container, runs setup, mounts storage and tmpfs boundaries, installs units,
  and creates snapshot `clean`
- `stagingctl install [wheel]`
  pushes wheel and config into container, installs in `/opt/ingress` venv,
  enables timer and trash path units
- `stagingctl reset`
  restores snapshot `clean` and restarts container
- `stagingctl uninstall`
  removes container only
- `stagingctl uninstall --purge`
  removes container and host evidence/log directories for the active storage mode

## Evidence and smoke

`stagingctl smoke` writes run artifacts to:

- `<host-evidence-base>/<run-id>/`

where host-evidence-base is mode-dependent (`/mnt/ssd/...` or `/run/...`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `STAGING_VOLATILE` | `0` | `1` => volatile `/run/staging-photo-ingress/*`; `0` => persistent `/mnt/ssd/staging/photo-ingress/*` |
| `STAGING_CLIENT_ID` | unset | Azure client id substitution for staging config |
| `STAGING_ACCOUNT` | `staging` | account name passed to poll command |
| `STAGING_TOKEN_JSON` | unset | optional token cache pushed into container |
| `STAGING_EVIDENCE_BASE` | mode-derived default | optional override for evidence path |
| `STAGING_LOG_BASE` | mode-derived default | optional override for log path |

## Tests

- Policy and script contracts (no host mutation): `tests/staging/test_stagingctl_policy_contracts.py`
- Evidence and scanner unit tests: `tests/staging/test_evidence_contracts.py`, `tests/staging/test_secret_scan.py`
- Container smoke contracts (require live container): `tests/staging/test_smoke_contracts.py`

## Directory overview

```text
staging/
  stagingctl
  container/
    setup.sh
    photo-ingress.conf
  systemd/
    nightfall-photo-ingress.service.d/
      override.conf
    nightfall-photo-ingress.timer.d/
      override.conf
    nightfall-photo-ingress-trash.path.d/
      override.conf
    nightfall-photo-ingress-trash.service.d/
      override.conf
  evidence/
    capture.py
    secret_scan.py
```
