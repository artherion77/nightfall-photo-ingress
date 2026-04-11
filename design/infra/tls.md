# Staging TLS Runbook (Phase 2 C2)

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Purpose

Define deterministic TLS termination and trust flow for staging LAN ingress.

Scope:
- in-container Caddy TLS termination
- container-local certificate material lifecycle
- operator trust-import path for staging CA

Out of scope:
- host-level TLS termination
- public CA issuance
- production PKI policy

## 2. TLS Invariants

1. TLS terminates in-container at Caddy only.
2. Staging ingress is HTTPS-only on port 443.
3. Host does not persist staging TLS private keys.
4. TLS artifacts are container-local under `/etc/caddy/tls`.
5. A staging-internal CA signs the Caddy leaf certificate.
6. Certificate generation is idempotent and automated by `stagingctl install`.
7. Canonical staging endpoint is `https://staging-photo-ingress.home.arpa`.

## 3. Container-Local Certificate Paths

- CA key: `/etc/caddy/tls/nightfall-staging-ca.key`
- CA cert: `/etc/caddy/tls/ca.pem`
- Leaf key: `/etc/caddy/tls/staging-photo-ingress.key`
- Leaf cert: `/etc/caddy/tls/staging-photo-ingress.crt`

## 4. Certificate Provisioning Flow

1. `stagingctl install` pushes Caddy config and invokes TLS provisioning inside the container.
2. If CA material is missing, generate a new internal CA key+cert.
3. Regenerate the leaf key and CSR on each `stagingctl install`, signed by the existing internal CA, with SANs:
   - `staging-photo-ingress`
   - `staging-photo-ingress.home.arpa`
   - `npi.pohl-family.org`
   - `localhost`
   - `127.0.0.1`
   - `::1`
4. Sign the leaf with the internal CA.
5. Set file permissions for Caddy runtime readability and key protection.
6. Validate Caddy config and restart `caddy.service`.
7. Export CA cert to repo-local trust path via `stagingctl export-ca`:
   - source: `/etc/caddy/tls/ca.pem`
   - destination: `tests/ca/staging-ca.pem`

## 5. Operator Trust Import

For browser trust in LAN testing, import CA cert `ca.pem` from inside the container into the operator trust store.

Container pull example:

```bash
lxc file pull staging-photo-ingress/etc/caddy/tls/ca.pem ./staging-ca.pem
```

After import, access staging UI over `https://staging-photo-ingress.home.arpa/`.

For automated test trust synchronization, use:

```bash
./dev/bin/stagingctl export-ca
```

This overwrites `tests/ca/staging-ca.pem` and prevents CA drift between staging runtime and host-side E2E clients.

## 6. Validation Checklist

1. `stagingctl smoke` passes TLS assertion `tls_https_only`.
2. HTTPS probe to `https://127.0.0.1/` succeeds from inside container.
3. HTTP probe to `http://127.0.0.1/` fails from inside container.
4. Caddy config validates prior to restart.
5. TLS artifact paths exist under `/etc/caddy/tls` and remain container-local.
