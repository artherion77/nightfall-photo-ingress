# Documentation Sufficiency Report

**Type:** Audit  
**Status:** Active  
**Date:** 2026-04-03  
**Author:** Documentation Sufficiency & Drift Audit  
**Scope:** `nightfall-photo-ingress` — full documentation corpus

---

## Purpose and Evaluation Criterion

This report evaluates whether the current documentation corpus is sufficient for a
third-party AI model of Claude Sonnet class or more powerful to reconstruct an
application implementing the same functional behavior as the system, using documentation
alone (no source code).

Evaluation dimensions:

- Lifecycle correctness
- State-machine transitions
- Invariants
- Storage topology
- Operator workflows
- Error handling
- Config semantics
- Accept / reject / purge flows
- Registry behavior
- Ingest behavior
- Safety guarantees
- Edge cases

**Overall verdict:** The documentation corpus is substantively above average for a
project of this scope. Happy-path core ingest, registry schema, operator flows, and
configuration are documented at implementation precision. However, three critical gaps
exist that would independently cause incorrect implementations. Closing all critical and
high-severity gaps would raise the reconstruction fidelity from the current estimate of
~80% to ~95%+.

---

## Section 1 — Subsystem Fidelity Assessments

### 1.1 Core ingest pipeline (poll → hash → registry → pending queue)

**Reconstruction fidelity: ~85%** ✅ Can reconstruct with minor gaps

The poll cycle (§6.1 of domain-architecture-overview.md), cursor commit model (§6.1.1),
metadata prefilter, staging temp-file naming convention, registry lookup, and all four
status-handling branches (`rejected_duplicate`, `discard_pending`, `duplicate_skipped`,
`pending` insert) are documented with sufficient precision to re-implement correctly.

**Gaps:**

| Gap | Severity |
|---|---|
| Cross-pool move decision algorithm (rename vs. copy-verify-unlink based on filesystem topology) is mentioned but the algorithm is not documented | High |
| JSONL journal line format: `IngestOperationJournal` is documented at the concept level (4 phases) but no field schema or line format is specified | High |

---

### 1.2 State machine

**Reconstruction fidelity: ~70%** ⚠️ Critical gap

The four `files.status` values are documented. Individual transitions are described
across their respective flow sections. However there is no consolidated state machine
diagram or transition table, and several transitions are only discoverable through the
verification checklist rather than specification sections.

**Documented transitions:**

| Transition | Documented in |
|---|---|
| unknown → pending (ingest) | §6.1 pipeline behavior |
| pending → accepted (explicit accept) | §6.5 accept flow |
| pending → rejected (CLI reject) | §6.4 CLI reject |
| accepted → rejected (via trash) | §12 verification checklist item 6 only |
| rejected → purged (explicit purge) | §6.5 purge flow |

**Gaps — undocumented behavior:**

| Gap | Severity |
|---|---|
| No consolidated state transition diagram or table | Critical |
| `accepted → rejected` via trash is only documented in the verification checklist, not in the rejection flow specification | High |
| Whether `purged` is a terminal state is never explicitly declared — only implied | High |
| Whether `accepted` files can be purged directly (skipping rejected) is not specified | High |
| Whether `rejected → accepted` is possible or prohibited is not specified | High |
| `live_photo_pairs.status` lifecycle: when do pair records transition states? Are pair transitions atomic with their component file transitions? What happens when only one component is rejected? | Critical |

---

### 1.3 Registry schema and semantics

**Reconstruction fidelity: ~90%** ✅ Can reconstruct

The full DDL for all 8 tables is present with constraints, triggers, and foreign keys.
Properties (idempotency, WAL mode, `BEGIN IMMEDIATE` transaction pattern, append-only
`audit_log`, `accepted_records` semantics) are documented.

**Gaps:**

| Gap | Severity |
|---|---|
| `initialize()` behavior on an existing schema v2 database is not documented: is it idempotent? does it check schema version? does it apply additive migrations automatically? | High |
| No documentation for the `migrations/` scaffold that exists in the source tree — no migration manifest, no schema version tracking mechanism, no migration record format | Critical |

---

### 1.4 Accept / reject / purge flows

**Reconstruction fidelity: ~90%** ✅ Can reconstruct the happy path

Each flow is documented with: preconditions, file move operation, registry transition,
audit_log append, and CLI invocation form. Idempotency on reject is documented.

**Gaps:**

| Gap | Severity |
|---|---|
| Purge when the file in `rejected/` has already been deleted by an operator: missing-file behavior not specified | Medium |
| Reject via trash when two files share the same SHA-256: which one wins? | Medium |
| Storage template token rendering (`{yyyy}`, `{mm}`, `{original}`, `{sha8}`) listed but the collision-safe suffixing algorithm is described only as "preserves uniqueness" with no specification of how | High |

---

### 1.5 Configuration

**Reconstruction fidelity: ~95%** ✅ Can reconstruct fully

`design/cli-config-specification.md` is the most complete individual document in the
corpus. All keys, types, defaults, constraints, and validation rules are present.

**Gap:**

| Gap | Severity |
|---|---|
| Behavior when a required config key is absent at startup (error message format, exit code, which keys are fatal vs. default-able) is not documented | Medium |

---

### 1.6 Authentication

**Reconstruction fidelity: ~90%** ✅ Can reconstruct

Device-code flow, MSAL usage, token cache serialization, per-account isolation,
`cache_lock.py` per-account singleton, and auth failure threshold behavior are all
documented. Design rationale is covered in `design/auth-design.md` and the ADL.

**Gap:**

| Gap | Severity |
|---|---|
| Behavior when the token cache file is present but corrupted (invalid JSON, wrong format, truncated): silent fallback vs. raised error vs. re-prompt is not specified | Low |

---

### 1.7 Error handling and resilience

**Reconstruction fidelity: ~85%** ✅ Can reconstruct the documented error paths

`design/error-taxonomy-and-resilience.md` is thorough. Exception hierarchy, retry policy,
URL/token redaction rules, delta resync on HTTP 410, auth resilience threshold, and
throughput bounds are documented at implementation precision.

**Gaps:**

| Gap | Severity |
|---|---|
| Disk full detection: `disk_full` is a documented status state but no documentation describes when or how it is detected, what threshold triggers it, or what the response behavior is | Medium |
| SQLite lock contention: if `registry.db` cannot be opened for writing despite the process lock being held, behavior is not documented | Medium |
| Trash service crash mid-processing: the `.path` unit fires again on the next filesystem change — whether this replay is safe (idempotency guarantee for `nightfall-photo-ingress-trash.service`) is not documented | Medium |

---

### 1.8 Sync import / external hash cache

**Reconstruction fidelity: ~65%** ⚠️ Documented drift present

The advisory SHA1 import mechanism is described (§6.3, §14 of domain-architecture-overview.md).
The `external_hash_cache` schema is present and accurate.

**Documented drift (Critical):**

The narrative in `design/domain-architecture-overview.md §6.3` describes the sync-import
→ download-avoidance optimization pipeline as if it is a working feature. However,
`audit/follow-up/module6-external-library-download-avoidance-open-point.md` explicitly
states the runtime optimization layer **is intentionally not implemented** and the
advisory hash has not been connected to the prefilter pipeline.

A reader of the main design document alone would conclude this feature is live. A
re-implementer would implement it. Both conclusions are incorrect.

**Additional gaps:**

| Gap | Severity |
|---|---|
| §6.3 narrative implies download-avoidance is implemented; open-point document says it is not | High (drift) |
| The end-to-end flow from `sync-import` → `external_hash_cache` → prefilter decision is only partially specifiable from documentation because the connection point is explicitly absent | High |

---

### 1.9 Live Photo pairing

**Reconstruction fidelity: ~50%** ⚠️ Critical gap in lifecycle specification

Pairing heuristics (`live_photo_capture_tolerance_seconds`, `live_photo_stem_mode`,
`live_photo_component_order`, `live_photo_conflict_policy`) and their current validated
defaults are documented. The `live_photo_pairs` schema is present.

**Gaps:**

| Gap | Severity |
|---|---|
| `live_photo_pairs.status` lifecycle: when do pair records transition? | Critical |
| Are pair status transitions atomic with corresponding individual `files.status` transitions? | Critical |
| What happens to the pair record when only one component is rejected (not the other)? | Critical |
| What does `paired` mean in terms of operator workflow? Is a paired item treated as a single review unit or as two independent files? | High |
| At what point does a `live_photo_pairs` row get created — during ingest if a pairing candidate is identified, or after both files are confirmed present? | High |

---

### 1.10 Observability

**Reconstruction fidelity: ~85%** ✅ Can reconstruct the main surface

Structured log format, run-ID propagation, diagnostic counter set, status snapshot field
contract, and state values are documented.

**Gaps:**

| Gap | Severity |
|---|---|
| JSONL journal line format is not specified (field names, field types, which fields appear in each phase record) | High |
| No documented procedure for using `run_id` to correlate status snapshot + journal log lines + audit rows across a single poll cycle | Low |

---

### 1.11 Deployment and operations

**Reconstruction fidelity: ~70%** ⚠️ Multiple gaps in post-install procedures

Install script, LXC container model, systemd unit configuration, and working-state path
distinction (`/var/lib/ingress/` inside container vs. `/mnt/ssd/photo-ingress/` on host)
are all documented.

**Gaps:**

| Gap | Severity |
|---|---|
| No versioning policy — how releases are cut, how `__version__` is bumped, what constitutes a breaking change | Medium |
| No upgrade procedure — how to upgrade from one installed version to the next without losing registry state | Medium |
| No rollback procedure for production deployments | Medium |
| No backup/restore procedure for `registry.db` | Medium |
| No maintenance procedures (DB vacuum, ZFS snapshot cadence for registry, staging cleanup, log rotation) | Medium |
| LXC bind-mount configuration and profile requirements are not documented (what LXD profiles are needed, what idmap is required for file ownership) | Medium |
| ZFS dataset creation is listed as a "manual pre-requisite" but the exact LXC bind-mount configuration needed to expose those datasets to the container is not documented | Medium |

---

### 1.12 Schema migrations

**Reconstruction fidelity: 0%** ❌ Cannot reconstruct — no documentation

The source tree contains a `domain/migrations/` directory scaffold, but nothing in the
documentation corpus describes the migration mechanism.

**Gaps:**

| Gap | Severity |
|---|---|
| No documentation of the migration mechanism — does `initialize()` auto-apply migrations? | Critical |
| How the current schema version is tracked (schema_version table, PRAGMA user_version, or other mechanism) is not documented | Critical |
| What a migration record looks like (naming convention, content format, execution order) is not documented | Critical |
| What happens if a migration partially applies before a crash is not documented | Critical |
| The only migration-related policy statement in the corpus is that v2.0 does not upgrade pre-v2 schemas in place — nothing about future v2.x → v2.y migrations | Critical |

---

### 1.13 Security / threat model

**Reconstruction fidelity: ~20% (implementation details only)** ❌ No threat model

`audit/security-threat-model.md` is empty (0 bytes) and was incorrectly named (missing `.md`
extension, filename contained "thread" instead of "threat"; renamed as part of housekeeping). Token cache mode `0600` and URL redaction rules are documented as
implementation details, but these are not a threat model.

**Gaps:**

| Gap | Severity |
|---|---|
| No threat model document — no trust boundaries, threat actors, attack surface, mitigations by threat category, or security requirements | High |
| Staging permissions open-point documents an unresolved `0777` security hole in staging directories (world-writable evidence/log paths) with no documented remediation timeline | High |
| No documentation of the security model for the web control plane bearer token (planned feature) | Medium |
| `audit/security-threat-model.md` is empty — presents an audit gap as if it were a present document (was previously misnamed; renamed as housekeeping) | High |

---

### 1.14 Web control plane (API + UI)

**Reconstruction fidelity: ~85% (for planned, unimplemented work)**

The five web control plane design documents (~2,800 lines) are the best-documented
unimplemented subsystem in the corpus. Phase 1 API endpoints, SvelteKit SPA architecture,
component hierarchy, state management patterns, bearer auth model, Phase 2 background
worker, and Phase 3 policy automation engine are all specified.

**Note:** These documents are for planned work. No `api/` or `webui/` directories exist
yet. Implementation has not begun.

**Gap:** The proposed target folder structure has no web/API documentation category.
These five documents would need to be discarded or misplaced if the proposed structure
were adopted without amendment.

---

## Section 2 — Master Gap Table

| # | Gap description | Severity | Subsystem |
|---|---|---|---|
| G-01 | No formal state machine diagram or transition table for `files.status` | **Critical** | State machine |
| G-02 | `live_photo_pairs.status` lifecycle entirely undocumented | **Critical** | Live Photo |
| G-03 | Migration mechanism not documented — schema versioning, migration execution, crash safety | **Critical** | Migrations |
| G-04 | Sync-import §6.3 narrative implies download-avoidance works; open-point says it is not implemented — documented drift | **High** | Sync import / Drift |
| G-05 | `audit/security-threat-model.md` is empty (and misnamed) | **High** | Security |
| G-06 | No threat model document | **High** | Security |
| G-07 | Live Photo pair lifecycle: atomicity of pair transitions with file transitions; single-component-rejected behavior | **High** | Live Photo |
| G-08 | `initialize()` behavior on existing schema v2 database is not documented | **High** | Registry |
| G-09 | JSONL journal line format not specified (field names, types, per-phase fields) | **High** | Observability |
| G-10 | Storage template collision-safe suffixing algorithm not specified | **High** | Specs |
| G-11 | Cross-pool move decision algorithm (rename vs copy-verify-unlink) not documented | **High** | Ingest |
| G-12 | `accepted → rejected` transition via trash documented only in verification checklist, not in rejection flow spec | **High** | State machine |
| G-13 | `purged` terminal-state guarantee never explicitly stated; direct accepted → purge and rejected → accepted paths unspecified | **High** | State machine |
| G-14 | No domain glossary (candidate, handoff, queue artifact, advisory match, paired, deferred) | **High** | Domain |
| G-15 | Staging permissions 0777 open point — unresolved security gap with no documented remediation timeline | **High** | Security |
| G-16 | No versioning/release policy | **Medium** | Deployment |
| G-17 | No upgrade procedure (version N → N+1) | **Medium** | Deployment |
| G-18 | No rollback procedure for production | **Medium** | Deployment |
| G-19 | No backup/restore procedure for `registry.db` | **Medium** | Deployment |
| G-20 | No maintenance procedures (DB vacuum, ZFS snapshots, staging cleanup, log rotation) | **Medium** | Deployment |
| G-21 | Disk full detection: threshold and response behavior not documented | **Medium** | Error model |
| G-22 | `registry.db` lock timeout / contention behavior not documented | **Medium** | Error model |
| G-23 | Trash service idempotency guarantee (replay on `.path` re-fire) not documented | **Medium** | Specs |
| G-24 | Purge with missing `rejected/` file: missing-file behavior not documented | **Medium** | Specs |
| G-25 | Startup behavior when required config key is absent (exit code, error format) | **Medium** | Config |
| G-26 | LXC bind-mount configuration and LXD profile requirements not documented | **Medium** | Deployment |
| G-27 | `audit/drift-analysis.md` and `audit/review-history.md` are empty stubs | **Medium** | Audit |
| G-28 | No consolidated invariants document | **Medium** | Architecture |
| G-29 | Auth token cache corruption behavior not documented | **Low** | Auth |
| G-30 | No `run_id` cross-surface correlation procedure | **Low** | Observability |

---

## Section 3 — Severity Distribution

| Severity | Count | % of gaps |
|---|---|---|
| Critical | 3 | 10% |
| High | 12 | 40% |
| Medium | 13 | 43% |
| Low | 2 | 7% |
| **Total** | **30** | |

---

## Section 4 — Prioritized Recommendations

### Tier 1 — Fix immediately (Critical gaps; block correct implementation)

**R-01: Author `design/architecture/state-machine.md`**  
Produce a consolidated state machine specification: all valid `files.status` values, all
legal transitions with preconditions, all explicitly prohibited transitions, and terminal
state declarations. Include a transition diagram. Close G-01, G-12, G-13.  
Estimated scope: 1 document, 100–200 lines.

**R-02: Author `design/specs/live-photo-lifecycle.md`**  
Specify `live_photo_pairs.status` transitions, atomicity guarantees with individual file
transitions, single-component-rejected behavior, and the operator workflow for paired
items (single review unit vs. independent). Close G-02, G-07.  
Estimated scope: 1 document, 80–150 lines.

**R-03: Author `migrations/` documentation**  
Document the schema migration mechanism: how `initialize()` behaves on an existing
database, how the current schema version is tracked, migration record naming and format,
execution order, crash safety guarantees, and the v2.x → v2.y migration policy. Close
G-03, G-08.  
Estimated scope: 2–3 documents (`schema-v2.md`, `upgrade-guide.md`), 100–200 lines each.

---

### Tier 2 — Fix in current release cycle (High severity; cause significant drift or incompleteness)

**R-04: Correct documented drift in §6.3 sync-import narrative**  
Add a clear annotation to `design/domain-architecture-overview.md §6.3` stating that the
download-avoidance optimization is not yet implemented and cross-referencing
`audit/follow-up/module6-external-library-download-avoidance-open-point.md`. Close G-04.  
Estimated scope: 3–5 lines added to existing doc.

**R-05: Author `audit/security-threat-model.md`**  
Document trust boundaries, threat actors, attack surface analysis, mitigations by
threat category, and security requirements. Rename and replace the empty misnamed stub.
Close G-05, G-06.  
Estimated scope: 1 document, 150–300 lines.

**R-06: Document `initialize()` idempotency contract**  
Add a subsection to `design/specs/registry.md` (or §5 of domain-overview) specifying
exact `initialize()` behavior on an existing schema v2 database. Close G-08.  
Estimated scope: 10–20 lines added to existing doc.

**R-07: Specify JSONL journal line format**  
Add a field schema table and per-phase field map to `design/ingest-lifecycle-and-crash-recovery.md`
(or the IngestOperationJournal section of domain-overview). Close G-09.  
Estimated scope: 20–40 lines added to existing doc.

**R-08: Specify storage template token rendering and collision-safe suffixing**  
Add a formal spec of the collision-safe suffixing algorithm to `design/cli-config-specification.md`.
Close G-10.  
Estimated scope: 20–40 lines added to existing doc.

**R-09: Document cross-pool move decision algorithm**  
Add a decision table or prose specification describing how the system chooses between
rename vs. copy-verify-unlink based on filesystem topology. Close G-11.  
Estimated scope: 15–25 lines added to domain-overview §6 or a new ingest.md spec.

**R-10: Author `design/domain/glossary.md`**  
Define all domain terms: candidate, handoff, queue artifact, advisory match, paired,
deferred, permanent library, registry, cursor, staging, poll cycle. Close G-14.  
Estimated scope: 1 document, 60–120 lines.

**R-11: Author or close staging permissions open point**  
Either document the remediation plan and timeline for the 0777 staging directory issue,
or document an accepted risk decision with owner and review date. Close G-15.  
Estimated scope: update to existing open-point document.

---

### Tier 3 — Address in next planning cycle (Medium severity; gaps in operator completeness)

**R-12: Author `docs/deployment/versioning-policy.md`** — Close G-16, G-17, G-18.  
**R-13: Author `docs/operator/maintenance.md`** — Close G-19, G-20.  
**R-14: Document disk full detection threshold and response** — Close G-21.  
**R-15: Document SQLite lock contention behavior** — Close G-22.  
**R-16: Document trash service idempotency guarantee** — Close G-23.  
**R-17: Document purge missing-file behavior** — Close G-24.  
**R-18: Document startup error format for missing config keys** — Close G-25.  
**R-19: Document LXC bind-mount configuration** — Close G-26.  
**R-20: Author `audit/drift-analysis.md` and `audit/review-history.md`** — Close G-27.  
**R-21: Author `design/architecture/invariants.md`** — Close G-28.  

---

### Tier 4 — Low priority

**R-22: Document auth token cache corruption behavior** — Close G-29.  
**R-23: Document `run_id` cross-surface correlation procedure** — Close G-30.  

---

## Section 5 — Housekeeping Actions (No content work required)

These are structural or naming corrections that do not require new content:

| Action | Closes |
|---|---|
| Rename old misnamed security file → `audit/security-threat-model.md` ✅ done | G-05 (partial) |
| Rename old misnamed open-points dir → `audit/follow-up/` ✅ done | Structural defect |
| Update all cross-references to `audit/follow-up/` after rename ✅ done | Consistency |

---

## Revision History

| Date | Change |
|---|---|
| 2026-04-03 | Initial report — full corpus audit, 30 gaps identified, 23 recommendations |
