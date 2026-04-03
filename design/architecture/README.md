# design/architecture/ — Architectural Specifications

This folder contains system-level architectural documents: how the major subsystems
are structured, how they behave at runtime, and what invariants they must maintain.

For the ingest lifecycle, two files cover different levels of detail: [lifecycle.md](lifecycle.md)
is a concise overview; [ingest-lifecycle-and-crash-recovery.md](ingest-lifecycle-and-crash-recovery.md)
is the complete specification. All other topics are covered by a single file.

---

## Documents

| File | Status | What it covers |
|---|---|---|
| [data-flow.md](data-flow.md) | active | High-level pipeline diagram from iOS → OneDrive → staging → queue; stage-by-stage descriptions |
| [environment-separation-and-container-lifecycle.md](environment-separation-and-container-lifecycle.md) | proposed | Development vs staging vs production container boundaries, lifecycle contracts, and migration plan (`dev-photo-ingress`) |
| [error-taxonomy-and-resilience.md](error-taxonomy-and-resilience.md) | active | Exception hierarchy, `as_log_dict()` contract, URL/token redaction policy, retry backoff, auth resilience, delta resync circuit-breakers, throughput bounds, edge case mitigations |
| [invariants.md](invariants.md) | active | Catalogue of 28 system invariants grouped by category (registry, storage, staging, audit log, configuration, process model); each with enforcement mechanism and source citation |
| [ingest-lifecycle-and-crash-recovery.md](ingest-lifecycle-and-crash-recovery.md) | active | **Full spec:** complete IngestOperationJournal JSONL format, phase sequence, recovery action detail, StagingDriftReport classification, zero-byte policy |
| [lifecycle.md](lifecycle.md) | active — overview | Poll cycle, authoritative cursor commit rule, IngestOperationJournal overview, crash recovery summary |
| [live-photo-pair-lifecycle.md](live-photo-pair-lifecycle.md) | active | Live Photo pair state machine: five-state lifecycle for `live_photo_pairs.status`, pairing heuristics, and component-level interaction |
| [observability.md](observability.md) | active | Logging modes, JSON log field schema and example, Run-ID propagation, diagnostic counters, safe logging (`sanitize_extra`, `_RedactingFormatter`), status snapshot writer, human-mode interactive output, transport debug logging |
| [schema-and-migrations.md](schema-and-migrations.md) | active | SQLite schema v2 bootstrap, migration framework scaffold, schema versioning policy |
| [state-machine.md](state-machine.md) | active | `files.status` state machine: all valid transitions, guard conditions, side effects (registry writes and physical file moves), and guard-failure errors |
| [storage-topology.md](storage-topology.md) | active | ZFS dataset layout (ssdpool and nightfall pool), mount points, pool rationale, pre-requisite creation commands |

---

## Reading Order

For a first read, start with the overview sequence:
1. [data-flow.md](data-flow.md) — understand the end-to-end pipeline
2. [state-machine.md](state-machine.md) — understand the file lifecycle
3. [lifecycle.md](lifecycle.md) — understand poll cycle and crash safety
4. [invariants.md](invariants.md) — understand system guarantees

For implementation or debugging:
- Environment boundaries: [environment-separation-and-container-lifecycle.md](environment-separation-and-container-lifecycle.md)
- Error handling: [error-taxonomy-and-resilience.md](error-taxonomy-and-resilience.md)
- Crash recovery: [lifecycle.md](lifecycle.md) → [ingest-lifecycle-and-crash-recovery.md](ingest-lifecycle-and-crash-recovery.md)
- Observability: [observability.md](observability.md)

---

*Parent: [design/README.md](../README.md)*
