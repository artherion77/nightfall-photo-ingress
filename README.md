# nightfall-photo-ingress

Incremental ingest service for photos, starting with a OneDrive adapter.

## Module 0 scope

This repository currently provides project skeleton artifacts only:
- package layout
- CLI command stubs
- logging bootstrap helper
- pytest harness

No ingest or provider logic is implemented yet.

## Local development commands

```bash
python -m pip install -e ".[dev]"
pytest
python -m nightfall_photo_ingress --help
nightfall-photo-ingress --help
```

## CLI stubs available in Module 0

```bash
nightfall-photo-ingress auth-setup --help
nightfall-photo-ingress poll --help
nightfall-photo-ingress reject --help
nightfall-photo-ingress process-trash --help
nightfall-photo-ingress sync-import --help
```
