# nightfall-photo-ingress

Pending-first photo ingress runtime with explicit accept, reject, and purge transitions.

## Project structure

This repository uses a standard `src` layout so local imports match the installed
wheel layout:

```text
nightfall-photo-ingress/
├── pyproject.toml
├── docs/
├── src/
│   └── nightfall_photo_ingress/
├── tests/
├── conf/
├── design/
├── planning/
├── review/
└── testspecs/
```

## Current scope

This repository now includes a hardened OneDrive client polling component with:
- deterministic account polling order
- delta pagination guards and resync markers
- streamed staging downloads with integrity checks
- retry/backoff handling for Graph and download requests
- structured redacted error taxonomy
- diagnostics counters for retries/throttling/resync/ghost scenarios

## Local development commands

```bash
python -m pip install -e ".[dev]"
pytest
python -m nightfall_photo_ingress --help
nightfall-photo-ingress --help
```

## Build and install

Build a wheel for deterministic deployment:

```bash
python -m build
python -m pip install dist/*.whl
```

The installed console entry point is compatible with `systemd` units:

```bash
nightfall-photo-ingress poll --path /etc/nightfall/photo-ingress.conf
```

`poll` executes both the OneDrive download stage and the ingest decision stage in one run. Newly discovered content lands in `pending`; only explicit `accept` writes `accepted` state.

Version 2.0 is intentionally incompatible with the legacy accepted-first topology. It requires:
- `config_version = 2`
- explicit `pending_path`, `accepted_path`, `rejected_path`, and `trash_path`
- a freshly bootstrapped `registry.db` at schema version 2

Packaged operational assets live under `systemd/`, `install/`, and `docs/`. The operator runbook is `docs/operations-runbook.md`. The production install workflow targets an LXC container named `photo-ingress` by default and deploys a copy of the runbook under `/opt/nightfall-photo-ingress/share/doc/nightfall-photo-ingress/` inside that container.

## Robustness regression suite (Chunk 10)

Run only resilience scenarios:

```bash
pytest -m robustness tests/unit/test_onedrive_robustness_regression.py
```

Run all tests except resilience scenarios:

```bash
pytest -m "not robustness"
```

## CLI commands

```bash
nightfall-photo-ingress auth-setup --help
nightfall-photo-ingress poll --help
nightfall-photo-ingress accept --help
nightfall-photo-ingress reject --help
nightfall-photo-ingress purge --help
nightfall-photo-ingress process-trash --help
nightfall-photo-ingress sync-import --help
```
