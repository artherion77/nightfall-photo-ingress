# Architecture Overview

`nightfall-photo-ingress` is structured as a **domain core** surrounded by pluggable
adapter and CLI layers. The domain layer is entirely source-agnostic; all OneDrive-
specific logic lives in `adapters/onedrive/`.

For the full design documentation, see [design/README.md](design/README.md).

---

## Module Structure

```
src/nightfall_photo_ingress/
├── cli.py                   Command-line interface
├── config.py                Configuration loading and validation
├── logging_bootstrap.py     Structured logging initialisation
├── runtime/                 Infrastructure and orchestration shell
├── domain/                  Core business logic (source-agnostic)
│   ├── registry.py          SQLite state management
│   ├── ingest.py            Hash-based policy decisions
│   ├── storage.py           Destination path rendering and durable commit workflows
│   └── journal.py           Crash-recovery lifecycle journal (JSONL)
└── adapters/
    └── onedrive/            OneDrive adapter (currently the only source)
        ├── auth.py          MSAL device-code authentication and token cache
        ├── client.py        Graph delta polling and streaming download
        ├── retry.py         Exponential backoff with Retry-After support
        ├── errors.py        Typesafe exceptions + URL/credential redaction
        └── safe_logging.py  sanitize_extra() and _RedactingFormatter
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `adapters/onedrive/` | Enumerate new files from OneDrive via the Graph delta API; authenticate using MSAL; download to SSD staging; expose `poll_accounts()` as the sole integration surface |
| `domain/registry.py` | Authoritative ledger of all known files (SHA-256 primary key); `files`, `accepted_records`, `file_origins`, `metadata_index`, `live_photo_pairs`, `ingest_terminal_audit` tables |
| `domain/ingest.py` | `IngestDecisionEngine`: decides pending / discard / duplicate based on registry state; source-agnostic |
| `domain/storage.py` | Renders destination paths from `{yyyy}/{mm}/{original}` templates; executes durable rename-or-copy-verify-unlink transitions across pool boundaries |
| `domain/journal.py` | `IngestOperationJournal`: JSONL crash-boundary log written before each staging move; replayed on startup to recover interrupted operations |
| `cli.py` | Thin command dispatcher; wires config, domain, and adapters together; delegates all state changes to domain |

---

## How the Modules Interact

```
  CLI (cli.py)
   │
   ├── poll ──► adapter/onedrive/client.poll_accounts()
   │              │
   │              ► domain/ingest.IngestDecisionEngine
   │                    │
   │                    ► domain/registry  (SHA-256 lookup and write)
   │                    ► domain/storage   (atomic move to pending/)
   │                    ► domain/journal   (crash-boundary JSONL write)
   │
   ├── accept/reject/purge ──► domain/registry + domain/storage
   │
   └── process-trash ──► domain/registry + domain/storage
```

Adapters never import from `domain/`; `domain/` never imports from `adapters/`. All
coordination flows through `cli.py` or tests.

---

## Key Architectural Properties

**Pending-first lifecycle.** Every newly downloaded file is written to `pending/` with
`status = 'pending'`. No file reaches `accepted` without an explicit operator action.
This makes accidental promotion impossible.

**Registry as system of record.** `registry.db` (SQLite, SSD) is the only durable
state. SHA-256 is the canonical, immutable identity key. File paths are advisory.

**Crash safety.** The `IngestOperationJournal` is written before each staging-layer
file operation. On next startup `replay_interrupted_operations()` reconciles any
partially-applied moves before the poll run begins.

**Delta cursor discipline.** The OneDrive delta cursor is advanced only after all
page-level side-effects are committed. Interrupted runs resume from the last durable
cursor; no file is re-ingested twice (registry `ON CONFLICT DO UPDATE` guard).

**Immich independence.** The pipeline has no write path into Immich. Immich mounts the
permanent library (`/nightfall/media/pictures`) as a read-only external library. A
fresh Immich rebuild has no effect on ingress state.

**Adapter isolation.** Adding a second source (e.g. Google Photos) requires only a new
`adapters/google_photos/` package. `domain/`, `cli.py`, and all tests are unchanged.

---

## Design Document Index

| Topic | Document |
|---|---|
| End-to-end pipeline diagram | [design/architecture/data-flow.md](design/architecture/data-flow.md) |
| File status state machine | [design/architecture/state-machine.md](design/architecture/state-machine.md) |
| Ingest lifecycle and crash recovery — overview | [design/architecture/lifecycle.md](design/architecture/lifecycle.md) |
| Ingest lifecycle — full specification | [design/architecture/ingest-lifecycle-and-crash-recovery.md](design/architecture/ingest-lifecycle-and-crash-recovery.md) |
| Error taxonomy, retry policy, resilience | [design/architecture/error-taxonomy-and-resilience.md](design/architecture/error-taxonomy-and-resilience.md) |
| Observability: logging, counters, status snapshot | [design/architecture/observability.md](design/architecture/observability.md) |
| System invariants catalogue | [design/architecture/invariants.md](design/architecture/invariants.md) |
| Domain model and bounded context | [design/domain/domain-model.md](design/domain/domain-model.md) |
| Domain constraints and version boundary | [design/domain/constraints.md](design/domain/constraints.md) |
| Naming conventions and glossary | [design/domain/glossary.md](design/domain/glossary.md) |
| Registry schema and SQLite tables | [design/specs/registry.md](design/specs/registry.md) |
| Ingest, accept, reject, purge specs | [design/specs/](design/specs/) |
| Auth design (MSAL, token cache, device-code flow) | [design/auth-design.md](design/auth-design.md) |
| Configuration specification | [design/cli-config-specification.md](design/cli-config-specification.md) |
| Tech stack rationale and tradeoffs | [design/rationale/tradeoffs.md](design/rationale/tradeoffs.md) |
| Architecture decision log | [design/rationale/architecture-decision-log.md](design/rationale/architecture-decision-log.md) |
| Web control plane | [design/web/](design/web/) |


- **CLI surface:** includes `accept` and `purge` as first-class human state transitions
- **State machine:** ingest writes `pending`; only explicit operator accept writes `accepted_records`
- **Compatibility policy:** v2.0 drops accepted-first config and legacy registry upgrade paths; bootstrap a fresh config and registry for deployment
