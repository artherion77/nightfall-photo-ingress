# Maintenance and Staging Validation

**Status:** active  
**Source:** extracted from `docs/operations-runbook.md` §Staging Flow P2, §Staging Flow P3, §Controlled-environment validation  
**See also:** [troubleshooting.md](troubleshooting.md), [cli-guide.md](cli-guide.md), [deployment/environment-setup.md](../deployment/environment-setup.md)

---

## Overview

This document covers the staging validation flows used to verify authentication and polling before production deployment, and the controlled-environment smoke testing contracts.

---

## Staging Flow: P2 — Interactive Authentication (Device-Code Flow)

P2 tests one-time interactive device-code setup.

### Prerequisites

- Staging container running (`./staging/stagingctl create`)
- Wheel package built (`python -m build --wheel`)
- Real Azure app registration client ID (see [cli-guide.md](cli-guide.md))
- Personal Microsoft account to authenticate with

### Run P2 Authentication Flow

```bash
export STAGING_CLIENT_ID="58996ba4-b840-498f-8ccc-7d1a98c071a0"  # your app client ID
./staging/stagingctl install dist/nightfall_photo_ingress-0.1.0-py3-none-any.whl

tests/staging-flow/flowctl run --phase p2
```

### What P2 Validates

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

For P2 troubleshooting, see [troubleshooting.md](troubleshooting.md#troubleshooting-p2-interactive-authentication-device-code-flow).

---

## Staging Flow: P3 — Live Authenticated Poll

P3 validates that the cached token works and the application can access OneDrive files.

### Prerequisites

- P2 passed (token cache written)
- Application has `Files.Read` permission granted

### Run P3 Poll Flow

```bash
tests/staging-flow/flowctl run --phase p3
```

### What P3 Validates

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

For P3 troubleshooting, see [troubleshooting.md](troubleshooting.md#troubleshooting-p3-live-authenticated-poll).

---

## Controlled-Environment Validation

Live systemd smoke testing must run in the staging container, not on the host.

```bash
./staging/stagingctl create
./staging/stagingctl install
pytest tests/staging/test_smoke_contracts.py -m staging
```

Smoke checks validate:
- The binary is installed and responds to `--version`.
- `config-check` succeeds with the staging config.
- Poll and trash units are known to systemd inside the container.

---

*For failure handling during staging, see [troubleshooting.md](troubleshooting.md).*  
*For install and container setup, see [deployment/environment-setup.md](../deployment/environment-setup.md).*
