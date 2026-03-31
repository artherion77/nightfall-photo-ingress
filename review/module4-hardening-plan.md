# Module 4 Hardening Plan (Chunked, Commit-Oriented)

Date: 2026-03-31
Scope: Ingest decision engine + storage commit workflow

This plan is prioritized by production risk and designed so each chunk can be implemented and committed independently.

---

## Priority Order

1. M4-H1 Atomic ingest finalize transaction
2. M4-H2 Crash-boundary operation journal + replay
3. M4-H3 Staging reconciliation and drift reporting
4. M4-H4 Contract validation at ingest boundary
5. M4-H5 Storage durability and root-containment hardening
6. M4-H6 Ingest integrity and policy controls
7. M4-H7 Audit completeness and ordering metadata
8. M4-H8 Performance/scalability improvements
9. M4-H9 Security policy tightening

---

## M4-H1 Atomic ingest finalize transaction

- [x] Implement one registry API for ingest-finalize in a single transaction.
- [x] Ensure updates include: `files`, `accepted_records`, `metadata_index`, `file_origins`, `audit_log`.
- [x] Add rollback behavior tests for injected failures at each internal step.
- [x] Add regression test for idempotent replay after simulated crash.

Commit scope:
- Registry API changes
- Ingest call path updated to use atomic finalize
- Unit + integration tests

---

## M4-H2 Crash-boundary operation journal + replay

- [x] Add append-only lifecycle journal for ingest phases:
  - `ingest_started`
  - `hash_completed`
  - `storage_committed`
  - `registry_persisted`
- [x] Implement startup replay/reconcile logic for interrupted records.
- [x] Ensure journal entries are durable and rotation policy is defined.
- [x] Add crash simulation tests for each boundary.

Commit scope:
- New journal helper(s)
- Ingest writes/reads journal
- Replay recovery tests

---

## M4-H3 Staging reconciliation and drift reporting

- [ ] Extend recovery beyond `.tmp` age cleanup.
- [ ] Classify and handle:
  - stale temp
  - completed-but-unpersisted
  - orphan unknown artifacts
- [ ] Add quarantine folder workflow instead of blind delete for suspicious files.
- [ ] Emit drift counters and threshold warnings.

Commit scope:
- Reconciliation logic
- Drift metrics/events
- Recovery integration tests

---

## M4-H4 Contract validation at ingest boundary

- [ ] Add explicit schema/version field for ingest input payload.
- [ ] Add strict validator for required candidate fields and allowed formats.
- [ ] Fail-fast on incompatible contract with actionable errors.
- [ ] Add compatibility tests with malformed and version-mismatch payloads.

Commit scope:
- Contract datamodel/validator
- Ingest pre-batch validation
- Contract tests

---

## M4-H5 Storage durability and root-containment hardening

- [ ] Enforce destination path resolved-under-root check before write.
- [ ] Add fsync durability step for cross-pool copy path before final replace.
- [ ] Add safer template normalization and reject unsafe path components.
- [ ] Add tests for traversal attempts and power-loss-simulated copy boundaries.

Commit scope:
- Storage helper hardening
- Path-safety checks
- Durability tests

---

## M4-H6 Ingest integrity and policy controls

- [ ] Add optional pre-hash size verification against candidate metadata.
- [ ] Add explicit zero-byte policy (`allow`, `quarantine`, `reject`).
- [ ] Add mismatch audit reasons and counters.
- [ ] Add tests for wrong size, missing size, and zero-byte branches.

Commit scope:
- Ingest policy flags and decision logic
- Integrity tests

---

## M4-H7 Audit completeness and ordering metadata

- [ ] Ensure all terminal outcomes emit audit events (`missing_staged`, recovery decisions, quarantine).
- [ ] Add `batch_run_id` and monotonic sequence number to audit metadata.
- [ ] Add tests verifying event ordering and completeness under mixed outcomes.

Commit scope:
- Audit payload enrichment
- Ordering tests

---

## M4-H8 Performance and scalability improvements

- [ ] Add optional bounded ingest worker pool.
- [ ] Add size-aware scheduling strategy.
- [ ] Add metadata prefilter hit/miss diagnostics to reduce unnecessary hash I/O.
- [ ] Add throughput benchmarks and regression guardrails.

Commit scope:
- Worker orchestration + scheduling
- Perf-focused tests/benchmarks

---

## M4-H9 Security policy tightening

- [ ] Enforce output file/directory permission policy.
- [ ] Add collision-loop threshold telemetry and alerts.
- [ ] Add template policy linter for unsafe patterns.
- [ ] Add security-focused tests for permissions and name/path edge cases.

Commit scope:
- Security policy helpers
- Validation + telemetry
- Security tests

---

## Execution Checklist (for each chunk)

- [ ] Implement chunk scope only
- [ ] Add dedicated unit tests
- [ ] Add integration tests (mocked where needed)
- [ ] Run targeted tests
- [ ] Run full regression suite
- [ ] Commit with chunk-specific message
- [ ] Mark chunk as completed in this file

---

## Suggested commit message format

`harden(module4/<chunk-id>): <short summary>`

Examples:
- `harden(module4/m4-h1): atomicize ingest finalize transaction`
- `harden(module4/m4-h2): add crash-boundary journal replay`
