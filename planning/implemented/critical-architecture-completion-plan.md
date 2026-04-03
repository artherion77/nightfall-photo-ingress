# Critical Architecture Completion Plan

**Status:** FULLY IMPLEMENTED (Chunks A, B, and C complete)  
**Author:** GitHub Copilot (reverse-engineered from implementation)  
**Created:** 2026-04-03  
**Scope:** Address the three Critical gaps identified in `audit/documentation-sufficiency-report.md` (G-01, G-02, G-03) that prevent a third-party AI model from reconstructing the system correctly.

---

## Background

The documentation sufficiency audit (`audit/documentation-sufficiency-report.md`) assessed the photo-ingress codebase at approximately 80% reconstruction fidelity. Three Critical gaps were identified — meaning a third-party model reading only the design documents would make materially wrong assumptions about core runtime behaviour:

| Gap ID | Description |
|--------|-------------|
| G-01 | No state machine diagram or transition table for `files.status` |
| G-02 | `live_photo_pairs.status` lifecycle is undocumented |
| G-03 | Schema migration mechanism is entirely undocumented |

This plan defines how to close all three gaps. Each gap becomes one execution chunk, to be completed in separate turns with user steering between them.

---

## Chunk A — Formal State Machine Specification

### Objectives

- Produce a canonical, complete state machine specification for the `files.status` field.
- State all valid statuses, all valid transitions, the trigger (code path) for each transition, the guard conditions that must hold before the transition fires, and the side effects produced.
- Provide a transition table and an ASCII or Mermaid diagram summary.
- Eliminate all ambiguity about which transitions are legal, which are prohibited, and what happens when a prohibited transition is attempted.

### Missing Information to Be Extracted from Implementation

- The full set of valid statuses: confirmed as `{"pending", "accepted", "rejected", "purged"}` from `ALLOWED_FILE_STATUSES` in `domain/registry.py`.
- The initial status on first ingest: `pending` (set in `upsert_from_staging()`).
- Transition: `pending → accepted`: triggered by `reject.accept_sha256()` → `registry.finalize_accept_from_pending()`. Guard: `record.status == "pending"`.
- Transition: `pending → rejected`: triggered by the trash-watch path via `_apply_reject()` in `reject.py`. Guard: status must be in `ALLOWED_FILE_STATUSES` (any status can be passed to `transition_status()`; the guard is enforced by the caller semantics, not by a database CHECK).
- Transition: `accepted → rejected`: confirm whether this path exists at all — `_apply_reject()` receives `known_status` and appears to accept any value in `ALLOWED_FILE_STATUSES`; need to confirm exact guard.
- Transition: `rejected → purged`: triggered by `reject.purge_sha256()` → `registry.finalize_purge_from_rejected()`. Guard: `record.status == "rejected"`.
- Transition: `* → *` via `transition_status()`: this is a general-purpose escape hatch; need to determine which callers use it, under what conditions, and whether any callers bypass normal guards.
- Terminal states: confirm that `purged` is terminal (no outbound transitions from `purged` exist).
- Error behaviour: confirm that `pending → purged` (skipping `rejected`) is blocked and how (exception type, message).
- Side effects per transition: file moves, audit_log entries, `accepted_records` inserts, `current_path` nullification on purge.
- The `discard_*` audit_log actions (e.g. `discard_pending`, `discard_accepted`) — confirm what code paths emit these and whether they correspond to status transitions or are advisory-only audit events.

### Missing Information to Be Clarified at Design Level

- Whether `accepted → rejected` is an intentional operator workflow or an implementation artefact.
- Whether `purged` records can ever be re-ingested (i.e. does a new ingest attempt for the same sha256 bypass the `purged` guard via upsert semantics, or is `purged` a permanent tombstone?).
- The intended meaning of the `discard_*` audit actions in relation to the status state machine — are they status transitions, or parallel event records for already-handled files?

### Dependencies

- None. This chunk has no dependency on Chunk B or Chunk C.
- Source file: `src/nightfall_photo_ingress/domain/registry.py`
- Source file: `src/nightfall_photo_ingress/reject.py`
- Source file: `src/nightfall_photo_ingress/domain/ingest.py`

### Expected Output Documents

- `design/architecture/state-machine.md`

### Acceptance Criteria

- The document states all 4 valid `files.status` values with definitions.
- The document contains a complete transition table with columns: (From Status, To Status, Trigger / Code Path, Guard Condition, Side Effects, Error if Guard Fails).
- Every outbound transition from every non-terminal state is covered.
- Terminal state(s) are explicitly labelled.
- A Mermaid state diagram is included that is consistent with the transition table.
- The document answers unambiguously: can `pending → purged` occur? Can `purged` be re-entered?
- After reading only this document and `design/domain-architecture-overview.md`, a third-party model can implement a correct status-guarded transition without reading any source code.

### Boundaries (Explicitly Out of Scope)

- `live_photo_pairs.status` transitions — covered in Chunk B.
- Schema migration mechanism — covered in Chunk C.
- Operator workflows (runbook procedures, CLI invocations) — covered in `docs/operations-runbook.md`.
- Web control plane status integration.
- Security / threat model.

---

## Chunk B — Live Photo Pair Lifecycle Specification

### Objectives

- Produce a complete lifecycle specification for `live_photo_pairs` records and their `status` field.
- Explain how pairs are detected, created, and why the pair `status` is a separate field from the individual `files.status` values of its two members.
- Define all pair statuses, all valid pair status transitions, and the atomicity contract (what happens when the two member `files` records and the pair record must all change together).
- Clarify single-member-rejected semantics — what happens when only one component (photo or video) fails while the other succeeds.
- Eliminate all ambiguity about `paired` as an initial pair status that does not appear in `ALLOWED_FILE_STATUSES`.

### Missing Information to Be Extracted from Implementation

- The pair `status` values: confirmed as `{"paired", "pending", "accepted", "rejected", "purged"}` from the `CHECK` constraint in `_schema_v2_sql()`. Note: `paired` is NOT in `ALLOWED_FILE_STATUSES` for `files.status`.
- Initial pair status at creation: `"paired"` (default in `upsert_live_photo_pair()`).
- Initial `files.status` for pair members at creation: need to confirm whether pair members enter `files` as `pending` or as some other status when first upserted via the ingest batch path.
- Transition: pair `paired → pending`: need to identify which code path triggers this — suspected to be the ingest batch completing both components.
- Transition: pair `pending → accepted`: triggered by `apply_live_photo_pair_status()` which calls `transition_status()` on both members and then updates the pair record.
- Transition: pair `pending → rejected`: same method; need guard conditions.
- Transition: pair `rejected → purged`: need to confirm whether this uses `apply_live_photo_pair_status()` or individual member purge calls.
- Atomicity contract: `apply_live_photo_pair_status()` uses separate `connection` calls for each member transition — confirm whether both member transitions and the pair record update are within a single SQLite transaction or across multiple transactions.
- Single-member failure: if one member's `transition_status()` raises, what is the state of the other member and the pair record? Is partial promotion observable?
- The `paired` status in the pair table when individual members are still in `pending` — is this the normal initial state (waiting for both halves), or does it indicate an error condition?
- Pair detection logic in `live_photo.py`: the heuristic matcher (stem equality, component type classification, timestamp tolerance window) — extract tolerance window constant and stem extraction algorithm for documentation.
- What happens to an unresolved candidate (one half arrives but the partner never arrives within the timeout): does the solo file become a regular `pending` file, or remain unresolved forever?
- `upsert_live_photo_pair()` upsert semantics: if a pair is re-upserted with a different status, what wins? (ON CONFLICT clause behaviour.)

### Missing Information to Be Clarified at Design Level

- Whether the `paired` status on the pair record is a transient assembly state or a stable "waiting for operator decision" state.
- The intended operator workflow for rejecting a Live Photo pair — is it always both-or-nothing, or can individual components be independently rejected?
- Whether a Live Photo pair can ever be partially accepted (photo accepted, video rejected).
- The correct response when a single component is moved to trash by the operator — does the trash-watch path reject only that file, or does it detect the pair and reject both?

### Dependencies

- Chunk A must be completed first, as the Live Photo pair lifecycle builds on the `files.status` state machine already specified.
- Source file: `src/nightfall_photo_ingress/live_photo.py`
- Source file: `src/nightfall_photo_ingress/domain/registry.py` (methods: `upsert_live_photo_pair`, `apply_live_photo_pair_status`, `get_live_photo_pair`, `get_live_photo_pair_for_member`)
- Source file: `src/nightfall_photo_ingress/domain/ingest.py` (live photo batch path)

### Expected Output Documents

- `design/architecture/live-photo-pair-lifecycle.md`

### Acceptance Criteria

- The document defines the `live_photo_pairs` table purpose and its relationship to `files`.
- The document explains why pair `status` has 5 values while `files.status` has 4 (specifically: what `paired` means and why it is not used in `files`).
- The document contains a pair status transition table with the same columns as the Chunk A table.
- The document states the atomicity contract for `apply_live_photo_pair_status()` — specifically whether the two `files` updates and the pair record update are atomic within one transaction.
- The document describes single-member failure behaviour explicitly.
- The document describes the pair detection heuristic (stem mode, component classification, tolerance window).
- The document describes what happens to an unresolved candidate when its partner exceeds the timeout.
- A Mermaid state diagram for the pair lifecycle is included.
- After reading only this document and `design/architecture/state-machine.md`, a third-party model can implement correct pair-lifecycle handling without reading source code.

### Boundaries (Explicitly Out of Scope)

- `files.status` state machine — covered in Chunk A.
- Web control plane Live Photo UI.
- sync-import Live Photo handling (separate deferred feature, annotated as not-implemented in open-points).
- Security / threat model.
- Operator runbook procedures for Live Photos.

---

## Chunk C — Schema Migration Mechanism (v2.x → v2.y Only)

### Objectives

- Document the SQLite schema versioning mechanism used by `photo-ingress` at v2.
- Make clear what `PRAGMA user_version` is, how it is used, and what `LATEST_SCHEMA_VERSION = 2` means in the runtime lifecycle.
- Document the v2 bootstrap path (version 0 → 2) and the forward/backward compatibility policy.
- Document `_ensure_optional_tables()` as the additive extension mechanism for minor schema additions within v2.
- Document what happens on version mismatch (version > LATEST, version < LATEST but non-zero) and why v1 → v2 migration is out of scope.

### Missing Information to Be Extracted from Implementation

- `LATEST_SCHEMA_VERSION = 2` declared in `domain/registry.py`.
- Migration invoked from `Registry.initialize()` only — not from individual operation methods. Confirm the call site.
- `_run_migrations()` logic:
  - `version == 0` → runs `_schema_v2_sql()` and sets `PRAGMA user_version = 2`. This is the bootstrap path: a new database.
  - `version > 2` → raises `RegistryError` with "newer than supported" message. No downgrade path.
  - `version != 0 and version != 2` → raises `RegistryError` with "Legacy registry schema detected" message and explicit declaration that v1 databases are not automatically migrated.
- `_schema_v2_sql()` — the full DDL for the initial schema: `files`, `metadata_index`, `accepted_records`, `file_origins`, `audit_log`, `live_photo_pairs`, `external_hash_cache`, and immutability triggers on `audit_log`.
- `_ensure_optional_tables()` — creates `ingest_terminal_audit` with `CREATE TABLE IF NOT EXISTS`. Confirm where this is called from and what it represents as an extension pattern.
- The `ingest_terminal_audit` table structure: columns, purpose, and why it was added as an optional table rather than into the base schema.
- WAL mode and `foreign_keys = ON` — confirm these are set at connection-open time via `_set_pragmas()`, not stored in schema.
- The `migrations/__init__.py` module exists but is empty — confirm this is intentional and that all migration logic lives in `registry.py`.

### Missing Information to Be Clarified at Design Level

- The versioning policy for future minor additions: is `_ensure_optional_tables()` the intended pattern for v2.x → v2.y additions, or will `LATEST_SCHEMA_VERSION` be incremented for each additive change?
- Whether a v2.1 → v2.2 migration (additive columns to existing tables) is expected to follow the same mechanism or a different one.
- The rationale for the "no auto-migration from v1" decision: confirm this is intentional and whether it should be stated as a forward-guarantee ("v2.x will always auto-migrate from v2.0") or a break-point policy.

### Dependencies

- No dependency on Chunk A or Chunk B. This chunk can be executed in any order relative to A and B.
- Source file: `src/nightfall_photo_ingress/domain/registry.py` (functions: `_run_migrations`, `_schema_v2_sql`, `_ensure_optional_tables`, `Registry.initialize`, `Registry.schema_version`)
- Source file: `src/nightfall_photo_ingress/migrations/__init__.py` (currently empty — document intent)

### Expected Output Documents

- `design/architecture/schema-and-migrations.md`

### Acceptance Criteria

- The document explains SQLite `PRAGMA user_version` and its role as the schema version carrier.
- The document states `LATEST_SCHEMA_VERSION = 2` and what it means.
- The document describes the bootstrap path (user_version 0 → 2) with the exact schema tables created.
- The document describes the forward-incompatibility guard (user_version > 2 → hard error).
- The document describes the legacy-version guard (user_version 1 → hard error, no auto-migration).
- The document describes `_ensure_optional_tables()` as the additive extension pattern for `IF NOT EXISTS` tables within v2.
- The document lists all tables in the v2 schema with a one-line purpose for each.
- The document states which pragma settings are applied per-connection (WAL, foreign_keys).
- The document answers unambiguously: "What must an operator do when upgrading from v1 to v2?" and "What must an operator do when adding a new table to v2?"
- After reading only this document, a third-party model can implement a correct `initialize()` and `_run_migrations()` replacement without reading source code.

### Boundaries (Explicitly Out of Scope)

- v1 → v2 migration procedure (no auto-migration exists; the decision rationale is noted but the v1 schema is not documented here).
- Backup/restore procedures.
- Disaster recovery.
- Web control plane database interactions.
- Security / threat model.

---

## Execution Order and Steering Points

```
PHASE 0 (this document) → STOP, await user approval
    ↓
CHUNK A (state-machine.md) ✅ COMPLETE → commit fa18fe6 + state-machine spec
    ↓
CHUNK B (live-photo-pair-lifecycle.md) ✅ COMPLETE → commit ac89d15 + live-photo-pair-lifecycle spec
    ↓
CHUNK C (schema-and-migrations.md) ✅ COMPLETE → commit 2f12ee8 + schema-and-migrations spec
```

Each chunk must be completed and confirmed before the next begins. No cross-chunk work may be performed during a single chunk's execution turn.

---

## Target Fidelity Goal

Upon completion of all three chunks, the documentation sufficiency score for the following subsystems should move from their current levels to the target:

| Subsystem | Current Fidelity | Target Fidelity |
|-----------|-----------------|-----------------|
| Status state machine | ~55% | 95%+ |
| Live Photo pair lifecycle | ~40% | 90%+ |
| Schema versioning / migration | ~30% | 90%+ |
| Overall corpus | ~80% | 90%+ |
