## Module Architecture — Navigation Index

> This document is retained as a navigation reference. The authoritative design
> documentation is in `design/`. Sections that formerly lived here have been extracted
> to focused topic documents; cross-references are provided below.

---

### Design Document Map

| Topic | Document |
|---|---|
| Domain model, entity map, module-layer map | [design/domain/domain-model.md](design/domain/domain-model.md) |
| Domain constraints and invariants | [design/domain/constraints.md](design/domain/constraints.md) |
| Naming conventions and glossary | [design/domain/glossary.md](design/domain/glossary.md) |
| Adapter extensibility rationale | [design/rationale/tradeoffs.md](design/rationale/tradeoffs.md) |
| Pipeline data flow | [design/architecture/data-flow.md](design/architecture/data-flow.md) |
| File status state machine | [design/architecture/state-machine.md](design/architecture/state-machine.md) |
| Ingest lifecycle and crash recovery | [design/architecture/lifecycle.md](design/architecture/lifecycle.md) — overview; full spec: [design/architecture/ingest-lifecycle-and-crash-recovery.md](design/architecture/ingest-lifecycle-and-crash-recovery.md) |
| Error taxonomy and resilience | [design/architecture/error-taxonomy-and-resilience.md](design/architecture/error-taxonomy-and-resilience.md) |
| Observability internals | [design/architecture/observability.md](design/architecture/observability.md) |
| Configuration specification | [design/cli-config-specification.md](design/cli-config-specification.md) |
| Auth design | [design/auth-design.md](design/auth-design.md) |
| Web control plane | [design/web/](design/web/) |

---

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

> **Module responsibilities and entity descriptions** are documented in
> [design/domain/domain-model.md](design/domain/domain-model.md).  
> **Adapter extensibility pattern** is documented in
> [design/rationale/tradeoffs.md](design/rationale/tradeoffs.md).

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

### Version Boundary

> The version boundary constraints are defined in
> [design/domain/constraints.md](design/domain/constraints.md).

- **CLI surface:** includes `accept` and `purge` as first-class human state transitions
- **State machine:** ingest writes `pending`; only explicit operator accept writes `accepted_records`
- **Compatibility policy:** v2.0 drops accepted-first config and legacy registry upgrade paths; bootstrap a fresh config and registry for deployment
