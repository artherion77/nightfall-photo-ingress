# Development Handbook

**Status:** active  
**Audience:** developers and operators working on build, test, and release validation flows  
**Primary implementation references:** [AGENTS.md](../AGENTS.md), [dev/govctl-targets.yaml](../dev/govctl-targets.yaml), [design/infra/build-governor-design.md](../design/infra/build-governor-design.md), [design/infra/devctl-update-architecture.md](../design/infra/devctl-update-architecture.md), [design/infra/container-invariants.md](../design/infra/container-invariants.md), [design/infra/metrics-ctl-design.md](../design/infra/metrics-ctl-design.md)

---

## 1. Purpose

This handbook is the consolidated developer-facing guide for the repository's
working environments, build/test tooling, and promotion flow from local
development to staging validation to production deployment.

It replaces the need to piece together the workflow from older deployment
notes, `README.md`, `staging/README.md`, and the implementation-oriented design
docs under `design/infra/`.

The design documents remain authoritative for rationale and invariants. This
handbook is the practical operating guide for the current implementation.

Scope boundary:

- This handbook is the primary source for developer setup, dev/staging build and
  test flow, and release promotion mechanics.
- `docs/operations-runbook.md` is the primary source for runtime layout,
  packaged service behavior, production install/uninstall, and operator-side
  deployment procedures.

---

## 2. Project Model

`nightfall-photo-ingress` is a Python-first photo ingress pipeline with a web
control plane and a staging-first release process.

At a high level:

- The product CLI is `nightfall-photo-ingress`.
- The backend lives in `src/nightfall_photo_ingress/`.
- The web control plane lives in `webui/`.
- Metrics/publishing tooling is driven by `metricsctl` and the metrics modules.
- Development and validation use LXC containers instead of assuming host Node or
  host service state.

The working environments are intentionally separated:

| Environment | Container | Purpose | Canonical entry point |
|---|---|---|---|
| Host workspace | none | source editing, Python venv, direct pytest when needed | `.venv/bin/python ...` |
| Development | `dev-photo-ingress` | rapid iteration, web stack sync, deterministic lockfile regeneration | `govctl run devcontainer.* --json` |
| Staging | `staging-photo-ingress` | release rehearsal, smoke, browser E2E, authenticated live poll | `govctl run staging.* --json` |
| Production | `photo-ingress` by default | stable packaged runtime | `install/install.sh` |

The automation rule is simple:

- Use `govctl run ... --json` as the canonical automation surface.
- Treat `devctl`, `stagingctl`, and `metricsctl` as underlying implementation
  tools behind governor targets.
- Use direct tool entry points only when debugging those tools or when no
  governor target exists yet.

Current limitation:

- `govctl run backend.deploy.dev --json` delegates to `devctl run-api`, which is
  still a scaffold rather than a complete live backend dev-run path.
- For backend runtime debugging today, use `devctl shell` and run the API
  process manually inside the dev container.

---

## 3. Repository Areas That Matter During Development

| Path | Purpose |
|---|---|
| `src/nightfall_photo_ingress/` | product Python package |
| `api/` | web API surface and control-plane server code |
| `webui/` | Svelte web control plane |
| `tests/unit/` | fast isolated Python tests |
| `tests/integration/` | isolated cross-module and API integration tests |
| `tests/e2e/` | staging-backed E2E suite executed through governor targets |
| `tests/staging/` | staging container contract tests |
| `tests/staging-flow/` | staged authentication/live-poll flow harness |
| `dev/bin/` | orchestration CLIs (`devctl`, `govctl`, `stagingctl`) |
| `dev/govctl-targets.yaml` | canonical build/test/deploy target manifest |
| `docs/deployment/` | superseded redirect stubs pointing to the handbook and runbook |
| `docs/operator/` | operator workflows, maintenance, troubleshooting |
| `design/infra/` | implementation constraints and design rationale |

---

## 4. Tooling and Command Surface

### 4.1 Governor-first automation

`govctl` is the build governor. It resolves dependencies, runs preflights,
delegates to existing tools, and emits JSONL output for automation.

Primary commands:

```bash
./dev/bin/govctl list
./dev/bin/govctl check TARGET
./dev/bin/govctl graph TARGET
./dev/bin/govctl run TARGET --json
```

Use `govctl run ... --json` for any scripted or MCP-driven workflow.

### 4.2 Underlying tools

| Tool | Role | Typical direct use |
|---|---|---|
| `devctl` | dev container lifecycle and stack maintenance | tool debugging, local container maintenance |
| `stagingctl` | staging container lifecycle and live rehearsal helpers | interactive auth setup, staging troubleshooting |
| `metricsctl` | metrics pipeline runtime and publication | metrics debugging |
| `nightfall-photo-ingress` | product CLI | runtime commands inside staging/production |

### 4.3 Current important governor targets

| Target | Purpose |
|---|---|
| `devcontainer.prepare` | setup + cached-ready verification + status |
| `devcontainer.check` | read-only drift report |
| `devcontainer.update` | refresh dev container state |
| `devcontainer.reset` | restore cached-ready dev baseline |
| `backend.test.unit` | Python unit suite |
| `backend.test.integration` | Python integration suite |
| `backend.deploy.dev` | backend dev-run wrapper; currently delegates to a scaffold |
| `test.web` | grouped web typecheck and unit suite |
| `web.build` | production web artifact build |
| `staging.create` | explicit staging container baseline creation |
| `staging.ensure-running` | idempotent staging bootstrap (create/start) |
| `staging.install` | build/install candidate into staging |
| `staging.smoke` | headless staging smoke validation |
| `staging.smoke-live` | authenticated live staging rehearsal |
| `web.test.e2e` | staging-backed E2E suite |
| `metrics.status` | metrics runtime status |
| `metrics.publish` | metrics publication path |

---

## 5. Host Setup

### 5.1 Required host capabilities

For normal development on this repo, the host should have:

- Python 3.11+ available
- LXC/LXD available for dev and staging container flows
- `flock` and `timeout` available for `govctl`
- Git access to the repository and remotes

Host Node/npm is not required for the standard development workflow. The web
toolchain is intentionally containerized.

### 5.2 Python environment

Use the repo virtual environment for host-side Python commands:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

The same venv is used by governor targets that need Python on the host, such as
backend test execution and metrics wrapper targets.

### 5.3 Optional package sets

- `.[dev]` provides build and pytest tooling.
- `.[web]` is installed in staging/container runtime contexts, not as a normal
  host development requirement.

---

## 6. Development Container Workflow

The development container exists to provide deterministic Node/web stack
behavior, lockfile regeneration, and rapid rollback without requiring host web
toolchains.

### 6.1 Canonical lifecycle

```bash
./dev/bin/govctl run devcontainer.prepare --json
./dev/bin/govctl run devcontainer.check --json
./dev/bin/govctl run devcontainer.update --json
./dev/bin/govctl run devcontainer.reset --json
```

### 6.2 Snapshot model

The dev container uses the dual-snapshot model described in
`design/infra/devctl-update-architecture.md`:

- `base` is created by `devctl setup`
- `current` is created only after successful `devctl update`
- `devctl reset` restores `current` first and falls back to `base`
- `devctl reset --base` forces the original bootstrap state

### 6.3 Cache mounts and drift model

The dev container bind-mounts package caches to speed rebuilds:

- `~/.npm -> /root/.npm`
- `~/.cache/npm -> /root/.cache/npm`
- `~/.cache/pip -> /root/.cache/pip`

`devctl ensure-stack-ready` and the governor preflights use manifest hashing,
Node version checks, and stack drift detection to decide whether the web stacks
need to be resynchronized or regenerated.

### 6.4 What the dev container is for

Use the dev container for:

- web UI iteration
- dashboard stack maintenance
- deterministic Node/npm lockfile regeneration
- fast rollback during dependency or toolchain changes

Do not treat the dev container as a release gate. Staging is the release gate.

---

## 7. Test Suite Setup and Boundaries

### 7.1 Python test taxonomy

| Suite | Location | Environment | Canonical runner |
|---|---|---|---|
| Unit | `tests/unit/` | host venv | `govctl run backend.test.unit --json` |
| Integration | `tests/integration/` | host venv | `govctl run backend.test.integration --json` |
| E2E | `tests/e2e/` | staging container must exist | `govctl run web.test.e2e --json` |
| Staging contracts | `tests/staging/` | live staging container | direct pytest when doing staging subsystem work |
| Staging flow harness | `tests/staging-flow/` | live staging container + auth state as required | `flowctl` for phase-specific validation |

Pytest defaults in `pyproject.toml` set `tests/unit` and `tests/integration` as
the normal host-side suite.

Markers currently include:

- `robustness`
- `staging`
- `staging_flow`

### 7.2 Web test taxonomy

| Suite | Location | Environment | Canonical runner |
|---|---|---|---|
| Component/unit | `webui/tests/component/` | dev container web stack | `govctl run test.web --json` |
| Web typecheck | webui + dashboard stack | dev container | `govctl run test.web --json` |
| Browser E2E | `tests/e2e/` | staging-backed | `govctl run web.test.e2e --json` |

Important boundary:

- Browser E2E does **not** run in the dev container.
- Browser E2E runs against the staging container and staged artifacts.
- `devctl test-web-e2e` remains a contract-test harness, not the canonical
  operator or automation entry point.

### 7.3 Metrics validation

Metrics has its own operational targets:

- `govctl run metrics.status --json`
- `govctl run metrics.run-now --json`
- `govctl run metrics.publish --json`

These are useful when changing metrics collection, dashboard generation, or
publication flows.

---

## 8. Common Development Flows

### 8.1 Backend-only change

```bash
./dev/bin/govctl run backend.test.unit --json
./dev/bin/govctl run backend.test.integration --json
```

If you changed packaging or release behavior:

```bash
./dev/bin/govctl run backend.build.wheel --json
```

### 8.2 Web control-plane change

```bash
./dev/bin/govctl run devcontainer.prepare --json
./dev/bin/govctl run test.web --json
./dev/bin/govctl run web.build --json
```

If the change affects user-visible browser behavior:

```bash
./dev/bin/govctl run staging.install --json
./dev/bin/govctl run web.test.e2e --json
```

### 8.3 Dependency or Node/toolchain change

```bash
./dev/bin/govctl run devcontainer.check --json
./dev/bin/govctl run devcontainer.update --json
./dev/bin/govctl run test.web --json
```

### 8.4 Metrics/dashboard change

```bash
./dev/bin/govctl run metrics.build.dashboard --json
./dev/bin/govctl run metrics.status --json
```

If the change affects publication or generated assets:

```bash
./dev/bin/govctl run metrics.full --json
```

---

## 9. Build and Promotion Flow

This project uses a staging-first promotion model.

### 9.1 Development phase

Goal: validate source changes before packaging.

Typical progression:

1. Prepare or verify the dev container.
2. Run backend tests and/or web tests depending on the change.
3. Regenerate or verify web artifacts if the UI changed.

Representative commands:

```bash
./dev/bin/govctl run devcontainer.prepare --json
./dev/bin/govctl run backend.test.unit --json
./dev/bin/govctl run backend.test.integration --json
./dev/bin/govctl run test.web --json
```

### 9.2 Build candidate artifacts

Goal: produce the wheel and static web artifact that staging will validate.

```bash
./dev/bin/govctl run backend.build.wheel --json
./dev/bin/govctl run web.build --json
```

`staging.install` depends on `staging.ensure-running` plus both build targets,
so invoking staging install
is usually sufficient when the intent is full candidate validation.

### 9.3 Staging validation

Goal: rehearse the release in the staging container using packaged artifacts.

Canonical flow:

```bash
./dev/bin/govctl run staging.ensure-running --json
./dev/bin/govctl run staging.install --json
./dev/bin/govctl run staging.smoke --json
./dev/bin/govctl run web.test.e2e --json
```

Alternate grouped path:

```bash
./dev/bin/govctl run staging.full --json
```

For authenticated live validation after interactive auth bootstrap:

```bash
./dev/bin/stagingctl auth-setup
./dev/bin/govctl run staging.smoke-live --json
```

Notes:

- `staging.install` deploys into `staging-photo-ingress`.
- `staging.smoke` verifies runtime contracts inside staging.
- `web.test.e2e` and `web.test.integration` are staging-backed and use the E2E
  suite under `tests/e2e/`.
- `tests/staging-flow/flowctl` remains available for phase-based P2/P3 auth and
  poll validation when you need that deeper harness.

### 9.4 Production deployment

Goal: deploy the validated release into the production LXC container.

Production deployment is currently **not** wrapped by `govctl`. The production
install surface remains the installer scripts in `install/`.

Core steps:

1. Ensure staging validation has passed for the candidate.
2. Ensure required host ZFS datasets exist.
3. Run the installer into the target production container.

Examples:

```bash
sudo ./install/install.sh
sudo ./install/install.sh --container my-photo-ingress
sudo ./install/uninstall.sh
```

Install options:

| Option | Purpose |
|---|---|
| `--container <name>` | override the production container name |
| `--image <image>` | override the image used when creating the container |
| `--profile <name>` | override the LXD profile used when creating the container |

`TARGET_CONTAINER=<name>` is the environment-variable equivalent of
`--container`.

Inside the production container, the packaged service is installed under
`/opt/nightfall-photo-ingress`, and packaged docs are installed under
`/opt/nightfall-photo-ingress/share/doc/nightfall-photo-ingress`.

Required host datasets before install:

```bash
zfs create -o mountpoint=/mnt/ssd/photo-ingress ssdpool/photo-ingress
zfs create -o mountpoint=/nightfall/media/photo-ingress nightfall/media/photo-ingress
```

### 9.5 Promotion rule

The intended release boundary is:

1. build the candidate
2. install and validate it in staging
3. promote the validated packaging to production

The dev container accelerates iteration. Staging is the release rehearsal.
Production remains the packaged runtime environment.

---

## 10. Runtime and Deployment Notes Developers Should Know

### 10.1 Runtime layout inside deployed containers

| Path | Purpose |
|---|---|
| `/etc/nightfall/photo-ingress.conf` | runtime config |
| `/var/lib/ingress/` | working state |
| `/run/nightfall-status.d/photo-ingress.json` | status snapshot |
| `/var/log/nightfall` | file-backed logs when configured |

Path note:

- Example host-side storage paths such as `/mnt/ssd/photo-ingress/` appear in
  config examples and installer prerequisites.
- Inside deployed LXC containers, runtime working state is under
  `/var/lib/ingress/`.

### 10.2 Packaged units

Production and staging work with the same named units:

- `nightfall-photo-ingress.service`
- `nightfall-photo-ingress.timer`
- `nightfall-photo-ingress-trash.path`
- `nightfall-photo-ingress-trash.service`

### 10.3 Staging versus production

- Staging is wheel-first and validation-focused.
- Production is stable unattended runtime.
- Staging includes release rehearsal tooling and smoke helpers.
- Production uses install scripts and packaged service layout.

---

## 11. When To Read Other Documents

Use this handbook first for day-to-day engineering workflow. Read the other
documents when you need deeper detail in a specific area.

| Need | Document |
|---|---|
| operator runtime layout, packaged units, production install/uninstall | `docs/operations-runbook.md` |
| staging subsystem contract | `staging/README.md` |
| operator maintenance and live validation | `docs/operator/maintenance.md` |
| operator troubleshooting and recovery | `docs/operator/troubleshooting.md` |
| governor internals and rationale | `design/infra/build-governor-design.md` |
| devctl snapshot/update rationale | `design/infra/devctl-update-architecture.md` |
| container invariants | `design/infra/container-invariants.md` |
| metrics decoupling and runtime design | `design/infra/metrics-ctl-design.md` |

---

## 12. Recommended Baseline Commands

For a typical full validation cycle:

```bash
./dev/bin/govctl run devcontainer.prepare --json
./dev/bin/govctl run backend.test.unit --json
./dev/bin/govctl run backend.test.integration --json
./dev/bin/govctl run test.web --json
./dev/bin/govctl run staging.install --json
./dev/bin/govctl run staging.smoke --json
./dev/bin/govctl run web.test.e2e --json
```

For a quick backend-only loop:

```bash
./dev/bin/govctl run backend.test.unit --json
./dev/bin/govctl run backend.test.integration --json
```

For a quick web-only loop:

```bash
./dev/bin/govctl run devcontainer.prepare --json
./dev/bin/govctl run test.web --json
```