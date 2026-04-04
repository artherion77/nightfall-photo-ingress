# Design Constraints and Goals

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §3  
**See also:** [glossary.md](glossary.md), [data-flow.md](../architecture/data-flow.md)

---

## Constraints

- **Fully automated** — no user behavior assumptions on iOS.
- **Robust against Immich changes** — the pipeline operates independently; a fresh Immich DB simply rescans the permanent library.
- **Reject-once, reject-forever** — a rejected SHA-256 is never ingested again regardless of re-uploads.
- **Explicit acceptance** — no automatic transition from unknown to accepted.
- **Accepted-history persistence** — accepted content remains blocked from re-download even after operator relocation.
- **Minimize unnecessary I/O** — metadata pre-filtering avoids downloading files that are already known; HDD is only touched for queue transitions.
- **Legacy-free v2 boundary** — no accepted-first config fallbacks, no silent auto-accept, and no in-place registry upgrade from pre-v2 schemas.
- **English-only** — all inline comments, logs, and documentation are in English.
- **Auditable** — every state transition is recorded in an immutable `audit_log` table.
- **Idempotent** — re-running the pipeline at any point produces the same end state.
- **Idempotent UI writes** — web triage mutation retries must be replay-safe via `X-Idempotency-Key`.

---

## Derived System Invariants

These invariants follow directly from the constraints above and are enforced by the implementation:

| Invariant | Enforcement |
|---|---|
| `config_version = 2` is mandatory | Runtime rejects any other value at startup |
| `pending_path`, `accepted_path`, `rejected_path`, `trash_path` must be distinct | Validated at startup |
| Registry `current_path` outside managed queue roots is an error | Accept/reject flows fail closed |
| No in-place upgrade from pre-v2 registries | Deployments must bootstrap a fresh `registry.db` |
| `audit_log` rows can never be updated or deleted | SQL triggers (`trg_audit_log_no_update`, `trg_audit_log_no_delete`) enforced at DB layer |
| All write paths use `BEGIN IMMEDIATE` transactions | SQLite WAL mode; no partial writes |
| Purge strictly requires prior `rejected` status | `purge` fails on non-rejected files |
| Triage retries do not duplicate state transitions | `ui_action_idempotency` replay in `api/services/triage_service.py` |

## Chunk 4 Note

Web triage writes in Chunk 4 are registry-status transitions only. Physical file move
parity with CLI accept/reject flows remains deferred.

---

*For system-level architecture, see [data-flow.md](../architecture/data-flow.md).*  
*For the full registry schema enforcing these invariants, see [specs/registry.md](../specs/registry.md).*
