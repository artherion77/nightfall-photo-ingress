# Staging Invariants (Phase 2 Infra Baseline)

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Purpose

This document defines the canonical Phase-2 staging infrastructure invariants for Web Control Plane reconciliation.

Scope:
- staging container infrastructure
- staging installer behavior contract
- staging policy tests and static contracts

Out of scope:
- runtime code changes
- container mutation in this reconciliation pass

## 2. Phase-2 Infra Baseline

The Phase-2 baseline is strict and non-negotiable:

1. All infrastructure lives inside the staging container.
2. Container-local tmpfs only.
3. Host-mounted persistent evidence/log paths are allowed and required.
4. No host-based tmpfs mounts.
5. No host-backed runtime tmp/cache device bindings for `/tmp`, `/var/tmp`, or `/var/cache/nightfall-photo-ingress`.
6. No host-level systemd involvement.
7. No host-level Caddy involvement.
8. Uvicorn remains localhost-bound behind in-container Caddy.
9. Staging ingress is HTTPS-only with TLS termination in in-container Caddy.
10. Staging TLS key material remains container-local under `/etc/caddy/tls`.
11. Future scope may include a dedicated read-only host mount for media library hash-import validation.

## 3. Reconciled Invariants

1. Ingress boundary is in-container Caddy only.
2. API process binds to localhost only.
3. Operational writable surfaces remain container-local, except required host-mounted persistent evidence/log storage.
4. Temporary writable surfaces are container-local tmpfs only.
5. Staging lifecycle commands must not create or bind host-based tmpfs devices for runtime tmp/cache paths.
6. Staging lifecycle commands must preserve host-mounted persistent evidence/log bindings.
7. Staging policy contracts must validate the split model: container-local runtime tmpfs plus host-persistent evidence/log mounts.
8. TLS termination must stay in-container and HTTPS-only behavior must be validated in staging smoke.
9. A future media-library mount, if introduced, must be host-backed and read-only.

## 4. Outdated Staging Contracts and Tests

The following contracts are outdated for Phase 2 and contradict the baseline:

1. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L70)
   - Asserts host tmpfs evidence path defaults.
2. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L71)
   - Asserts host tmpfs log path defaults.
3. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L85)
   - Tmpfs boundary test class validates host-backed LXD disk devices.
4. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L87)
   - Asserts host-backed tmpfs device add for `/tmp`.
5. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L88)
   - Asserts host-backed tmpfs device add for `/var/tmp`.
6. [tests/staging/test_stagingctl_policy_contracts.py](tests/staging/test_stagingctl_policy_contracts.py#L89)
   - Asserts host-backed tmpfs device add for cache path.

## 5. stagingctl Behaviors That Contradict Phase-2 Invariants

The following behaviors are inconsistent with the corrected baseline:

1. [dev/bin/stagingctl](dev/bin/stagingctl#L72)
   - Resolver for host tmpfs base path.
2. [dev/bin/stagingctl](dev/bin/stagingctl#L204)
   - Host tmpfs backing directory creation.
3. [dev/bin/stagingctl](dev/bin/stagingctl#L210)
   - LXD host-device add for `/tmp`.
4. [dev/bin/stagingctl](dev/bin/stagingctl#L211)
   - LXD host-device add for `/var/tmp`.
5. [dev/bin/stagingctl](dev/bin/stagingctl#L212)
   - LXD host-device add for cache path.
6. [dev/bin/stagingctl](dev/bin/stagingctl#L349)
   - Legacy host-backed device-removal logic in install.

## 6. Corrected stagingctl Behavior Contract (Implemented in C1.1)

1. `create` provisions container-local runtime directories and container-local tmpfs semantics.
2. `create` keeps host-mounted persistent evidence/log paths as required infrastructure.
3. `install` must not add/remove host-backed tmpfs devices for `/tmp`, `/var/tmp`, or `/var/cache/nightfall-photo-ingress`.
4. `install` enables in-container API + Caddy services only.
5. Evidence and logs are collected via host-mounted persistent paths.
6. `uninstall --purge` must preserve the persistent evidence/log mount contract unless an explicit retention policy says otherwise.
7. Future media-library host mount support is reserved for read-only hash import tests.

## 7. Remaining Follow-up Work

1. Add an explicit contract test that fails if host-backed runtime tmp/cache devices are reintroduced.
2. Add a forward-compatible contract placeholder for future read-only media library host mount validation.
3. Add a dedicated operational runbook subsection for evidence/log retention and purge policy.
