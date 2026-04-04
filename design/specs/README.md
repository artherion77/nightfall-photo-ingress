# design/specs/ — Behavioral Specifications

This folder contains operator-visible behavioral specifications: what each operation
does, what preconditions it requires, what side effects it produces, and what the
registry schema looks like. These are the implementation contracts.

---

## Documents

| File | Status | What it covers |
|---|---|---|
| [registry.md](registry.md) | active | Full SQLite schema DDL for all 8 tables, append-only audit triggers, and registry properties (idempotent, concurrent-safe, resilient, provenance-tracked) |
| [ingest.md](ingest.md) | active | Poll cycle (7-step), metadata pre-filter, authoritative cursor commit rule, sync hash import, Live Photo support |
| [accept.md](accept.md) | active | Accept flow: preconditions, file move from `pending/` to `accepted/`, `accepted_records` write, audit entry |
| [reject.md](reject.md) | active | Reject flow: trash-directory trigger (path unit → service) and CLI `reject` command; idempotency; audit entry |
| [purge.md](purge.md) | active | Purge flow: preconditions (must be `rejected`), root-containment safety check, physical deletion, status transition |
| [triage.md](triage.md) | active | Web API triage write path (`accept`/`reject`/`defer`), idempotency replay (`ui_action_idempotency`), audit-first semantics, and error model |

---

## Configuration Specification

The INI configuration file — all required keys, defaults, validation rules, and section
structure — is documented in the parent folder:

- **[design/cli-config-specification.md](../cli-config-specification.md)**

This document predates the subfolder organisation and is the authoritative config spec.

---

## Reading Order

To understand a complete operator workflow:
1. [ingest.md](ingest.md) — how files arrive
2. [registry.md](registry.md) — how they are tracked
3. [accept.md](accept.md) + [reject.md](reject.md) + [purge.md](purge.md) — what an operator does with them
4. [triage.md](triage.md) — how the web control plane applies triage mutations

## Chunk 4 Testing Note

Chunk 4 triage uses pytest integration tests (API + UI-flow simulation) as the active
test strategy. Playwright coverage for the same flow is deferred.

---

*Parent: [design/README.md](../README.md)*
