# nightfall-photo-ingress

Incremental ingest service for photos, starting with a OneDrive adapter.

## Project structure

This repository uses a standard `src` layout so local imports match the installed
wheel layout:

```text
nightfall-photo-ingress/
├── pyproject.toml
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

## Robustness regression suite (Chunk 10)

Run only resilience scenarios:

```bash
pytest -m robustness tests/test_onedrive_robustness_regression.py
```

Run all tests except resilience scenarios:

```bash
pytest -m "not robustness"
```

## CLI stubs available in Module 0

```bash
nightfall-photo-ingress auth-setup --help
nightfall-photo-ingress poll --help
nightfall-photo-ingress reject --help
nightfall-photo-ingress process-trash --help
nightfall-photo-ingress sync-import --help
```
