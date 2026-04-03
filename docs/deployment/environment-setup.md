# Environment Setup and Deployment

**Status:** active  
**Source:** extracted from `docs/operations-runbook.md` §Runtime layout, §Packaged units, §Install and uninstall  
**See also:** [docs/operator/cli-guide.md](../operator/cli-guide.md), [design/architecture/storage-topology.md](../../design/architecture/storage-topology.md)

---

## Runtime Layout

| Path | Purpose |
|---|---|
| `/run/nightfall-status.d/photo-ingress.json` | Status snapshot (written atomically after each command) |
| `/etc/nightfall/photo-ingress.conf` | Service configuration |
| `/var/lib/ingress/` | Working state inside the LXC container (staging, tokens, cursors, registry) |
| journald | Structured log output from systemd units and file outputs if configured |

> **Note on paths:** The `conf/photo-ingress.conf.example` uses `/mnt/ssd/photo-ingress/` as a host-relative path example. Inside the deployed LXC container, the working state directory is `/var/lib/ingress/`. Use the container path in production config.

---

## Status File Contract

The status file is written atomically by CLI commands and systemd-triggered runs.

Top-level fields: `schema_version`, `service`, `version`, `host`, `state`, `success`, `command`, `updated_at`, `details`.

Quick inspection:
```bash
sudo cat /run/nightfall-status.d/photo-ingress.json
jq . /run/nightfall-status.d/photo-ingress.json
```

For full state value definitions and operator actions, see [docs/operator/operational-playbook.md](../operator/operational-playbook.md).

---

## Packaged systemd Units

| Unit | Purpose |
|---|---|
| `nightfall-photo-ingress.service` | Runs a single poll |
| `nightfall-photo-ingress.timer` | Schedules periodic polls |
| `nightfall-photo-ingress-trash.path` | Watches the trash queue directory |
| `nightfall-photo-ingress-trash.service` | Drains queued rejection requests |

Units are installed under `/etc/systemd/system` inside the LXC container.

---

## Install and Uninstall

Production deployment targets an LXC container on the host. The installer creates or updates a container named `photo-ingress` (default) using the `ubuntu:24.04` image and the LXD `default` profile.

### Install Options

| Option | Usage |
|---|---|
| `--container <name>` | Override the target LXC container name |
| `--image <image>` | Override the LXC image (container creation only) |
| `--profile <name>` | Override the LXC profile (container creation only) |

`TARGET_CONTAINER=<name>` is an alternative to `--container`.

Inside the container, the service is installed into `/opt/nightfall-photo-ingress`, and operator documentation is installed under `/opt/nightfall-photo-ingress/share/doc/nightfall-photo-ingress`.

### Standard Install

```bash
sudo ./install/install.sh
```

### Override Container Name

```bash
sudo ./install/install.sh --container my-photo-ingress
```

### Override Image

```bash
sudo ./install/install.sh --image ubuntu:24.04
```

### Override All Three Options

```bash
sudo ./install/install.sh \
  --container my-photo-ingress \
  --image ubuntu:24.04 \
  --profile default
```

### Uninstall

Remove the default container:
```bash
sudo ./install/uninstall.sh
```

Remove a non-default container:
```bash
sudo ./install/uninstall.sh --container my-photo-ingress
```

---

## ZFS Dataset Prerequisites

Before running the installer, create the required ZFS datasets on the host:

```bash
zfs create -o mountpoint=/mnt/ssd/photo-ingress ssdpool/photo-ingress
zfs create -o mountpoint=/nightfall/media/photo-ingress nightfall/media/photo-ingress
```

For full storage topology details, see [design/architecture/storage-topology.md](../../design/architecture/storage-topology.md).

---

*For CLI setup (Entra app registration, auth-setup), see [docs/operator/cli-guide.md](../operator/cli-guide.md).*  
*For staging environment validation, see [docs/operator/maintenance.md](../operator/maintenance.md).*
