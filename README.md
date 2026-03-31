# nightfall-photo-ingress

Incremental ingest service for photos, starting with a OneDrive adapter.

## Current scope

This repository now includes a hardened Module 3 OneDrive polling client with:
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
