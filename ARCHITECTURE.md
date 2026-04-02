## Module Architecture After Refactoring

This document explains the new modular structure, designed for extensibility to support multiple data sources (OneDrive, Google Photos, Flickr, etc.).

For web operator surface and API expansion planning, see:
- [design/web-control-plane-architecture-extension.md](design/web-control-plane-architecture-extension.md)
- [planning/web-control-plane-implementation-roadmap.md](planning/web-control-plane-implementation-roadmap.md)

### Directory Structure

```
src/nightfall_photo_ingress/
├── __init__.py              Package initialization
├── __main__.py              CLI entry point
├── cli.py                   Command-line interface
├── config.py                Configuration loading and validation
├── logging_bootstrap.py     Logging initialization
│
├── runtime/                 Infrastructure & Orchestration
│   ├── __init__.py
│   └── (future: command_runner, lifecycle managers)
│
├── domain/                  Core Business Logic (Source-Agnostic)
│   ├── __init__.py          Exports Registry, IngestDecisionEngine
│   ├── registry.py          SQLite state management (files, audit, metadata index)
│   ├── storage.py           Destination path rendering, durable commit workflows
│   ├── ingest.py            IngestDecisionEngine: hash-based policy decisions
│   ├── journal.py           Crash-recovery lifecycle journal
│   └── migrations/          Database schema migrations
│
├── adapters/                Pluggable External Data Sources
│   ├── __init__.py
│   └── onedrive/            OneDrive-specific adapter
│       ├── __init__.py
│       ├── auth.py          MSAL-based authentication (device code flow)
│       ├── client.py        Microsoft Graph API client (delta polling, downloads)
│       ├── retry.py         Exponential backoff retry policy
│       ├── cache_lock.py    Account-level singleton locking for poll safety
│       ├── errors.py        OneDrive-specific error taxonomy
│       └── safe_logging.py  URL/credential redaction for logs
```

### Module Responsibilities

#### **domain/** — Core Extensibility Layer
- **Registry**: ACID-safe system of record for ingested files, audit logs, metadata pre-filters
- **Storage**: Path templating, cross-pool resilience, durable staging-to-accepted workflows
- **IngestDecisionEngine**: Hash-based policy matrix (unknown → pending, known → discard)
- **Journal**: Append-only lifecycle log for crash recovery and idempotency

These modules are **source-agnostic** and work the same way whether data comes from OneDrive, Google Photos, or any future adapter.

#### **adapters/onedrive/** — Pluggable Data Source
All communication with external systems is isolated here:
- MSAL OAuth token management
- Microsoft Graph API deltas and file downloads
- Provider-specific error handling and retries

Future adapters follow this same pattern:
```
adapters/
├── onedrive/      (existing)
├── google_photos/ (future)
├── flickr/        (future)
└── base.py        (common adapter interface)
```

#### **runtime/** — Infrastructure
Currently a placeholder for:
- Command orchestration
- Lifecycle management
- Pluggable runtime adapters (e.g., systemd integration, container runtimes)

---

### Test Organization

Tests are split into **execution layers** for clarity and performance:

```
tests/
├── conftest.py             Shared pytest configuration
├── unit/                   Fast isolated unit tests (~4.7s, 237 tests)
│   ├── conftest.py         Unit-specific fixtures
│   ├── test_registry_*.py  Domain registry tests
│   ├── test_ingest_*.py    Ingest engine tests
│   ├── test_chunk*.py      OneDrive hardening specs
│   └── test_*.py           Other isolated tests
│
└── integration/            Cross-module integration tests (~0.13s, 6 tests)
    ├── conftest.py         Integration-specific fixtures (fake clients, harnesses)
    ├── test_m3_m4_*.py     Module 3 (OneDrive) ↔ Module 4 (Ingest) workflows
    └── (future: test_adapter_*.py for pluggable adapters)
```

**Running tests by layer:**
```bash
pytest tests/unit/           # Run only unit tests (fast feedback)
pytest tests/integration/    # Run integration tests
pytest tests/                # Run all tests (full regression)
```

---

### Adding a New Data Source

To add Google Photos as a second adapter:

1. **Create adapter structure:**
   ```
   src/nightfall_photo_ingress/adapters/google_photos/
   ├── __init__.py
   ├── auth.py         (OAuth2 + refresh tokens)
   ├── client.py       (Photos API calls)
   ├── errors.py       (Google-specific errors)
   └── retry.py        (Google rate-limit handling)
   ```

2. **No changes to domain/** — The IngestDecisionEngine, Registry, Storage, and Journal modules work identically for any source

3. **Update CLI:**
   ```python
   # cli.py
   from .adapters.onedrive.client import poll_accounts as onedrive_poll
   from .adapters.google_photos.client import poll_accounts as photos_poll
   ```

4. **Add integration tests:**
   ```
   tests/integration/test_google_photos_m3_m4_happy_path.py
   (identical contract to OneDrive tests)
   ```

---

### Import Patterns

**From domain (source-agnostic):**
```python
from nightfall_photo_ingress.domain.registry import Registry
from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine
```

**From a specific adapter:**
```python
from nightfall_photo_ingress.adapters.onedrive.client import poll_accounts
from nightfall_photo_ingress.adapters.google_photos.client import poll_accounts
```

**For CLI and tests:**
```python
# All adapters available, pick at runtime
from nightfall_photo_ingress.adapters import onedrive, google_photos
```

---

### Backward Compatibility

- **CLI surface expanded:** adds `accept` and `purge` commands for human state transitions
- **Package imports:** code using `from nightfall_photo_ingress.domain.registry import Registry` continues to work
- **State machine update:** ingest now writes `pending`; only explicit operator accept writes `accepted_records`

---

### Design Benefits

1. **Separation of Concerns**: Domain logic (what to do with files) is isolated from adapter logic (how to fetch them)
2. **Testability**: Each layer can be tested independently without mocking entire systems
3. **Scalability**: Adding a new source requires only a new adapter; core pipeline unchanged
4. **Maintainability**: Clear module boundaries make code easier to understand and modify
5. **Reusability**: Domain policies (registry, storage, ingest) can be used by multiple adapters simultaneously
