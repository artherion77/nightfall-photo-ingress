# Self-Hosted GitHub Actions Runner – LXC Security Design

Date: 2026-04-10
Status: Draft

---

## 1. Goals and Constraints

Goals:
- Run mAOF implementation and analysis workflows triggered by GitHub issue labels.
- Give the runner access to dev-photo-ingress and staging-photo-ingress containers.
- Keep complexity low: one host, one broker, one allowlist.

Constraints:
- Runner must not have general access to the LXD socket.
- Broker must permit only govctl target invocations.
- Shell-level lxc exec must never be reachable from the runner directly.
- No additional infrastructure (no Vault, no Kubernetes, no cloud IAM).

---

## 2. Architecture Overview

```
GitHub Actions
     │  HTTPS (label event)
     ▼
runner-photo-ingress (LXC, unprivileged)
     │  SSH forced-command (restricted key)
     ▼
host nightfall (root)
     │  exec
     ▼
govctl-broker  (allowlist enforcement)
     │  exec
     ▼
./dev/bin/govctl run <TARGET> --json
     │  lxc exec / lxc snapshot / lxc restore
     ▼
dev-photo-ingress / staging-photo-ingress
```

Key design choices:
- SSH forced-command is the only trust boundary crossing.
  No socket passthrough, no HTTP daemon, no sudo rules.
- Broker is a single short shell script with an explicit allowlist.
  It validates the requested target against the list and refuses everything else.
- govctl remains the sole automation surface;
  raw lxc commands stay entirely on the host side of the boundary.

---

## 3. Runner Container Setup

### 3.1 LXC Profiles

Launch the runner container with two profiles applied in order:

```bash
lxc launch ubuntu:24.04 runner-photo-ingress -p staging -p runner
```

**`staging` profile** (existing, reused): provides the network isolation baseline —
the same network constraints already applied to staging-photo-ingress.
This is the primary network boundary; apply it first.

**`runner` profile** (new, additive): adds runner-specific resource caps on top:

```yaml
config:
  security.privileged: "false"
  security.nesting: "false"
  security.idmap.isolated: "true"
  limits.cpu: "2"
  limits.memory: "3GB"
```

No device passthrough. No raw idmap. No LXD socket bind-mount.

### 3.2 Network

The `staging` profile's network isolation is the enforced boundary.
Within that, the runner needs outbound HTTPS only:
- github.com (Actions, gh CLI, Copilot)
- npmjs.com (Copilot CLI install)
- Host SSH broker port (a non-standard port, e.g. 2222) on the host's management IP

All other outbound traffic is blocked by the `staging` profile's bridge rules.

### 3.3 Runner User

Inside the container, run the GitHub Actions runner as a dedicated non-root user, e.g. `runner`.
That user holds the SSH broker key. Nothing else.

---

## 4. SSH Forced-Command Broker

### 4.1 Mechanism

On the host, add one SSH authorized_keys entry for the runner's public key:

```
restrict,command="/usr/local/bin/govctl-broker \"$SSH_ORIGINAL_COMMAND\"" ssh-ed25519 AAAA... runner@runner-photo-ingress
```

`restrict` disables port forwarding, agent forwarding, X11 forwarding, and TTY allocation.
`command=` overrides every SSH invocation with the broker.
The runner sends the desired govctl target as the SSH command argument.

Usage from inside the runner container:

```bash
ssh broker@nightfall-host -p 2222 backend.test.unit
```

### 4.2 Broker Script

```bash
#!/usr/bin/env bash
# /usr/local/bin/govctl-broker
# Accept exactly one argument: an allowed govctl target name.
set -euo pipefail

ALLOWED=(
  devcontainer.prepare
  devcontainer.check
  devcontainer.reset
  dev.check
  backend.build.wheel
  backend.test.unit
  backend.test.integration
  web.build
  web.typecheck
  web.typecheck.dashboard
  web.test.unit
  web.test.e2e
  web.test.integration
  staging.install
  staging.smoke
  staging.e2e.module1
  test.backend
  test.web
  test.all
  staging.full
  runner.reset
)

TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  echo "broker: no target specified" >&2
  exit 1
fi

for t in "${ALLOWED[@]}"; do
  if [[ "$t" == "$TARGET" ]]; then
    exec /home/chris/dev/nightfall-photo-ingress/dev/bin/govctl run "$TARGET" --json
  fi
done

echo "broker: target '$TARGET' is not permitted" >&2
exit 1
```

Install:

```bash
install -o root -g root -m 755 govctl-broker /usr/local/bin/govctl-broker
```

Audit: the SSH daemon logs every invocation with the invoking key fingerprint.
Add a log line to the broker itself for a local audit trail in `/var/log/govctl-broker.log`.

---

## 5. Broker Policy

| Target | Permitted | Notes |
|---|---|---|
| devcontainer.prepare | yes | Container bootstrap and snapshot |
| devcontainer.check | yes | Read-only drift check |
| devcontainer.reset | yes | Restore to cached-ready snapshot |
| dev.check | yes | Read-only |
| backend.build.wheel | yes | Builds dist/*.whl on host |
| backend.test.unit | yes | Pure Python, no container needed |
| backend.test.integration | yes | Pure Python, no container needed |
| web.build | yes | SvelteKit build in dev container |
| web.typecheck | yes | Svelte-check in dev container |
| web.typecheck.dashboard | yes | Svelte-check in dev container |
| web.test.unit | yes | Vitest in dev container |
| web.test.e2e | yes | Playwright against staging |
| web.test.integration | yes | Integration suite against staging |
| staging.install | yes | Build + deploy to staging |
| staging.smoke | yes | Headless smoke assertions |
| staging.e2e.module1 | yes | E2E Suite Module 1 |
| test.backend | yes | Group: unit + integration |
| test.web | yes | Group: typecheck + unit |
| test.all | yes | Group: all test targets |
| staging.full | yes | Group: install + smoke + e2e |
| runner.reset | yes | Post-job container restore to runner-clean snapshot |
| staging.smoke-live | **no** | Requires live auth / TTY |
| devcontainer.update | **no** | Maintenance only |
| backend.deploy.dev | **no** | Interactive dev server |
| web.deploy.dev | **no** | Interactive dev server |
| metrics.* | **no** | Not relevant to CI ticket work |
| dev.ensure-running | **no** | Internal govctl dependency only |
| dev.stack-ready.* | **no** | Internal govctl dependency only |

Deny-by-default: anything not in the ALLOWED array is rejected with exit 1.

---

## 6. Ephemeral Runner Reset

The runner container is reset to a known-clean state **after each mAOF job completes**, using the
GitHub Actions post-job hook mechanism. This prevents state bleed between Copilot sessions
(credentials, cached tokens, workspace dirt, git state).

**Chosen mechanism: Option A — post-job hook (`ACTIONS_RUNNER_HOOK_JOB_COMPLETED`)**

GitHub Actions runner supports an environment variable `ACTIONS_RUNNER_HOOK_JOB_COMPLETED`
pointing to a script that is executed after the job finishes but before the runner polls for the
next job. The hook runs *inside the container*, calls `ssh broker@host runner.reset`, waits for
the host to restore the container, and then exits. The restore kills the hook process — this is
expected and harmless because GitHub has already received the job result. The next job starts
from a clean snapshot.

Configure this in the runner's `.env` file (stored in the clean snapshot):

```bash
# ~runner/actions-runner/.env  (baked into runner-clean snapshot)
ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/home/runner/bin/post-job-reset.sh
```

```bash
#!/usr/bin/env bash
# /home/runner/bin/post-job-reset.sh
# Called by the Actions runner after every job.
# Triggers a host-side container restore; this process will be killed by the restore.
set -euo pipefail
ssh -q \
  -o StrictHostKeyChecking=yes \
  -i ~/.ssh/govctl_broker \
  -p 2222 \
  broker@nightfall \
  runner.reset
# If SSH returns (it should not), exit cleanly.
exit 0
```

The broker target `runner.reset` maps to a host-side script:

### 6.1 Snapshot Naming Convention

| Snapshot | Contents |
|---|---|
| runner-clean | LXC container with OS, GitHub Actions runner binary, gh CLI, Node, project checkout, installed Python dev deps. Runner service is stopped. |

Create the clean snapshot after bootstrapping the runner container once:

```bash
# on host nightfall
lxc stop runner-photo-ingress
lxc snapshot runner-photo-ingress runner-clean
lxc start runner-photo-ingress
```

Refresh the snapshot whenever the runner binary, gh CLI, or major dependencies change.

### 6.2 Host-Side Reset Script

```bash
# /usr/local/bin/runner-reset  (root-owned, called by govctl-broker for runner.reset)
set -euo pipefail
lxc stop runner-photo-ingress --force 2>/dev/null || true
lxc restore runner-photo-ingress runner-clean
lxc start runner-photo-ingress
# Wait for systemd inside the restored container to be ready.
until lxc exec runner-photo-ingress -- systemctl is-system-running --quiet 2>/dev/null; do
  sleep 1
done
```

The broker maps `runner.reset` to this script:

```bash
# In govctl-broker ALLOWED array: runner.reset
# Corresponding exec line in the broker:
exec /usr/local/bin/runner-reset
```

Note: the SSH connection that triggered `runner-reset` is severed when the container is restored.
This is expected. The broker does not need to return a success code to the caller.

### 6.3 Snapshot Maintenance

- Refresh `runner-clean` after: runner binary updates, major dep upgrades, gh CLI updates.
- Do not refresh automatically in CI; treat it as a controlled infra change.
- Keep one previous snapshot (`runner-prev`) before overwriting for rollback.

```bash
lxc snapshot rename runner-photo-ingress runner-clean runner-prev 2>/dev/null || true
lxc delete runner-photo-ingress/runner-clean 2>/dev/null || true
lxc stop runner-photo-ingress
lxc snapshot runner-photo-ingress runner-clean
lxc start runner-photo-ingress
```

---

## 7. Secret Handling

- `GITHUB_TOKEN` is injected by GitHub Actions at runtime and scoped to the workflow job.
- No long-lived secrets are stored inside the runner container.
- The broker SSH key lives only inside the runner container under the `runner` user's `~/.ssh/`.
  It is recreated from the clean snapshot on every reset.
- The host's authorized_keys entry for the broker key uses `restrict` to prevent key reuse
  for anything other than the forced-command.

---

## 8. What Is Not Implemented (Intentionally)

- No Vault, no HSM, no OIDC token broker. The risk profile of this host does not justify it.
- No per-job container image rebuild. Snapshot restore is fast and sufficient.
- No network policy enforcement inside the runner container beyond the host bridge ACL.
- No runtime syscall filtering (seccomp) beyond LXC defaults. Add if risk profile changes.

---

## 9. govctl Container Shim

### 9.1 Problem

Copilot agent sessions and workflow scripts inside the runner container will naturally invoke
`./dev/bin/govctl run <target> --json`. Direct govctl execution inside the container would fail
because the container has no LXD socket, no lxc binary, and no access to sibling containers.
The agent cannot be expected to know it must SSH instead.

### 9.2 Chosen Approach: Environment-Variable-Driven Shim

The govctl binary detects a container environment via an environment variable injected by the
runner LXC profile, and transparently proxies the call over SSH to the host broker.

No changes to agent prompts, workflow YAML, or govctl's target logic are required.
The shim is a five-line guard at the very top of `./dev/bin/govctl`.

### 9.3 Environment Variable

Set `GOVCTL_BROKER_HOST` and `GOVCTL_BROKER_PORT` in the runner container's LXC profile config:

```yaml
# runner LXC profile
config:
  environment.GOVCTL_BROKER_HOST: "nightfall"
  environment.GOVCTL_BROKER_PORT: "2222"
  environment.GOVCTL_BROKER_KEY: "/home/runner/.ssh/govctl_broker"
```

These are set once in the profile and baked into the clean snapshot.
They are visible to every process inside the container, including the Copilot session.

### 9.4 Shim Implementation

At the very top of `./dev/bin/govctl`, before the existing argument parsing:

```bash
# --- Container broker shim ---
# When running inside the runner container, proxy all govctl calls through the SSH broker.
if [[ -n "${GOVCTL_BROKER_HOST:-}" ]]; then
  exec ssh -q \
    -o StrictHostKeyChecking=yes \
    -i "${GOVCTL_BROKER_KEY:-$HOME/.ssh/govctl_broker}" \
    -p "${GOVCTL_BROKER_PORT:-2222}" \
    "broker@${GOVCTL_BROKER_HOST}" \
    "$@"
fi
# --- End shim ---
```

Behaviour:
- On the host: `GOVCTL_BROKER_HOST` is unset → shim is skipped → govctl runs normally.
- Inside the runner container: variable is set → govctl replaces itself with the SSH call.
- The broker receives the full `"$@"` argument list (e.g. `run backend.test.unit --json`).

The broker must therefore accept the full govctl argument form, not just a bare target name.
Update the broker to parse `run <TARGET> [--json]` and validate only `<TARGET>`:

```bash
# In govctl-broker, replace argument parsing:
RAW="${1:-}"
# Accept both bare target ("backend.test.unit") and govctl form ("run backend.test.unit --json")
if [[ "$RAW" == "run" ]]; then
  TARGET="${2:-}"
else
  TARGET="$RAW"
fi
```

### 9.5 StrictHostKeyChecking

Pin the host key in the runner snapshot's `~runner/.ssh/known_hosts` at bootstrap time:

```bash
ssh-keyscan -p 2222 nightfall >> ~runner/.ssh/known_hosts
```

`StrictHostKeyChecking=yes` then prevents MITM substitution even if the container's
network path is compromised.

### 9.6 Transparency to Agents

From a Copilot session perspective:
- `./dev/bin/govctl run backend.test.unit --json` works identically inside or outside the container.
- JSONL output is streamed back through the SSH channel to stdout.
- Non-zero exit codes from the host propagate through SSH exit status.
- No special instructions need to be added to agent prompts.
