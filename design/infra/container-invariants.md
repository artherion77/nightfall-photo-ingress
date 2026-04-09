# Container Infrastructure Invariants

**Status:** proposed  
**Date:** 2025-07-27  
**Owner:** Systems Engineering  
**See also:** [build-governor-design.md](build-governor-design.md), [devctl-design.md](devctl-design.md), [AGENTS.md](../../AGENTS.md)

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Scope](#2-scope)
3. [Container Construction Inventory](#3-container-construction-inventory)
4. [Infrastructure Invariants](#4-infrastructure-invariants)
5. [Regression Coverage Assessment](#5-regression-coverage-assessment)
6. [Definitions](#6-definitions)

---

## 1. Purpose

This document formalizes the container infrastructure invariants for the
nightfall-photo-ingress project. These invariants were previously implicit
in the shell scripts (`devctl`, `stagingctl`) and systemd overrides. A
staging failure caused by ephemeral host-path dependencies (status=226/
NAMESPACE) demonstrated that implicit invariants create fragile
infrastructure. This document makes those invariants explicit, auditable,
and testable.

---

## 2. Scope

Covers the two LXC container environments:

| Container | Controller | Base Image | Profiles |
|---|---|---|---|
| `dev-photo-ingress` | `devctl` | ubuntu:24.04 | default, staging |
| `staging-photo-ingress` | `stagingctl` | ubuntu:24.04 | default, staging |

This document does not cover production deployment, CI/CD pipelines,
or the govctl orchestrator itself (see build-governor-design.md).

---

## 3. Container Construction Inventory

### 3.1 Dev Container (`dev-photo-ingress`)

**Lifecycle:** `devctl setup` creates the container and bootstraps all
toolchains. `devctl reset` restores to a known snapshot. `devctl update`
applies incremental changes and gates on the regression suite.

#### LXC Bind-Mount Cache Devices

| Device Name | Host Path | Container Path | Purpose |
|---|---|---|---|
| `cache-root-npm-home` | `~/.npm` | `/root/.npm` | npm package cache |
| `cache-root-cache-npm` | `~/.cache/npm` | `/root/.cache/npm` | npm secondary cache |
| `cache-root-cache-pip` | `~/.cache/pip` | `/root/.cache/pip` | pip package cache |

All cache devices are idempotently removed and re-added on each setup.
Host directories are created with `mkdir -p` and `chmod 0777`.

#### Directories Created Inside Container

| Path | Purpose |
|---|---|
| `/opt/nightfall-webui` | webui source tree |
| `/opt/nightfall-metrics-dashboard` | dashboard source tree |
| `/opt/ingress` | Python venv root |
| `/opt/nightfall-manifest` | Hash manifest files (`webui.hash`, `dashboard.hash`) |

#### Bootstrap Sequence

1. Cache mounts configured (`_ensure_cache_mounts`)
2. Node.js installed via nvm (`_install_node_exact`); symlinks to `/usr/local/bin/`
3. Python toolchain bootstrapped (`_bootstrap_python_toolchain`); venv at `/opt/ingress`; marker: `/opt/ingress/.bootstrap-python.done`
4. webui stack installed (`_install_stack webui`): tar-sync, `npm ci`, write hash
5. dashboard stack installed (`_install_stack dashboard`): same pattern

#### Snapshots

| Snapshot | When Created | Restore Behavior |
|---|---|---|
| `base` | End of `devctl setup` | Deleted and recreated each setup |
| `current` | `devctl update` after regression gate passes | `devctl reset` restores `current` if present, else `base`. `--base` forces `base`. |

---

### 3.2 Staging Container (`staging-photo-ingress`)

**Lifecycle:** `stagingctl create` launches the container and pushes all
systemd units. `stagingctl install` deploys a wheel, all overrides, and
takes a clean snapshot. `stagingctl destroy` removes the container.

#### LXC Bind-Mount Devices

Staging has two operating modes controlled by `STAGING_VOLATILE`:

**Persistent mode (default):**

| Device Name | Host Path | Container Path |
|---|---|---|
| `evidence` | `/mnt/ssd/staging/photo-ingress/evidence` | `/var/lib/ingress/evidence` |
| `logs` | `/mnt/ssd/staging/photo-ingress/logs` | `/var/log/nightfall` |

**Volatile mode (`STAGING_VOLATILE=1`):**

| Device Name | Host Path | Container Path |
|---|---|---|
| `evidence` | `/run/staging-photo-ingress/evidence` | `/var/lib/ingress/evidence` |
| `logs` | `/run/staging-photo-ingress/logs` | `/var/log/nightfall` |

#### Directories Created by `setup.sh` (Inside Container)

| Path | Purpose |
|---|---|
| `/etc/nightfall` | Configuration directory |
| `/var/lib/ingress/{staging,pending,accepted,rejected,trash,evidence,tokens,cursors}` | Application data directories |
| `/var/log/nightfall` | Log directory |
| `/var/cache/nightfall-photo-ingress` | Application cache |
| `/run/nightfall-status.d` | Runtime status export directory |

#### Directories Created by `stagingctl` Commands

`cmd_create` and `cmd_install` both ensure:
- `/run/nightfall-status.d` exists
- `/var/cache/nightfall-photo-ingress` exists
- `/tmp` and `/var/tmp` have mode `1777`

#### Systemd Units Pushed During Create

- `nightfall-photo-ingress.service`
- `nightfall-photo-ingress.timer`
- `nightfall-photo-ingress-trash.path`
- `nightfall-photo-ingress-trash.service`

#### Override Drop-Ins Pushed During Create and Install

| Unit | Override Source |
|---|---|
| `nightfall-photo-ingress.service` | `staging/systemd/nightfall-photo-ingress.service.d/override.conf` |
| `nightfall-photo-ingress.timer` | `staging/systemd/nightfall-photo-ingress.timer.d/override.conf` |
| `nightfall-photo-ingress-trash.service` | `staging/systemd/nightfall-photo-ingress-trash.service.d/override.conf` |
| `nightfall-photo-ingress-trash.path` | `staging/systemd/nightfall-photo-ingress-trash.path.d/override.conf` |

Both `cmd_create` and `cmd_install` push all overrides and run `systemctl daemon-reload`.

#### Trash Service Sandbox (Override Directives)

| Directive | Value | Invariant Purpose |
|---|---|---|
| `TemporaryFileSystem=/tmp:rw,mode=1777` | Ephemeral `/tmp` scoped to service | Eliminates host-path dependency for `/tmp` |
| `TemporaryFileSystem=/var/cache/nightfall-photo-ingress:rw,mode=0777` | Ephemeral cache scoped to service | Eliminates host-path dependency for cache |
| `RuntimeDirectory=nightfall-status.d` | systemd-managed `/run/nightfall-status.d` | Auto-created on service start, cleaned on stop |
| `RuntimeDirectoryMode=0755` | Permissions for runtime dir | Deterministic access control |
| `PrivateTmp=yes` | Private namespace for `/tmp` | Isolation from other services |
| `ProtectSystem=full` | Read-only system directories | Defense in depth |
| `NoNewPrivileges=yes` | Block privilege escalation | Defense in depth |
| `MemoryMax=256M` | Memory ceiling | Resource containment |
| `ReadWritePaths=/var/lib/ingress /var/log/nightfall /run/nightfall-status.d` | Explicit writable mounts | Principle of least privilege |

#### Legacy Device Cleanup

`cmd_install` removes stale bind-mount devices from older container configurations:
- `tmpfs-tmp`
- `tmpfs-var-tmp`
- `tmpfs-nightfall-cache`

These devices were replaced by `TemporaryFileSystem` and `RuntimeDirectory` directives.

#### Snapshots

| Snapshot | When Created |
|---|---|
| `clean` | End of `cmd_create` and end of `cmd_install` |

The `clean` snapshot is deleted and recreated on each `cmd_install`.

---

## 4. Infrastructure Invariants

### 4.1 Ephemeral Storage Invariants

**INV-ES-1: No host-ephemeral path dependencies.**  
Container services must not depend on host paths under `/run/user/`, `/tmp`,
or any path whose existence is tied to a host login session, systemd user
slice, or host reboot cycle. Violation of this invariant produces
status=226/NAMESPACE failures when the host path disappears.

**INV-ES-2: Ephemeral mounts via systemd directives, not LXC devices.**  
Temporary filesystem space required by services must be provided through
`TemporaryFileSystem=` or `RuntimeDirectory=` in systemd unit overrides.
LXC bind-mount devices must not be used for ephemeral/tmp paths. This
ensures storage allocation is scoped to the service lifecycle, not the
container lifecycle.

**INV-ES-3: Runtime directories managed by systemd.**  
Directories under `/run/` that services require at startup must be declared
via `RuntimeDirectory=` so that systemd creates them before `ExecStart` and
cleans them on service stop. Manual `mkdir` in shell scripts is permitted
only as a defense-in-depth fallback during container create/install; the
systemd directive is the primary mechanism.

**INV-ES-4: `/tmp` sticky bit preserved by scope.**  
Container-global `/tmp` and `/var/tmp` must have mode `1777`.
Any service-private tmpfs mounted at `/tmp` via `TemporaryFileSystem=`
must also declare `mode=1777`.

### 4.2 Persistent Storage Invariants

**INV-PS-1: Data durability is mode-defined and device-backed.**  
Evidence and log paths are always provided through named LXC bind-mount
devices (`evidence`, `logs`) with explicit host-side sources.
In persistent mode, these sources must be durable host storage.
In volatile mode, these sources are explicitly non-durable.

**INV-PS-2: Host persistent paths are on stable storage.**  
Persistent-mode host paths must be on stable storage (`/mnt/ssd/...`).
Volatile-mode uses `/run/` paths intentionally and accepts data loss on
host reboot.

**INV-PS-3: Application data directories created by `setup.sh`.**  
The full `/var/lib/ingress/` subtree (`staging`, `pending`, `accepted`,
`rejected`, `trash`, `evidence`, `tokens`, `cursors`) is created by
`setup.sh` during container creation. Services assume these directories
exist.

### 4.3 Host/Container Boundary Invariants

**INV-HCB-1: Cache bind-mounts are dev-only.**  
LXC bind-mount devices for package caches (`npm`, `pip`)
are attached only to the dev container. The staging container has no
cache bind-mounts.

**INV-HCB-2: Network policy for staging.**  
The staging container must be on bridged network (`br-staging`).
`stagingctl create` validates this via network policy check.

**INV-HCB-3: Override push completeness.**  
Both `cmd_create` and `cmd_install` must push all override drop-ins for
all units. Partial override push (e.g., pushing API override but not
trash override) leaves services running without their sandbox directives.
This was the root cause of the status=226/NAMESPACE failure.

**INV-HCB-4: `daemon-reload` after override changes.**  
Every operation that pushes or modifies systemd unit files or override
drop-ins must call `systemctl daemon-reload` before starting or
restarting services.

### 4.4 Lifecycle and Reboot Safety Invariants

**INV-LS-1: Snapshot as recovery baseline.**  
Every controller must maintain a named snapshot (`clean` for staging,
`base`/`current` for dev) that represents a known-good post-install
state. Reset operations restore to this snapshot.

**INV-LS-2: Services survive container restart.**  
All runtime directories and ephemeral mounts required by services are
recreated by systemd directives on service start. No manual
initialization steps are needed after a container reboot.

**INV-LS-3: Legacy device cleanup on install.**  
Each `cmd_install` must remove deprecated LXC bind-mount devices.
New installations must not introduce devices that contradict
INV-ES-2 (ephemeral mounts via systemd, not LXC).

**INV-LS-4: Idempotent setup and install.**  
`devctl setup` and `stagingctl create`/`install` are idempotent.
Running them multiple times produces the same container state. Cache
mounts, directories, units, and overrides are all written
unconditionally.

---

## 5. Regression Coverage Assessment

### 5.1 Coverage by `staging.smoke`

The smoke test (`stagingctl smoke`) executes five steps:

| Step | What It Tests | Invariants Covered |
|---|---|---|
| 1. CLI help | `nightfall-photo-ingress -h` exits 0 | INV-PS-3 (implicitly: venv and binary exist) |
| 2. Config check + status export | config-check writes `/run/nightfall-status.d/photo-ingress.json` | INV-ES-3 (runtime dir exists and is writable) |
| 3. Trash processor start | `systemctl start nightfall-photo-ingress-trash.service` | INV-ES-1, INV-ES-2, INV-ES-3 (service starts without NAMESPACE failure) |
| 4. Live poll (conditional) | poll with STAGING_CLIENT_ID | — (authentication, not infrastructure) |
| 5. Secret scan | scan evidence directory for credential leaks | — (security policy, not infrastructure) |

**Assessment:** Step 3 is the primary invariant validator. If any ephemeral
storage invariant (INV-ES-1 through INV-ES-3) is violated, the trash
service fails to start. Step 2 validates that the runtime status directory
functions correctly.

### 5.2 Coverage by `staging.e2e.module1`

The E2E suite (15 test cases across 4 test files) covers:

| Test File | Cases | Invariants Covered |
|---|---|---|
| `test_auth_handshake.py` | 1-5 | — (authentication logic, not infrastructure) |
| `test_token_consistency.py` | 6-8 | — (token/config consistency, not infrastructure) |
| `test_artifact_integrity.py` | 9-11 | — (artifact provenance/integrity, not lifecycle/idempotency invariants) |
| `test_staging_health.py` | 12-15 | INV-HCB-3 (Case 12: API service active indicates override push completeness) |

**Assessment:** Case 12 (`test_case_12_api_systemd_service_is_active`)
validates that the API service is running, which implicitly validates
override push completeness (INV-HCB-3) for the API service.

### 5.3 Coverage Gaps

| Invariant | Covered | Gap Description |
|---|---|---|
| INV-ES-1 | Partial | Tested via trash service start (smoke step 3). Not tested by asserting absence of host-ephemeral devices. |
| INV-ES-2 | Partial | Tested via trash service start. No assertion that LXC device list lacks tmpfs-* entries. |
| INV-ES-3 | Yes | Smoke step 2 and step 3 both exercise runtime directories. |
| INV-ES-4 | No | No test asserts `/tmp` sticky bit. |
| INV-PS-1 | No | No test validates that `evidence` and `logs` devices are attached. |
| INV-PS-2 | No | No test validates host path stability. |
| INV-PS-3 | Partial | setup.sh creates directories; no test enumerates the full subtree. |
| INV-HCB-1 | No | No test asserts cache-mount absence on staging. |
| INV-HCB-2 | Partial | Enforced in stagingctl create; not re-validated in smoke. |
| INV-HCB-3 | Partial | Indirectly tested by services starting. No assertion that all 4 override files exist in the container. |
| INV-HCB-4 | No | Assumed by smoke. Not independently validated. |
| INV-LS-1 | No | No test validates that the `clean` snapshot exists after install. |
| INV-LS-2 | No | No test restarts the container and re-checks services. |
| INV-LS-3 | No | No test asserts legacy devices are absent. |
| INV-LS-4 | No | No test runs setup/install twice and compares state. |

**Summary:** The existing smoke and E2E suites cover the most critical
ephemeral-storage invariants (INV-ES-1 through INV-ES-3) via the trash
service start gate. Persistent storage, host/container boundary, and
lifecycle invariants have minimal or no automated coverage.

### Minimum Enforcement Set
- Preflight: required staging override drop-ins are present for all staged units.
- Preflight: staging evidence/log bind-mount devices are attached and mode-consistent (persistent vs volatile).
- Preflight: legacy tmpfs-* LXC devices are absent.
- Smoke: trash service start succeeds without namespace/mount failure.
- Smoke: config-check writes a valid runtime status snapshot under `/run/nightfall-status.d`.
- E2E: API service is active after install/restart cycle entrypoint.

---

## 6. Definitions

| Term | Definition |
|---|---|
| Host-ephemeral path | A filesystem path on the LXC host whose existence depends on a login session, user slice, or tmpfs that is cleared on reboot (e.g., `/run/user/1000/`). |
| LXC bind-mount device | A named LXC device of type `disk` that maps a host path into the container. |
| Override drop-in | A systemd configuration fragment placed under `/etc/systemd/system/<unit>.d/override.conf` that extends or overrides directives in the base unit file. |
| `TemporaryFileSystem` | A systemd directive that mounts a private tmpfs at a given path within the service's mount namespace. |
| `RuntimeDirectory` | A systemd directive that creates a directory under `/run/` before `ExecStart` and optionally removes it on service stop. |
| Snapshot | A point-in-time LXC container image used for fast restore to a known state. |
| Volatile mode | Staging operating mode where evidence and logs use `/run/` host paths, accepting data loss on host reboot. |
