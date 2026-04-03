# Documentation Reconciliation & Reverse-Engineering Execution Plan

**Status:** active — awaiting chunk-by-chunk steering  
**Created:** 2026-04-03  
**Owner:** ops/copilot  
**Mode:** Documentation Reconciliation & Reverse-Engineering

---

## Overview

This plan drives a systematic drift-elimination pass across all three documentation
layers of the `nightfall-photo-ingress` project:

| Layer | Path | Role |
|-------|------|------|
| Design | `/design/` | Authoritative architecture — treated as the backbone |
| Planning | `/planning/` | Implementation status and future work inventory |
| Operator docs | `/docs/` | Runtime, install, and operational guidance |

The work is chunked into self-contained phases that can be executed one at a time and
reviewed before proceeding. Each chunk ends with an explicit stopping point.

---

## Pre-Work: Key Findings from Initial Survey

The initial survey (2026-04-03) identifies the following categories of drift before
any work begins. These are the inputs that each phase corrects.

### F1 — CLI and systemd naming drift (critical)

The design document (`design/domain-architecture-overview.md` §1.1) states:

- CLI command: `photo-ingress`
- systemd units: `photo-ingress-poll.*`, `photo-ingress-trash.*`

The actual implementation and operator docs use:

- CLI command: `nightfall-photo-ingress` (from `pyproject.toml` console_scripts entry)
- systemd units: `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`,
  `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service`
- `docs/operations-runbook.md` already uses the correct `nightfall-photo-ingress` names

The naming matrix in the design doc must be updated to reflect the implemented names.
A decision record explaining the `nightfall-` prefix retention policy must be added.

### F2 — domain-architecture-overview.md is partially stale

`design/domain-architecture-overview.md` still carries:

- `Status: DRAFT — pending review` (never promoted to `active`)
- Date: `2026-03-31` (accurate but needs an updated-at field)
- **Section 9 (File Layout):** shows the old monolithic package layout
  (`nightfall_photo_ingress/onedrive/`, `nightfall_photo_ingress/pipeline/`)
  rather than the refactored `domain/`, `adapters/`, `runtime/` structure
- **Section 10 (Implementation Phases):** phases 1–7 were fully delivered but
  the text reads as a forward plan, not a delivered record
- **Section 11 (Configuration):** shows the old single-account INI format rather
  than the current `[core]` + `[account.<name>]` multi-account format
- **Section 5 (Schema):** missing `live_photo_pairs`, `file_origins`, and
  `blocked_rules` tables that exist in the schema
- No coverage of: IngestOperationJournal, StagingDriftReport, zero-byte quarantine
  policy, throughput backpressure controls, delta circuit-breaker, auth resilience
  threshold, per-account singleton lock, safe-logging redaction, run-ID tracing

### F3 — ARCHITECTURE.md root references a non-existent file

`ARCHITECTURE.md` (root) references:

```
design/web-control-plane-architecture-extension.md
planning/web-control-plane-implementation-roadmap.md
```

Neither file exists under those paths. The correct paths are:
- `design/web-control-plane-architecture-phase2.md` (and phase3)
- `planning/planned/web-control-plane-integration-plan.md`

### F4 — Planning: Gate status for post-audit next steps is unknown

`planning/planned/cli-domain-post-audit-next-steps.md` defines Gates 1, 2, 3 as
checkboxes. It is unclear which gate tasks are complete. The review artifacts in
`review/` suggest significant work was done on Module 3 and Module 4 hardening, but
the gate checkboxes have not been updated.

### F5 — Planning: Modules 5–8 not yet started (confirmed)

From `planning/implemented/cli-domain-iterative-implementation-roadmap.md`: Modules 0–4
are complete; Modules 5–8 remain planned. No implementation exists for:

- Module 5: Trash watch systemd integration + `process-trash` flow (partially in reject.py
  but systemd integration is not confirmed started)
- Module 6: Observability hardening / status file for all commands
- Module 7: Sync hash import expanded validation pass
- Module 8: Package + installer hardening to production-grade

> Note: Core trash, process-trash, accept, reject, purge, and status file/export
> code is present in the implementation. The gap is in the production-grade systemd
> path unit integration and end-to-end staging smoke validation.

### F6 — Design: three large undocumented subsystems

The following implemented components have no dedicated design coverage in `/design/`:

1. **Ingest lifecycle journal** (`domain/journal.py`) — append-only JSONL crash-recovery
   log separate from the SQLite audit_log; supports phase-tagged replay
2. **Error taxonomy and resilience** (`adapters/onedrive/errors.py`, `retry.py`,
   `adapters/onedrive/auth.py`) — structured error hierarchy, URL-redacting raise sites,
   exponential backoff with rate-limit-aware retry, consecutive-auth-failure threshold
3. **Observability internals** (`adapters/onedrive/safe_logging.py`, `status.py`,
   diagnostic counters in `client.py`) — run-ID threading, structured JSON logging,
   diagnostic counter export, atomic status snap

### F7 — docs/app-registration-design.md is misclassified

`docs/app-registration-design.md` contains a mix of:
- Design-level content (auth design principles, error handling improvements, scope
  normalization) — belongs in `/design/`
- Operator content (how to register the app, config-check steps) — belongs in `/docs/`

This file should be split: design portion moves to `/design/`, operator portion stays
in `/docs/` and is integrated into the runbook or a dedicated operator guide.

### F8 — Operator docs missing several workflows

`docs/operations-runbook.md` covers install, systemd, status, and app registration.
It does not cover:

- `accept` / `reject` / `purge` CLI workflows with examples
- `process-trash` workflow
- `config-check` command usage
- `sync-import` command usage and behaviour
- Staging reconciliation / recovery from a crashed poll
- Status file interpretation guide (what each `state` value means operationally)
- Common troubleshooting scenarios

---

## Phase 1 — Design Layer: domain-architecture-overview.md

**Scope:** Update, complete, and promote the main architecture document.

**Priority:** Highest — all other design work references this document.

### Chunk 1.1 — Promote status and fix naming matrix

Affected file: `design/domain-architecture-overview.md`

Tasks:
- [x] Change `Status: DRAFT — pending review` → `Status: active`
- [x] Add `Updated: 2026-04-03` field
- [x] In Section 1.1 (Naming Matrix), update:
  - CLI command: `photo-ingress` → `nightfall-photo-ingress`
  - systemd units: `photo-ingress-poll.*` / `photo-ingress-trash.*` →
    `nightfall-photo-ingress.service`, `nightfall-photo-ingress.timer`,
    `nightfall-photo-ingress-trash.path`, `nightfall-photo-ingress-trash.service`

### Chunk 1.2 — Update Section 5 (Registry Schema)

Tasks:
- [x] Add `file_origins` table (account-to-file provenance mapping)
- [x] Add `live_photo_pairs` table (pair_id, account, stem, photo_sha256,
  video_sha256, status, created_at, updated_at)
- [x] Add `blocked_rules` table (for future web control plane blocklist API)
- [x] Correct any field names that differ from the actual schema in `domain/registry.py`

### Chunk 1.3 — Update Section 9 (File Layout)

Tasks:
- [x] Replace old monolithic layout (with `onedrive/` and `pipeline/` subdirs) with
  the actual `domain/`, `adapters/onedrive/`, `runtime/` refactored layout
- [x] Ensure all files listed in the layout exist in `src/nightfall_photo_ingress/`

### Chunk 1.4 — Update Section 11 (Configuration) and Section 6 (Pipeline)

Tasks:
- [x] Replace the old single-account config example (with `[onedrive]` + `[paths]`
  + `[polling]` + `[alerts]` sections) with the current `[core]` + `[account.<name>]`
  format — reference `design/cli-config-specification.md` for the canonical spec
- [x] In Section 6.1 (Poll Cycle), adjust step c1 to reference the journal append
  step and the M3→M4 `DownloadedHandoffCandidate` contract
- [x] In Section 6.4 (Rejection Flow), verify the trash flow description reflects
  the actual `reject.py` implementation

### Chunk 1.5 — Update Section 10 (Implementation Phases) and add new subsections

Tasks:
- [x] Reframe Section 10 from forward plan to delivery record: mark phases 1–7 as
  delivered (brief one-liner each); retain as historical record but mark clearly
- [x] Add Section 12: Ingest Lifecycle Journal — brief architecture-level description
  of the JSONL journal, its role in crash recovery, and relationship to the SQLite
  audit_log
- [x] Add Section 13: Error Taxonomy and Resilience — structured error hierarchy,
  retry policy, consecutive auth-failure alerting threshold, circuit-breaker behavior
  at delta-resync boundaries
- [x] Add Section 14: Observability Internals — run-ID threading, diagnostic counter
  keys, safe-logging redaction rules, status snapshot contract

---

## Phase 2 — Design Layer: architecture-decision-log.md

**Scope:** Add missing decision records for implemented behaviors.

### Chunk 2.1 — Add naming finalization decision

Tasks:
- [x] Add `DEC-20260403-01`: CLI and systemd unit naming finalization
  - Decision: retain `nightfall-` prefix for CLI (`nightfall-photo-ingress`) and
    systemd units; `photo-ingress` used for config paths and service-level naming
  - Rationale: consistency with other nightfall tooling; `nightfall-` prefix in PATH
    avoids collision with non-nightfall packages
  - References: `pyproject.toml`, `systemd/nightfall-photo-ingress.service`

### Chunk 2.2 — Add domain/adapters/runtime architecture decision

Tasks:
- [x] Add `DEC-20260403-02`: Domain/adapters/runtime module separation
  - Decision: refactor from monolithic layout to a three-layer separation
  - Rationale: allows future source adapters without touching domain core
  - References: `src/nightfall_photo_ingress/`, `ARCHITECTURE.md`

### Chunk 2.3 — Add crash-recovery journal decision

Tasks:
- [x] Add `DEC-20260403-03`: Append-only JSONL lifecycle journal for crash recovery
  - Decision: maintain a separate JSONL journal alongside the SQLite audit_log
  - Rationale: provides phase-tagged operation recovery without locking the DB;
    SQLite audit_log remains authoritative for state; journal is for crash-boundary
    idempotency replay
  - References: `src/nightfall_photo_ingress/domain/journal.py`

### Chunk 2.4 — Add safe-logging and singleton lock decisions

Tasks:
- [x] Add `DEC-20260403-04`: URL/token redaction at all raise sites
  - Decision: all exception raise sites in the adapter use `redact_url()`; no
    pre-authenticated URLs appear in logs or tracebacks
  - Rationale: pre-authenticated OneDrive download URLs carry bearer material in
    query strings; logs must never capture them
- [x] Add `DEC-20260403-05`: Per-account singleton lock for concurrent poll safety
  - Decision: `account_singleton_lock` in `cache_lock.py` prevents two concurrent
    polls from touching the same account's MSAL token cache
  - Rationale: MSAL token cache is not safe for concurrent writers; the global
    process lock covers single-process concurrency but not multi-process edge cases

---

## Phase 3 — Design Layer: New Documents

**Scope:** Create three new focused design documents for undocumented subsystems.

Each document should be architecture-level: no code copies, describes behavior,
invariants, and failure modes in structured prose.

### Chunk 3.1 — design/ingest-lifecycle-and-crash-recovery.md

Topics to cover:
- Role of the IngestOperationJournal (JSONL, phase-tagged, append-only, max_bytes rotation)
- Phase sequence: `download_started` → `download_complete` → `hash_computed` →
  `decision_applied` → `finalized`
- Crash recovery: which phases are safe to replay vs which require staging cleanup
- StagingDriftReport: stale_temp, completed_unpersisted, orphan_unknown,
  quarantined classifications and their remediation paths
- Zero-byte file policy: quarantine (not silent discard) with audit record
- Relationship with SQLite audit_log: journal is ephemeral crash boundary; audit_log
  is permanent state history

### Chunk 3.2 — design/error-taxonomy-and-resilience.md

Topics to cover:
- Structured error hierarchy: `AuthError`, `GraphError`, `DownloadError`,
  `GraphResyncRequired` and their loggable fields
- URL/token redaction policy: which query parameters are redacted, the `redact_url()`
  contract, sentinel values for unparseable URLs
- Retry policy: `RetryPolicy` dataclass fields, retryable status codes, `Retry-After`
  header parsing, exponential backoff formula
- Delta resync: `GraphResyncRequired` triggers cursor reset and full delta restart;
  resync count is tracked as a diagnostic counter
- Auth resilience: consecutive failure threshold (`≥3` auth failures triggers alert
  email); diagnostic counters: `auth_refresh_attempt_total`,
  `auth_refresh_success_total`, `auth_refresh_failure_total`
- Throughput controls: `max_downloads_per_poll` and `max_poll_runtime_seconds` -
  when either limit is hit, the current page is committed and the poll terminates
  cleanly (not aborted)

### Chunk 3.3 — design/observability.md

Topics to cover:
- Structured JSON log format: fields `ts`, `level`, `component`, `msg`, plus
  context fields (`sha256`, `filename`, `status`, `run_id`, `account`)
- Run-ID: UUID generated once per poll run, propagated to all log entries and
  audit_log rows for cross-surface correlation
- Diagnostic counter model: `_EXPORTED_DIAGNOSTIC_KEYS` set in `client.py`;
  counters are accumulated per poll run and emitted in structured logs and
  status snapshot details
- Safe-logging: `sanitize_extra()` strips fields whose names match credential
  patterns before they reach the logging system; never raises
- Status snapshot contract:
  - Path: `/run/nightfall-status.d/photo-ingress.json`
  - Written atomically (tmp then rename)
  - Fields: `schema_version`, `service`, `version`, `host`, `state`, `success`,
    `command`, `updated_at`, `details`
  - State values: `healthy`, `degraded`, `auth_failed`, `disk_full`,
    `ingest_error`, `registry_corrupt`
- Human-mode vs JSON-mode logging selection (CLI `--log-mode` flag)

---

## Phase 4 — Planning Layer Audit

**Scope:** Reconcile all `/planning/` documents with reality.

### Chunk 4.1 — cli-domain-post-audit-next-steps.md: gate status

Tasks:
- [x] Read `audit/archive/module3-module4-integration-suite-compliance-audit-final.md`
  and `audit/archive/module4-cross-module-state-machine-operator-readiness-final.md`
- [x] For each checkbox in Gates 1, 2, 3: determine actual status (done / partial /
  still open)
- [x] Update checkboxes or add a status summary block at the top of the document
- [ ] If all three gates are passed, move this doc to `planning/implemented/` (Gates 1–3 remain open)

### Chunk 4.2 — cli-domain-iterative-implementation-roadmap.md: Modules 5–8

Tasks:
- [x] Review what is actually implemented for Modules 5, 6, 7, 8 vs what the roadmap
  describes (core trash/reject/accept/purge is present; production systemd
  path-unit smoke test may not be)
- [x] Update implementation status checkboxes for any steps that are complete
- [x] Add a note for what remains for each module before it can be marked complete

### Chunk 4.3 — Web control plane planning docs: status and coherence

Files to review:
- `planning/planned/web-control-plane-integration-plan.md`
- `planning/planned/web-control-plane-phase1-scope.md`
- `planning/planned/web-control-plane-project-structure.md`
- `planning/planned/web-control-plane-techstack-decision.md`
- `planning/proposed/web-control-plane-phase2-implementation-roadmap.md`

Tasks:
- [x] Confirm Phase 0 of the web control plane has not been started (no `api/` or
  `webui/` directories exist in the repo)
- [x] Verify cross-references between these documents are consistent and alive
- [x] Confirm the Phase 1 re-evaluation decisions in `web-control-plane-phase1-scope.md`
  are reflected in `webui-architecture-phase1.md` and `web-control-plane-integration-plan.md`
- [x] Add a status header block to `web-control-plane-integration-plan.md` that
  clearly states "Phase 0 not yet started as of 2026-04-03"

### Chunk 4.4 — cli-v2-deferred-backlog.md: staleness check

Tasks:
- [x] Review §7.3 (Identity provider abstraction) — this is referenced in the
  design decision log as a future option; confirm it remains deferred
- [x] Review §7.1 (MCP exposure) — nightfall-mcp exists as a separate project;
  confirm this item is still valid and note the relationship
- [x] If any items have been silently implemented, move them out of this doc

---

## Phase 5 — Operator Docs Layer

**Scope:** Update `/docs/` to be complete, correct, and drift-free.

### Chunk 5.1 — operations-runbook.md: validation pass

Tasks:
- [x] Validate all CLI command invocations use `nightfall-photo-ingress` (not
  `photo-ingress`)
- [x] Validate systemd unit names throughout match actual filenames in `systemd/`
- [x] Validate install path `/opt/nightfall-photo-ingress` and config path
  `/etc/nightfall/photo-ingress.conf` match install script behavior
- [x] Check working state path (`/var/lib/ingress` is mentioned in runbook but
  design says `/mnt/ssd/photo-ingress` — confirm which is correct in production)
- [x] Add section: **Operator Workflows** covering:
  - `nightfall-photo-ingress config-check` — purpose and expected output
  - `nightfall-photo-ingress accept <sha256>` — when and how to use
  - `nightfall-photo-ingress reject <sha256>` — when and how to use
  - `nightfall-photo-ingress purge <sha256>` — when and how to use
  - `nightfall-photo-ingress process-trash` — when and how to use
  - Trash directory workflow (drop file → systemd path unit → auto-process)
  - `nightfall-photo-ingress sync-import` — when to run and what it does
- [x] Add section: **Status File Interpretation** — each `state` value and what
  operator action it implies
- [x] Add section: **Staged File Recovery** — what to do if poll crashed mid-run:
  staging reconciliation, stale .tmp cleanup, safe restart

### Chunk 5.2 — app-registration-design.md: reclassification

Tasks:
- [x] Split the file:
  - Design-level content (error detection design, scope normalization, design
    principles) → new file `design/auth-design.md`
  - Operator content (how to register the app, config-check steps, bootstrap token
    cache, verify Graph access, registered instance record) → stays in `docs/`
    integrated into or alongside `operations-runbook.md`
- [x] Update `docs/app-registration-design.md` to contain only operator-facing
  content; add a reference at the top pointing to `design/auth-design.md` for
  the design rationale
- [x] In `design/auth-design.md`, reference `design/domain-architecture-overview.md`
  §13 (Error Taxonomy) and the new `design/error-taxonomy-and-resilience.md`

---

## Phase 6 — ARCHITECTURE.md Root File

**Scope:** Fix the broken references in the root README-adjacent architecture file.

### Chunk 6.1 — Fix broken cross-references

Tasks:
- [x] Replace `design/web-control-plane-architecture-extension.md` reference with
  correct paths: `design/web-control-plane-architecture-phase2.md` and
  `design/web-control-plane-architecture-phase3.md`
- [x] Replace `planning/web-control-plane-implementation-roadmap.md` reference with
  `planning/planned/web-control-plane-integration-plan.md`
- [x] Review the module responsibilities table and verify it is consistent with the
  current source tree; update `runtime/` description to mention process lock and
  per-account singleton lock

---

## Phase 7 — Consistency Validation

**Scope:** After phases 1–6, perform a structured cross-layer consistency sweep.

### Chunk 7.1 — Naming consistency sweep

Check every design, planning, and docs file for:
- [x] `photo-ingress` CLI invocations → should be `nightfall-photo-ingress`
- [x] `photo-ingress-poll.*` systemd units → should be `nightfall-photo-ingress.*`
- [x] Any reference to old paths: `ssdpool/onedrive-ingress`, `/mnt/ssd/onedrive-ingress`,
  `nightfall/media/onedrive-ingress`
- [x] Any reference to old module paths: `nightfall_photo_ingress/onedrive/`,
  `nightfall_photo_ingress/pipeline/`

### Chunk 7.2 — Cross-layer invariant check

Verify these invariants hold across all three layers:

| Invariant | Checked in |
|-----------|-----------|
| Registry status set = `{pending, accepted, rejected, purged}` | design §5, docs runbook |
| `accepted_records` written only on explicit accept, never on ingest | design §6.5 |
| Cursor advance only after page side-effects are durable | design §6.1.1 |
| Audit log is append-only; no rows ever deleted | design §5, Schema Properties |
| Token cache mode = `0600` | design §8, docs runbook |
| Process lock serializes poll runs | design §7, ARCHITECTURE.md |
| Permanent library is read-only from ingress perspective | design §3, §4 |
| Zero-byte files are quarantined, not silently discarded | design §12 (new) |

### Chunk 7.3 — Internal link health check

For each markdown file in `/design/`, `/planning/`, and `/docs/`:
- [x] Scan all `[text](path)` references
- [x] Confirm each referenced file exists at the stated path
- [x] Flag any dead links for repair

---

## Execution Order and Stopping Points

| Chunk | Description | Stop after? | Status |
|-------|-------------|-------------|--------|
| 1.1 | Promote domain-architecture-overview.md status + fix naming | Yes | ✅ Done — 2026-04-03 |
| 1.2 | Update schema section | Yes | ✅ Done — 2026-04-03 |
| 1.3 | Update file layout section | Yes | ✅ Done — 2026-04-03 |
| 1.4 | Update config + pipeline sections | Yes | ✅ Done — 2026-04-03 |
| 1.5 | Update phases section + add new design sections | Yes | ✅ Done — 2026-04-03 |
| 2.1–2.4 | ADL additions (all four in one pass) | Yes | ✅ Done — 2026-04-03 |
| 3.1 | New doc: ingest-lifecycle-and-crash-recovery | Yes | ✅ Done — 2026-04-03 |
| 3.2 | New doc: error-taxonomy-and-resilience | Yes | ✅ Done — 2026-04-03 |
| 3.3 | New doc: observability | Yes | ✅ Done — 2026-04-03 |
| 4.1 | Planning: gate status update | Yes | ✅ Done — 2026-04-03 |
| 4.2 | Planning: roadmap Modules 5–8 status update | Yes | ✅ Done — 2026-04-03 |
| 4.3 | Planning: web control plane docs coherence | Yes | ✅ Done — 2026-04-03 |
| 4.4 | Planning: v2 deferred backlog staleness | Yes | ✅ Done — 2026-04-03 |
| 5.1 | Docs: operations-runbook validation + expansion | Yes | ✅ Done — 2026-04-03 |
| 5.2 | Docs: app-registration-design reclassification | Yes | ✅ Done — 2026-04-03 |
| 6.1 | Root ARCHITECTURE.md reference fixes | Yes | ✅ Done — 2026-04-03 |
| 7.1–7.3 | Consistency validation sweep | Yes | ✅ Done — 2026-04-03 |

Total: 18 stopping-point chunks.

---

## Out of Scope for This Plan

- Implementing any new code (this is documentation work only)
- Web control plane implementation (no `api/` or `webui/` code)
- Changing the registry schema or existing migration files
- Resolving the open points in `audit/open ponts/module6-external-library-download-avoidance-open-point.md`
  and `audit/open ponts/staging-permissions-security-open-point.md` (these are implementation decisions,
  not documentation tasks — they produce design inputs, not design outputs)

---

## Notes for Execution

- When editing existing markdown files, preserve append-only sections (ADL records,
  audit records) by appending rather than rewriting.
- When adding new design sections to `domain-architecture-overview.md`, add them as
  new numbered sections — do not renumber existing sections.
- New design documents should use the same header style as existing design docs:
  `Status`, `Date`, `Author`, with a short Overview section and structured body.
- All inline examples, log excerpts, and CLI snippets use `nightfall-photo-ingress`
  as the command name.
