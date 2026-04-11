# Staging Cloudflare Tunnel (Phase 2 C6/C7 Infra Extension)

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Purpose

Define deterministic and secure Cloudflare Tunnel integration for staging ingress reachability while preserving existing TLS termination boundaries.

Scope:
- staging container cloudflared runtime
- host-mounted token secret pattern
- operational status and validation checks

Out of scope:
- storing Cloudflare credentials inside the container image or writable filesystem
- replacing Caddy as TLS terminator

## 2. Architecture

1. The staging container runs cloudflared as a managed systemd service.
2. Cloudflared authenticates with a pre-provisioned tunnel token.
3. The token is mounted from host path `/home/chris/.cloudflare-secrets/npi-staging/tunnel-token` to container path `/etc/cloudflared/token`.
4. The mount is read-only and must remain read-only.
5. Caddy stays in-container and remains the TLS terminator for the application.
6. Cloudflare Tunnel forwards traffic to the staging endpoint; it does not terminate application TLS in this architecture.

## 3. Authentication Model and Secret Handling

1. Authentication uses token-based tunnel run mode:
   - `cloudflared tunnel run --token $(cat /etc/cloudflared/token)`
2. The token file is host-owned and never copied into container writable layers.
3. No Cloudflare credentials may persist under container-local paths such as:
   - `/root/.cloudflared`
   - `/etc/cloudflared/*.json`
   - `/var/lib/cloudflared/*.json`
4. Validation must fail if credential artifacts are detected in container-local filesystem paths.

## 4. Service Supervision Model

1. Service name: `cloudflared-tunnel.service`
2. Managed by container systemd:
   - enabled at boot
   - restarted on failure
3. Service logs are collected via `journalctl` for troubleshooting.
4. `stagingctl cloudflared-status` is the operator status command to verify:
   - token mount policy
   - service active state
   - tunnel connectivity signals in logs
   - recent logs tail

## 5. DNS and TLS Implications

1. DNS points the Cloudflare tunnel hostname to Cloudflare edge as usual.
2. Inside staging, Caddy remains the TLS endpoint for the app.
3. Cloudflare Origin Certificates or TLS passthrough can be used between Cloudflare and origin, but deployment policy must preserve:
   - Caddy as the only application TLS terminator
   - no host-level TLS termination
4. Existing staging internal CA flow for LAN/operator trust remains valid and independent of cloudflared token auth.

## 6. Operational Validation Checklist

1. `stagingctl create` mounts `/etc/cloudflared/token` as read-only from host secret path.
2. `stagingctl install` verifies token mount, installs cloudflared when missing, and starts `cloudflared-tunnel.service`.
3. `stagingctl cloudflared-status --strict` succeeds with tunnel-connected log evidence.
4. `govctl run staging.validate --json` fails fast with actionable diagnostics when tunnel posture drifts.
