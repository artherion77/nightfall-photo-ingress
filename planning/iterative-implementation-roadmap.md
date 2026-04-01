# photo-ingress Iterative Implementation Roadmap

Status: Drift-corrected to audited implementation state
Date: 2026-04-01
Owner: Systems Engineering

Related roadmap:
- [Web Control Plane Implementation Roadmap](web-control-plane-implementation-roadmap.md)

## Audited reality snapshot (2026-04-01)

This section corrects documentation drift between the original sequential plan and
the implemented repository state.

| Area | Original roadmap status | Audited repository status |
|---|---|---|
| Module 0 | Completed | Completed |
| Module 1 | Completed | Completed |
| Module 2 | Completed | Completed |
| Module 3 | Not started | Implemented + hardening delivered (Chunk 1-10 and V2-1..V2-10) |
| Module 4 | Not started | Implemented + hardening delivered (H1-H9 coverage present) |
| Integration M3+M4 | Planned | Implemented with documented compliance gaps to close |
| Module 5-8 | Planned | Still planned (not yet implemented) |

Evidence base:
- `review/module3-hardening-chunk-plan.md`
- `review/module3-hardening-plan-v2.md`
- `review/module3-module4-integration-suite-compliance-audit-final.md`
- `tests/unit/` and `tests/integration/` current tree
- `src/nightfall_photo_ingress/` current module tree

Note:
- The original STOP gates were not followed strictly in execution order.
- This roadmap remains the planning artifact; implementation truth is recorded by
  source, tests, and review artifacts above.

## How to use this plan

- Execute modules strictly in order.
- Do not start the next module until the current module passes tests and receives review approval.
- If issues are found, revise this plan section before continuing.
- Tick checkboxes as work completes.

## Global implementation guardrails

- [ ] Use Python 3.11+ and strict type hints.
- [ ] Keep OneDrive as adapter-specific logic (`provider = onedrive`) and keep core domain provider-agnostic.
- [ ] No direct write access to permanent library (`/nightfall/media/pictures`) in ingest flows.
- [ ] Keep all operator-facing text/logs/comments in English.
- [ ] Keep all stateful writes idempotent and transaction-safe.
- [ ] Require tests for each module before merge.

---

## Module 0: Project Skeleton and Build/Test Harness

### Purpose and scope
Create a stable project scaffold, dependency management, CLI entrypoint shell, and test harness to support incremental development.

### Inputs and outputs
- Inputs:
  - Approved design docs in `design/`
  - Naming matrix and config spec
- Outputs:
  - Runnable package skeleton
  - Test tooling and CI-local command flow

### Internal components
- Package layout (`nightfall_photo_ingress/`)
- CLI skeleton (`cli.py`, `__main__.py`)
- Config loader placeholder (`config.py`)
- Test harness (`tests/`, pytest config)
- Logging bootstrap helper

### Implementation steps
- [x] Create package directories and `__init__.py` files.
- [x] Add `pyproject.toml` with runtime and dev dependencies.
- [x] Add CLI command group with stub commands (`auth-setup`, `poll`, `reject`, `process-trash`, `sync-import`).
- [x] Add base logger setup with JSON/human mode switch.
- [x] Add make-like command documentation in README (no implementation details yet).

### Unit tests
- [x] CLI command registration test.
- [x] Logger mode selection test.
- [x] Basic import tests for package modules.

### Integration tests
- [x] `python -m nightfall_photo_ingress --help` returns exit code 0.
- [x] `pytest` runs and discovers tests in clean environment.

### Expected artifacts
- `pyproject.toml`
- `nightfall_photo_ingress/__main__.py`
- `nightfall_photo_ingress/cli.py`
- `tests/test_cli_bootstrap.py`
- `tests/test_logging_bootstrap.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 1: Config Model, Validation, and Versioning

### Purpose and scope
Implement strict INI configuration loading and validation from `/etc/nightfall/photo-ingress.conf`, including account sections and schema version checks.

### Inputs and outputs
- Inputs:
  - `design/configspec.md`
  - canonical naming rules
- Outputs:
  - Typed config object
  - Validation report with clear errors

### Internal components
- INI parser
- typed config dataclasses/TypedDicts
- validation rules engine
- account section discovery (`[account.<name>]`)
- config version checker
- account ordering policy reader (declaration order)

### Implementation steps
- [x] Implement parser for `[core]`, `[logging]`, and `[account.*]` sections.
- [x] Validate required keys, path fields, booleans, integer ranges.
- [x] Enforce unique `token_cache` and `delta_cursor` per account.
- [x] Enforce provider support (`onedrive` only in V1, explicit error for others).
- [x] Implement `process_accounts_in_config_order` semantics (`true` default) using declaration order from config file.
- [x] Add and validate Live Photo pairing config keys with V1 defaults:
  - `live_photo_capture_tolerance_seconds`
  - `live_photo_stem_mode`
  - `live_photo_component_order`
  - `live_photo_conflict_policy`
- [x] Add and validate `verify_sha256_on_first_download` (default `true`).
- [x] Add config diagnostics output command (`config-check`).

### Unit tests
- [x] Valid config round-trip parse test.
- [x] Missing-key and wrong-type validation tests.
- [x] Duplicate token/cursor path rejection test.
- [x] Unsupported provider rejection test.
- [x] Invalid account name pattern test.
- [x] Account declaration order preservation test.
- [x] Live Photo config default and enum validation tests.
- [x] `verify_sha256_on_first_download` default and bool parsing tests.

### Integration tests
- [x] `config-check` against sample valid config exits 0.
- [x] `config-check` against sample invalid config exits non-zero and prints actionable messages.

### Expected artifacts
- `nightfall_photo_ingress/config.py`
- `tests/test_config_parsing.py`
- `tests/test_config_validation.py`
- `conf/photo-ingress.conf.example`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 2: Registry Core and Schema Migration Engine

### Purpose and scope
Build the SQLite system-of-record with schema versioning, append-only audit logging, acceptance history, and migration support.

### Inputs and outputs
- Inputs:
  - Validated config (`registry_path`)
  - schema requirements from design docs
- Outputs:
  - initialized/migrated SQLite DB
  - repository methods for reads/writes

### Internal components
- SQLite connection manager
- migration runner (`PRAGMA user_version`)
- core tables:
  - `files`
  - `metadata_index`
  - `accepted_records`
  - `file_origins`
  - `audit_log`
- transaction helpers

### Implementation steps
- [x] Implement DB initialization and schema creation at version 1.
- [x] Implement migration framework scaffold for future versions.
- [x] Implement CRUD operations for file status transitions.
- [x] Implement immutable audit event append API.
- [x] Implement account-aware origin/provenance upsert logic.

### Unit tests
- [x] Fresh DB initialization test.
- [x] Migration idempotency test.
- [x] Status transition transaction test (`accepted -> rejected -> purged`).
- [x] Audit immutability test.
- [x] Accepted history retained when physical file path disappears test.

### Integration tests
- [x] End-to-end DB lifecycle test from empty DB to populated records.
- [x] Simulated restart test preserving consistency.

### Expected artifacts
- `nightfall_photo_ingress/registry.py`
- `nightfall_photo_ingress/migrations/`
- `tests/test_registry_schema.py`
- `tests/test_registry_operations.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 3: OneDrive Adapter (Auth + Delta + Download)

### Purpose and scope
Implement OneDrive adapter with account-scoped token cache, delta cursor handling, resilient pagination, and streaming download.

### Inputs and outputs
- Inputs:
  - account config (`authority`, `client_id`, `onedrive_root`, token/cursor paths)
- Outputs:
  - normalized remote candidate list
  - downloaded staging files for unknown items

### Internal components
- MSAL auth client (device code + silent refresh)
- Graph client (delta API + pagination)
- cursor manager (per-account)
- downloader with retry/backoff and throttling support

### Implementation steps
- [x] Implement account-scoped token cache handling with file mode enforcement.
- [x] Implement `auth-setup --account` flow.
- [x] Implement delta fetch and pagination parser.
- [x] Implement cursor persistence and recovery strategy.
- [x] Implement resilient download with `Retry-After` handling.
- [x] Deliver hardening set Chunk 1-10.
- [x] Deliver hardening set V2-1..V2-10.

### Unit tests
- [x] Token cache file permission enforcement test.
- [x] Delta parser test with create/rename/delete payloads.
- [x] Cursor recovery fallback test.
- [x] Retry policy tests for 429/503.

### Integration tests
- [x] Mocked Graph API end-to-end poll cycle for one account.
- [x] Multi-account polling sequence with independent cursors.
- [x] Multi-account poll ordering test: enabled accounts execute in config declaration order.

### Expected artifacts
- `src/nightfall_photo_ingress/adapters/onedrive/auth.py`
- `src/nightfall_photo_ingress/adapters/onedrive/client.py`
- `tests/unit/test_onedrive_auth.py`
- `tests/unit/test_onedrive_delta.py`

### Follow-up status after audit
- Open: integration boundary fidelity corrections for Module 3 -> Module 4 handoff.
- Open: operator semantics and audit coherence assertions in integration suite.

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 4: Ingest Decision Engine and Staging Workflow

### Purpose and scope
Apply metadata prefiltering, compute authoritative SHA-256, consult registry, and manage accepted queue behavior without touching permanent library.

### Inputs and outputs
- Inputs:
  - remote candidates from Module 3
  - staging path and accepted path from config
  - registry APIs from Module 2
- Outputs:
  - updated registry state
  - files persisted or discarded in staging/accepted according to policy

### Internal components
- candidate evaluator
- hasher (streaming SHA-256)
- ingest state machine
- file mover/copy-verifier for cross-pool behavior

### Implementation steps
- [x] Implement metadata prefilter (`metadata_index`) to skip obvious known items.
- [x] Implement staged hashing pipeline.
- [x] Implement decision matrix:
  - unknown => queue to accepted + record acceptance
  - accepted/rejected/purged => discard staging + audit
- [x] Implement collision-safe accepted naming via storage template.
- [x] Implement cleanup of temp/incomplete staging files.
- [x] Deliver hardening set H1-H9.

### Unit tests
- [x] SHA-256 hashing correctness test.
- [x] Decision matrix branch coverage test.
- [x] Name collision handling test.
- [x] Cross-pool copy-verify-unlink behavior test.

### Integration tests
- [x] Synthetic ingest run with mixed known/unknown/rejected files.
- [x] Restart recovery test with leftover `.tmp` files.

### Expected artifacts
- `src/nightfall_photo_ingress/domain/ingest.py`
- `src/nightfall_photo_ingress/domain/storage.py`
- `tests/unit/test_ingest_decisions.py`
- `tests/unit/test_staging_recovery.py`

### Follow-up status after audit
- Open: complete lifecycle-level crash injection seams in integration harness.
- Open: strengthen invariant assertions around accepted queue vs. registry/journal states.

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 5: Live Photo Support (V1 Required)

### Purpose and scope
Support iPhone Live Photos as a first-class V1 feature by pairing image/video components and preserving pair provenance.

### Inputs and outputs
- Inputs:
  - downloaded OneDrive candidates
  - file metadata (name, timestamps, size)
- Outputs:
  - paired ingest decisions
  - pair metadata persisted in registry

### Internal components
- live photo detector
- pair correlation engine
- pair status recorder
- timeout/deferred pairing queue

### Implementation steps
- [x] Wire pairing heuristics to config parameters with V1 defaults:
  - `live_photo_capture_tolerance_seconds = 3`
  - `live_photo_stem_mode = exact_stem`
  - `live_photo_component_order = photo_first`
  - `live_photo_conflict_policy = nearest_capture_time`
- [x] Enforce V1 support policy: runtime accepts only default enum values while preserving parameterized configuration surface.
- [x] Introduce `live_photo_pairs` registry table with component references.
- [x] Implement deferred pairing logic when counterpart arrives later.
- [x] Ensure reject/accept actions are applied consistently to pair members.
- [x] Add operator diagnostics for unresolved pair candidates.

### Unit tests
- [x] Pair detection by stem/time rules using configured defaults.
- [x] Late-arrival pairing test.
- [x] Rejection propagation across pair members test.
- [x] Unresolved candidate aging test.
- [x] Unsupported non-default heuristic value rejection test (V1 policy).

### Integration tests
- [x] Ingest mixed burst containing HEIC+MOV pairs and standalone assets.
- [x] Re-upload of previously rejected pair blocked correctly.

### Expected artifacts
- `nightfall_photo_ingress/live_photo.py`
- registry migration for `live_photo_pairs`
- `tests/test_live_photo_pairing.py`
- `tests/integration/test_live_photo_integration.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 6: Sync-Import from Permanent Library Hash Files

### Purpose and scope
Implement operator-triggered sync import from read-only `/nightfall/media/pictures` using existing `.hashes.sha1` artifacts to prevent unnecessary re-download.

### Inputs and outputs
- Inputs:
  - `sync_hash_import_path`
  - `sync_hash_import_glob` (default `.hashes.sha1`)
- Outputs:
  - imported hash index entries tied to accepted history/provenance

### Internal components
- hash file parser compatible with existing format
- import planner (new/known/conflict handling)
- import reporter

### Implementation steps
- [x] Implement parser for per-directory `.hashes.sha1` files.
- [x] Validate and normalize imported hash entries.
- [x] Map imported entries into advisory external hash cache structures.
- [x] Add `sync-import` CLI command with dry-run mode.
- [ ] Apply `verify_sha256_on_first_download` behavior:
  - when `true` (default), advisory SHA1 match triggers one verification download for canonical SHA-256
  - when `false`, advisory SHA1 match may skip download
- [x] Add import summary output (new, skipped, invalid lines).

Current implementation note:
- Missing, stale, or invalid `.hashes.sha1` files fall back to read-only directory re-hash for import only; importer never rewrites library cache files.

### Unit tests
- [x] Parser compatibility test with known hash file fixtures.
- [x] Invalid line/error handling tests.
- [x] Idempotent re-import test.
- [ ] `verify_sha256_on_first_download=true` path test (one-time verification download).
- [ ] `verify_sha256_on_first_download=false` path test (metadata-only skip).

### Integration tests
- [x] Simulated read-only library import flow with nested directories.
- [ ] Poll-after-import test showing reduced downloads.

### Expected artifacts
- `nightfall_photo_ingress/sync_import.py`
- `tests/test_sync_hash_import_parser.py`
- `tests/test_sync_import_integration.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 7: Rejection Flows (Trash + CLI) and Lifecycle State Updates

### Purpose and scope
Implement both operator-triggered rejection paths and ensure lifecycle states remain consistent and auditable.

### Inputs and outputs
- Inputs:
  - files in `trash_path`
  - CLI `reject` requests
- Outputs:
  - updated file statuses and audit records
  - cleaned trash staging

### Internal components
- trash scanner/processor
- reject command handler
- lifecycle transition validator

### Implementation steps
- [ ] Implement `process-trash` command with idempotent behavior.
- [ ] Implement `reject <sha256>` with reason/actor metadata.
- [ ] Ensure accepted history retained even after queue file deletion.
- [ ] Add guardrails for already-rejected and unknown hashes.
- [ ] Emit structured audit events for all transitions.

### Unit tests
- [ ] CLI rejection idempotency test.
- [ ] Trash processing branch tests.
- [ ] Transition validation tests.

### Integration tests
- [ ] End-to-end reject and re-upload-block scenario.
- [ ] Batch trash processing scenario.

### Expected artifacts
- `nightfall_photo_ingress/pipeline/reject.py`
- `tests/test_reject_cli.py`
- `tests/test_trash_processor.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Module 8: Observability, Health, and Operational Packaging

### Purpose and scope
Provide production operability: structured logs, status file export, systemd units/timers/path units, install scripts, and runbooks.

### Inputs and outputs
- Inputs:
  - completed core modules
  - service scheduling requirements
- Outputs:
  - deployable service package
  - health and troubleshooting visibility

### Internal components
- status exporter (`/run/nightfall-status.d/photo-ingress.json`)
- poll metrics counters
- systemd unit files
- install/uninstall scripts

### Implementation steps
- [ ] Implement status snapshot writer (atomic write/rename).
- [ ] Implement per-account and global counters in logs/status.
- [ ] Add systemd files:
  - poll service/timer
  - trash path/service
- [ ] Add install scripts for `/etc/nightfall` config and service enablement.
- [ ] Add operator runbook and failure playbooks.

### Unit tests
- [ ] Status file schema and atomic write tests.
- [ ] Logging field completeness tests.

### Integration tests
- [ ] systemd smoke tests in controlled environment.
- [ ] End-to-end poll to status export to health consumer compatibility test.

### Expected artifacts
- `systemd/nightfall-photo-ingress-poll.service`
- `systemd/nightfall-photo-ingress-poll.timer`
- `systemd/nightfall-photo-ingress-trash.path`
- `systemd/nightfall-photo-ingress-trash.service`
- `install/install.sh`
- `install/uninstall.sh`
- `tests/test_status_export.py`

=== STOP: Awaiting user feedback before proceeding ===

---

## Iterative revision protocol (mandatory)

Apply this protocol after every module and before starting the next:

- [ ] Review test results and unresolved defects.
- [ ] Classify findings: design gap, implementation defect, or environment issue.
- [ ] If design gap exists, revise this roadmap module section before writing new code.
- [ ] Record decision/rationale in `design/decisions.md`.
- [ ] Re-estimate next module scope if complexity changed.
- [ ] Obtain explicit user approval to continue.

## Immediate post-audit execution order (next)

1. Boundary fidelity correction for Module 3 -> Module 4 integration harness.
2. Operator semantics and audit-coherence integration assertions.
3. Containerized staging environment for real-account smoke integration path.
4. Module 5 implementation (Live Photo V1 scope) after gates 1-3 are green.
5. Optional hardening idea: add deterministic time-control fixture for stale/replay tests.

## Definition of done per module

A module is done only when all are true:

- [ ] All module unit tests pass.
- [ ] All module integration tests pass.
- [ ] Artifacts listed for the module exist.
- [ ] Documentation and decisions updated.
- [ ] User approval received at STOP gate.
