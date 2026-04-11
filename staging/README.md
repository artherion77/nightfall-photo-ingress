# staging — Nightfall LXC staging subsystem

This directory contains the policy-compliant staging subsystem for
`nightfall-photo-ingress`.

Staging does not own the product unit definitions. Canonical deployable units live in `../systemd/`; this directory only carries container-specific systemd drop-in overrides so staging validates the same unit names and base contracts that production installs.

The subsystem is intentionally minimal and non-invasive:

- uses one LXC container (`staging-photo-ingress`)
- uses Caddy as the mandatory ingress boundary for LAN exposure
- does not modify host network definitions
- does not modify host Python, host systemd, or host packages
- keeps rollback deterministic via snapshot `clean`
- installs web control-plane runtime dependencies (`.[web]`) only inside the
  container venv (`/opt/ingress`), never as host-level dev packages

## Reverse proxy boundary (Phase 2 C1)

- Caddy listens on container port `80` and owns all ingress.
- Static SPA assets are served from `/opt/webui/build` by Caddy.
- API requests under `/api/*` are reverse-proxied to `127.0.0.1:8000`.
- Uvicorn remains localhost-bound in staging via `nightfall-photo-ingress-api.service.d/override.conf`.

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
  pushes wheel and config into container, installs in `/opt/ingress` venv with
  web extras (`[web]`), enables timer and trash path units
- `stagingctl auth-setup`
  runs `nightfall-photo-ingress auth-setup` interactively inside the container
  via TTY pass-through; the operator completes the Entra device-code flow in a browser.
  Writes the token cache and identity sidecar to the container's `/var/lib/ingress/tokens/`.
  **This is the correct authentication path for live testing.**
- `stagingctl smoke`
  runs headless (no-auth) assertions and collects evidence
- `stagingctl smoke-live`
  runs after `auth-setup`; performs a live authenticated poll and secret scan.
  Fails fast if no token cache is present.
- `stagingctl reset`
  restores snapshot `clean` and restarts container.
  Auth state written at install time is cleared; re-run `auth-setup` after reset.
- `stagingctl uninstall`
  removes container only
- `stagingctl uninstall --purge`
  removes container and host evidence/log directories for the active storage mode

## Authentication for live testing

Production uses the MSAL delegated device-code flow with per-account identity binding.
Staging must exercise the same path.

**Recommended workflow:**

```bash
stagingctl create
stagingctl install
stagingctl smoke            # headless: config, dirs, units, status file
stagingctl auth-setup       # interactive: complete device-code auth in browser
stagingctl smoke-live       # live: authenticated poll + secret scan
```

`auth-setup` runs inside the container (TTY pass-through). The operator sees the
device-code URL in their terminal and completes sign-in in a browser. After
completion, the token cache and identity sidecar are verified automatically.

After `stagingctl reset`, auth state is cleared (the snapshot was taken before
`install`). Re-run `auth-setup` to re-authenticate.

## Development boundary

Staging is intentionally a release-validation environment. Web UI development
tooling belongs to the dedicated development container model (`dev-photo-ingress`)
defined in `docs/deployment/dev-container-workflow.md` and
`design/architecture/environment-separation-and-container-lifecycle.md`.

## Evidence and smoke

All smoke commands write run artifacts to `<host-evidence-base>/<run-id>/`:

- `manifest.jsonl` — smoke start/finish events
- `assertions.jsonl` — per-assertion pass/fail records
- `*.log` — raw command output captured per step

Host-evidence-base is mode-dependent (`/mnt/ssd/...` or `/run/...`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `STAGING_VOLATILE` | `0` | `1` => volatile `/run/staging-photo-ingress/*`; `0` => persistent `/mnt/ssd/staging/photo-ingress/*` |
| `STAGING_CLIENT_ID` | unset | Azure client id substituted into staging config |
| `STAGING_ACCOUNT` | `staging` | account name passed to `auth-setup` and `poll` |
| `STAGING_TOKEN_JSON` | unset | **[DEPRECATED]** Use `stagingctl auth-setup` instead |
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
    Caddyfile
    photo-ingress.conf
  systemd/
    nightfall-photo-ingress-api.service.d/
      override.conf
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
