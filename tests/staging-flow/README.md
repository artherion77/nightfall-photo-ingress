# tests/staging-flow — Staging production flow test suite

This directory contains the end-to-end production flow test for
`nightfall-photo-ingress`. It exercises the complete operator surface — every
CLI command a real operator would run — including interactive commands that
require human input (device-code browser onboarding).

## What it tests

| Phase | Kind | What is verified |
|-------|------|------------------|
| P1 | Automated | Container running, CLI `--help`, `auth-setup` discoverable, `config-check`, status file schema, directory layout, systemd units enabled |
| P2 | **Interactive** | `stagingctl auth-setup` (device-code login only, no discovery); token cache written; file mode 0600; identity sidecar; onboarding sidecar |
| P3 | **Interactive** | `stagingctl discover-paths` auto-discovers OneDrive paths using cached token (no new login); writeback to config |
| P4 | Semi-automated | `stagingctl smoke-live` (live poll + secret scan); status file reflects `poll` command |
| P5 | Automated | `stagingctl reset` restores clean snapshot; token cache absent; `config-check` still passes |

P2, P3, and P4 are skipped when `--skip-interactive` is passed (e.g. for CI pre-flight
checks against a known-good installed container).

## Files

- `flowctl` — interactive test controller script (executable)
- `test_flowctl_contracts.py` — static policy contracts (pytest, no live container needed)

## Prerequisites

1. A staging container must be created and have the application installed:

   ```bash
   stagingctl create
   stagingctl install
   ```

2. `STAGING_CLIENT_ID` must be set so the config has a real Azure client ID:

   ```bash
   export STAGING_CLIENT_ID=<your-app-registration-client-id>
   ```

3. For P2 (onboarding), the operator needs access to a browser and a staging OneDrive
   account that the Entra app registration is authorized for.

## Running

### Full flow (interactive):

```bash
tests/staging-flow/flowctl run
```

### Automated phases only (CI-friendly):

```bash
tests/staging-flow/flowctl run --skip-interactive
```

### Single phase:

```bash
tests/staging-flow/flowctl run --phase p1
tests/staging-flow/flowctl run --phase p2
tests/staging-flow/flowctl run --phase p3
tests/staging-flow/flowctl run --phase p4
tests/staging-flow/flowctl run --phase p5
```

### Static contract tests only (no container):

```bash
pytest tests/staging-flow/
```

## Evidence

Each `flowctl run` writes a timestamped evidence directory:

```
$FLOW_EVIDENCE_BASE/flow-<run_id>/
    manifest.jsonl          # flow start/finish events with exit code
    p1/                     # pre-flight logs
    p2/                     # auth-setup step logs
    p3/                     # path discovery logs
    p4/                     # live poll logs
    p5/                     # reset verification logs
```

`FLOW_EVIDENCE_BASE` defaults to `/mnt/ssd/staging/photo-ingress/evidence`
(same base as `stagingctl smoke`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONTAINER` | `staging-photo-ingress` | LXC container name |
| `STAGING_ACCOUNT` | `staging` | Account name used for onboarding and poll |
| `FLOW_EVIDENCE_BASE` | `/mnt/ssd/staging/photo-ingress/evidence` | Evidence output directory |
