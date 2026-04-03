# Documentation Structure Mapping Implementation Plan

**Status:** Chunks D and B complete; Chunks A and C pending  
**Author:** GitHub Copilot  
**Created:** 2026-04-03  
**Authoritative source:** `audit/documentation-structure-mapping.md` — Summary and Recommendations  
**Scope:** Implement the structural recommendations from the documentation structure mapping
audit. Raise structural coherence, navigation fidelity, and target-category coverage to
match the proposed documentation architecture.

---

## Background

The documentation structure mapping audit (`audit/documentation-structure-mapping.md`)
evaluated 42 existing documentation files against a proposed 12-category target folder
hierarchy. It identified four categories of required work:

1. Two composite documents that each span multiple proposed targets and require decomposition.
2. Two structural additions missing from the proposed target architecture that have extensive existing content but no home.
3. Fourteen proposed target files with no existing source content (missing or partial).
4. Four housekeeping defects that require no content work.

This plan defines four execution chunks — D, B, A, C — in the order they must be
executed. Each chunk must be reviewed and approved by the user before the next begins.

---

## Out of Scope for This Plan

The following topics are explicitly excluded from all chunks. Work touching these areas
that is identified incidentally must be annotated but not performed:

- Security / threat model content
- Schema migrations (v1 → v2)
- Deployment details and environment setup documentation
- Operator maintenance procedures
- Versioning policy
- Backup / restore procedures
- Web control plane implementation details (content authoring)
- Any non-critical topics from the audit not listed as actions below

---

## Execution Order

```
CHUNK D (housekeeping — no content work) ✅ COMPLETE → commit 6a4ee6a
    ↓
CHUNK B (add missing structural categories) ✅ COMPLETE → commit TBD
    ↓
CHUNK A (decompose composite documents) → STOP, await user review
    ↓
CHUNK C (create missing target documents) → STOP, await user review
```

**Rationale for this order:**
- D first: zero-dependency renames and deletions; unblocks accurate cross-references in all subsequent chunks.
- B second: establishes the target directories that Chunk A's decomposed documents need as destinations (`design/web/`, `design/architecture/observability.md`).
- A third: extracts content from the two composite documents into the target directories created in B; must precede C so that Chunk C does not duplicate content that already exists post-extraction.
- C last: authors net-new documents for targets with no source content; depends on B and A being complete so that the correct target structure is in place and no overlaps exist.

---

## Chunk D — Fix Four Housekeeping Defects

### Objectives

Correct all mechanical defects in the repository layout that impose navigation friction
and silently mislead tooling. None of these actions require content authoring.

### Required Actions

| # | Defect | Location | Required action |
|---|--------|----------|-----------------|
| D-1 | `audit/security-threat-model.md` was missing the `.md` extension (old filename misnamed) | `audit/` | ✅ Renamed to `audit/security-threat-model.md` |
| D-2 | Old filename contained "thread" instead of "threat" | `audit/` | ✅ Rename applied the spelling correction simultaneously with D-1 |
| D-3 | `audit/open-points/` directory name contained a typo and a space (misnamed) | `audit/` | ✅ Moved to `audit/open-points/`; all cross-references updated |
| D-4 | `audit/drift-analysis.md` and `audit/review-history.md` were empty 0-byte stubs | `audit/` | ✅ Minimal stub header added to both |

**Notes:**
- D-1 and D-2 are resolved in a single `git mv` operation.
- D-3 required a scan of all markdown files for references to the old misnamed directory name and updating those cross-references after the rename.
- D-4 is the only action in this chunk that touches content. The scope is limited to adding a minimal front-matter header (title, status: stub, date) to each empty file, not authoring substantive content. If the user decides to delete rather than stub, no content is produced.
- `audit/security-threat-model.md` is out of scope for content authoring (threat model is excluded from this plan). The rename corrects the filename defect only; the file remains empty after D-1/D-2.

### Dependencies

None. This chunk has no dependency on any other chunk or on any other plan.

### Boundaries (Explicitly Out of Scope)

- Authoring any substantive content in `audit/security-threat-model.md`.
- Authoring `audit/drift-analysis.md` or `audit/review-history.md` beyond a minimal stub header.
- Any changes to `/design/`, `/planning/`, or `/docs/` files.
- Moving or restructuring the contents of `audit/open-points/` (only the directory rename is performed).
- Fixing the `docs/app-registration-design.md` misclassification defect (listed in Section 7 of the audit but not named in the Summary Recommendations for housekeeping; deferred).

### Expected Output

After Chunk D, the repository will have:
- `audit/security-threat-model.md` (renamed; content unchanged — empty or minimal stub)
- `audit/open-points/` (renamed from old misnamed directory; all internal files unchanged ✅)
- `audit/drift-analysis.md` (either minimal stub or deleted)
- `audit/review-history.md` (either minimal stub or deleted)
- All cross-references to old names updated

### Acceptance Criteria

- `git ls-files audit/` contains `audit/security-threat-model.md` and no file matching the old misnamed filename.
- `git ls-files audit/` contains `audit/open-points/` and no path segment matching the old directory name.
- `grep` for the old misnamed directory name returns no results in markdown files.
- `grep` for the old security file name returns no results in markdown files.
- `audit/drift-analysis.md` and `audit/review-history.md` each either have content (≥1 line) or are absent from `git ls-files`.
- No content has been authored in `audit/security-threat-model.md`.

---

## Chunk B — Add Missing Mandatory Categories to Documentation Structure

### Objectives

Introduce two structural additions that are missing from the proposed documentation
architecture but which have extensive existing content that cannot be correctly placed
without them. This chunk creates directories and placeholder README files only — no
substantive content is authored.

### Required Actions

#### B-1 — Create `/design/web/` category

The five web control plane design documents (~2,800 lines total) currently live flat
under `design/` alongside core CLI design documents. The proposed structure has no
web/API documentation section. Without this category, these documents have no valid
target home and cannot be decomposed correctly.

Required actions:
1. Create `design/web/` directory (via a `README.md` placeholder).
2. Move the five existing web control plane design documents into `design/web/`:
   - `design/webui-architecture-phase1.md` → `design/web/webui-architecture-phase1.md`
   - `design/webui-component-mapping-phase1.md` → `design/web/webui-component-mapping-phase1.md`
   - `design/webui-design-tokens-phase1.md` → `design/web/webui-design-tokens-phase1.md`
   - `design/web-control-plane-architecture-phase2.md` → `design/web/web-control-plane-architecture-phase2.md`
   - `design/web-control-plane-architecture-phase3.md` → `design/web/web-control-plane-architecture-phase3.md`
3. Update any cross-references to these documents in other markdown files.
4. Add a `design/web/README.md` with: category purpose, list of documents and their purpose, and a note that this category covers the web control plane and UI design only.

**Scope note:** This chunk only moves existing documents and creates the structural
placeholder. It does not add, remove, or modify any content within the moved documents.

#### B-2 — Create `/design/architecture/observability.md` placeholder

`design/observability.md` (226 lines) is a specification-grade document that does not
fit any current proposed category. The recommended addition is a dedicated
`design/architecture/observability.md` target.

Required actions:
1. Create `design/architecture/` directory if it does not already exist.
2. Create a `design/architecture/observability.md` placeholder that notes this file is
   the intended target for the observability specification content extracted from
   `design/observability.md`.
3. Do NOT move or modify `design/observability.md` in this chunk — migration from the
   source document is handled in Chunk A.

**Note:** `design/architecture/` is also the intended home for the state machine spec
(`state-machine.md`) and live photo lifecycle spec (`live-photo-pair-lifecycle.md`),
which are produced by a parallel plan (`critical-architecture-completion-plan.md`). This
chunk only creates the directory and the observability placeholder; the other
`design/architecture/` files are produced by that separate plan.

### Dependencies

- Chunk D must be completed first (cross-reference updates in D-3 must precede the
  reference updates in B-1).
- No dependency on Chunk A or Chunk C.

### Boundaries (Explicitly Out of Scope)

- Authoring any content within the moved web control plane documents.
- Creating subdirectories within `design/web/` (e.g. `design/web/api/`, `design/web/ui/`).
- Migrating observability content from `design/observability.md` into the new placeholder (that is Chunk A's responsibility).
- Creating any other `design/architecture/` files (covered by the critical architecture completion plan).
- Modifying `docs/`, `planning/`, or `audit/` files beyond cross-reference updates.

### Expected Output

After Chunk B, the repository will have:
- `design/web/README.md` (new — placeholder with category description)
- `design/web/webui-architecture-phase1.md` (moved)
- `design/web/webui-component-mapping-phase1.md` (moved)
- `design/web/webui-design-tokens-phase1.md` (moved)
- `design/web/web-control-plane-architecture-phase2.md` (moved)
- `design/web/web-control-plane-architecture-phase3.md` (moved)
- `design/architecture/observability.md` (new — placeholder only)
- All cross-references to moved files updated across the corpus

### Acceptance Criteria

- `git ls-files design/web/` lists all five moved documents plus `README.md`.
- `git ls-files design/` does not list any of the five web documents at the flat `design/` level.
- `git ls-files design/architecture/observability.md` exists.
- `grep -r "webui-architecture-phase1\|web-control-plane-architecture-phase" design/ docs/ planning/` returns only paths under `design/web/`.
- No content has been added to or removed from the five moved documents (only path changes).
- `design/architecture/observability.md` contains only a placeholder header (no substantive content migrated yet).

---

## Chunk A — Decomposition of Composite Documents

### Objectives

Decompose the two composite documents that each span multiple proposed target categories.
The approach for both documents is incremental extraction, not bulk rewrite:
- Retain the source document as a navigational anchor with cross-references to extracted files.
- Extract each major section into its dedicated target document.
- Replace the extracted section in the source document with a summary paragraph and a cross-reference link.

### Source Document 1 — `design/domain-architecture-overview.md` (773 lines)

This document maps to 12 proposed targets. Each extraction is a separate sub-task.

| Sub-task | Section(s) to extract | Target file |
|----------|----------------------|-------------|
| A-1a | §2 high-level pipeline flow | `design/architecture/data-flow.md` |
| A-1b | §2 pipeline diagram, §4 storage layout | `design/architecture/storage-topology.md` |
| A-1c | §6.1 poll cycle, §14 journal, §6.1.1 cursor commit rule | `design/architecture/lifecycle.md` |
| A-1d | §15 error taxonomy | `design/architecture/error-model.md` |
| A-1e | §7 observability spec, structured log schema, run-ID threading, diagnostic counters | `design/architecture/observability.md` (created in Chunk B) |
| A-1f | §5 registry schema + properties | `design/specs/registry.md` |
| A-1g | §6.1 pipeline behaviour, §6.3 sync import | `design/specs/ingest.md` |
| A-1h | §6.5 accept flow | `design/specs/accept.md` |
| A-1i | §6.4 rejection flow | `design/specs/reject.md` |
| A-1j | §6.5 purge flow | `design/specs/purge.md` |
| A-1k | §3 design constraints | `design/domain/constraints.md` |
| A-1l | §1.1 naming matrix | `design/domain/glossary.md` (partial — see Chunk C) |
| A-1m | §8 tech stack rationale | `design/rationale/tradeoffs.md` (partial — see Chunk C) |

**Retained in source:** Navigation index, introduction, cross-reference list, any sections that do not cleanly map to a single target (retain with annotation).

**Extraction rule per sub-task:**
1. Copy the relevant section(s) verbatim into the target file with a standard header.
2. In the source document, replace the extracted section body with a one-paragraph summary and a `→ See [target file](../relative/path)` link.
3. Commit each sub-task individually so that decomposition history is granular.

### Source Document 2 — `docs/operations-runbook.md` (602 lines)

This document maps to 5 proposed targets. Each extraction is a separate sub-task.

| Sub-task | Section(s) to extract | Target file |
|----------|----------------------|-------------|
| A-2a | §Operator Workflows (accept/reject/purge/trash/sync-import), §Status File Interpretation | `docs/operator/operational-playbook.md` |
| A-2b | §Config check, §auth-setup, §poll, §Registered Application Instance | `docs/operator/cli-guide.md` |
| A-2c | §Failure handling, §Staged File Recovery, §Troubleshooting P2/P3 failures, §Status File Interpretation | `docs/operator/troubleshooting.md` |
| A-2d | §Install and uninstall, §Runtime layout, §Packaged units, §How To: Register Entra App | `docs/deployment/environment-setup.md` |
| A-2e | §Staging Flow: P2/P3, §Controlled-environment validation | `docs/operator/maintenance.md` |

**Note on A-2d and A-2e:** `docs/deployment/environment-setup.md` (A-2d) and
`docs/operator/maintenance.md` (A-2e) cover deployment details and operator maintenance,
which are out of scope for content authoring in this plan. However, the structural
decomposition action — extracting the section into the target file with a header, and
replacing the source section with a cross-reference — is in scope as a structural act.
The sub-task is limited to: (1) creating the target file with the verbatim extracted
section, (2) replacing the section in the runbook with a cross-reference. No additional
content is authored in A-2d or A-2e.

**Post-decomposition:** Once all five extractions are complete, `docs/operations-runbook.md`
becomes a navigational index only. Evaluate whether to retain it as an index or remove it
and replace with a `docs/README.md` navigation document; decision deferred to user
steering before chunk execution.

### Dependencies

- Chunk D must be completed first (correct cross-reference paths must be in place).
- Chunk B must be completed first (`design/architecture/` and `design/web/` must exist before extractions target them; `design/architecture/observability.md` placeholder must exist for A-1e).
- Sub-task A-1l (`glossary.md`) and A-1m (`tradeoffs.md`) produce partial target files; Chunk C will complete them. These sub-tasks must be completed before Chunk C begins.
- Sub-task A-1d (`error-model.md`) is a full extraction of `design/error-taxonomy-and-resilience.md` content; Chunk C does not need to create `error-model.md` as it will exist after A-1d.

### Boundaries (Explicitly Out of Scope)

- Authoring new content beyond what is verbatim in the source documents.
- Rewriting, restructuring, or editorialising any extracted section.
- Creating target files not listed in the extraction tables above.
- Architectural decisions about content (e.g. whether §6.3 sync-import belongs in `ingest.md` as a deferred/unimplemented feature or as a separate document).
- Decomposing `design/auth-design.md`, `design/ingest-lifecycle-and-crash-recovery.md`, or any document not listed as a source here; those are 1:1 or near-1:1 mappings and do not require decomposition.
- Performing any Chunk C authoring work during Chunk A execution.

### Expected Output

After Chunk A, the repository will have the following new or materially extended files
(from `design/domain-architecture-overview.md` extractions):
- `design/architecture/data-flow.md`
- `design/architecture/storage-topology.md`
- `design/architecture/lifecycle.md`
- `design/architecture/error-model.md`
- `design/architecture/observability.md` (extended from Chunk B placeholder)
- `design/specs/registry.md`
- `design/specs/ingest.md`
- `design/specs/accept.md`
- `design/specs/reject.md`
- `design/specs/purge.md`
- `design/domain/constraints.md`
- `design/domain/glossary.md` (partial — naming matrix section only)
- `design/rationale/tradeoffs.md` (partial — tech stack section only)

And from `docs/operations-runbook.md` extractions:
- `docs/operator/operational-playbook.md`
- `docs/operator/cli-guide.md`
- `docs/operator/troubleshooting.md`
- `docs/deployment/environment-setup.md`
- `docs/operator/maintenance.md`

And the modified source documents:
- `design/domain-architecture-overview.md` (retained as navigational anchor)
- `docs/operations-runbook.md` (retained as navigational index or removed — decision before execution)

### Acceptance Criteria

- Each extraction target file exists and contains verbatim extracted content with a standard header.
- Each extracted section in the source documents is replaced with a one-paragraph summary and a cross-reference link.
- `design/domain-architecture-overview.md` and `docs/operations-runbook.md` each have ≤ 20% of their original line count remaining as body prose (remainder is navigation/cross-references).
- No new content has been authored; all target file content is traceable to a line range in a source document.
- All internal links from other documents to headings within the extracted content continue to resolve (update-in-place to new target paths).

---

## Chunk C — Create 14 Missing Target Documents

### Objectives

Author or formally stub the 14 proposed target files from Section 6 of the structure
mapping report that have no existing source content. This chunk is the only place where
net-new content is authored.

Note on overlaps with parallel plans: Three of the 14 missing targets are being addressed
by `critical-architecture-completion-plan.md`. This chunk must not duplicate that work;
instead it records the dependency and defers execution of those items.

### All 14 Missing Targets: Scope Classification

| # | File | Section 6 status | This plan's action |
|---|------|-----------------|-------------------|
| C-01 | `design/architecture/state-machine.md` | MISSING | **Deferred to critical-architecture-completion-plan.md Chunk A** |
| C-02 | `design/architecture/invariants.md` | MISSING | **Author in this chunk** |
| C-03 | `design/domain/glossary.md` | PARTIAL | **Complete in this chunk** (A-1l produced the naming matrix section; this sub-task adds full domain glossary) |
| C-04 | `design/domain/domain-model.md` | PARTIAL | **Author in this chunk** (extract from `ARCHITECTURE.md` module map + extend) |
| C-05 | `design/rationale/tradeoffs.md` | PARTIAL | **Complete in this chunk** (A-1m produced tech stack section; this sub-task adds adapter extensibility and other tradeoff entries) |
| C-06 | `design/rationale/deprecated-concepts.md` | PARTIAL | **Author in this chunk** (synthesize from `design/superseeded/` files) |
| C-07 | `migrations/schema-v1.md` | MISSING | **Out of scope** (v1→v2 migrations excluded) |
| C-08 | `migrations/schema-v2.md` | MISSING | **Deferred to critical-architecture-completion-plan.md Chunk C** |
| C-09 | `migrations/upgrade-guide.md` | MISSING | **Out of scope** (versioning policy / deployment details excluded) |
| C-10 | `docs/operator/maintenance.md` | MISSING | **Out of scope** (operator maintenance excluded) — stub only from Chunk A decomposition |
| C-11 | `docs/operator/failure-scenarios.md` | PARTIAL | **Out of scope** (operator maintenance excluded) |
| C-12 | `docs/deployment/versioning-policy.md` | MISSING | **Out of scope** (versioning policy excluded) |
| C-13 | `planning/migration-roadmap.md` | MISSING | **Author a minimal stub** (planning document, not a migration document; records migration intent only) |
| C-14 | `/design/web/` category | MISSING | **Completed in Chunk B** (structural category created; content authoring out of scope) |

### In-Scope Sub-Tasks

#### C-02 — `design/architecture/invariants.md`

**Purpose:** Consolidate the system invariants that are currently scattered across prose
in `design/domain-architecture-overview.md`, `design/ingest-lifecycle-and-crash-recovery.md`,
and `docs/operations-runbook.md` into a single authoritative invariants catalogue.

**Source material:** Extract invariant statements from the design corpus; do not invent
new invariants.

**Expected content structure:**
- Invariant catalogue table: (ID, Invariant statement, Scope, Source document, Section)
- Grouping by category: registry invariants, storage invariants, staging invariants, audit log invariants

**Acceptance criteria:**
- All invariants documented in `design/domain-architecture-overview.md` §3 (design constraints) and elsewhere are enumerated.
- Each invariant has a traceable source citation.
- No invariant is invented without a source.

#### C-03 — `design/domain/glossary.md` (completion)

**Purpose:** Extend the naming matrix extracted in A-1l into a full domain glossary with
definitions, owning module, and usage notes for each term.

**Source material:** `design/domain-architecture-overview.md §1.1` (already extracted in A-1l), `design/ingest-lifecycle-and-crash-recovery.md`, `ARCHITECTURE.md`.

**Expected content structure:**
- Alphabetical term table: (Term, Definition, Owning module, Notes)
- Second table: naming conventions matrix (service name vs. binary name vs. systemd unit name vs. ZFS dataset name)

**Acceptance criteria:**
- All terms used in design documents with non-obvious meanings are defined.
- Naming matrix is present and consistent with `design/domain-architecture-overview.md §1.1`.

#### C-04 — `design/domain/domain-model.md`

**Purpose:** Produce a cross-cutting domain model document that describes the bounded
context, the primary entities, their relationships, and the module-layer map.

**Source material:** `ARCHITECTURE.md` (module map, adapter extensibility), `design/domain-architecture-overview.md` (entity relationships implicit in the architecture).

**Expected content structure:**
- Bounded context statement
- Primary domain entities table: (Entity, Table/structure, Module ownership, Lifecycle)
- Module-layer map (extracted from `ARCHITECTURE.md` and extended with domain/adapter/runtime layers)
- Entity relationship summary diagram (Mermaid)

**Acceptance criteria:**
- All primary entities (`files`, `live_photo_pairs`, `metadata_index`, `audit_log`, etc.) are described.
- Module ownership for each entity is stated.
- `ARCHITECTURE.md` module map section is superseded by cross-reference to this document.

#### C-05 — `design/rationale/tradeoffs.md` (completion)

**Purpose:** Extend the tech stack section extracted in A-1m into a full tradeoff
document covering adapter extensibility, SQLite over PostgreSQL decision, WAL mode
rationale, and other architectural options.

**Source material:** `design/domain-architecture-overview.md §8`, `design/architecture-decision-log.md`, `ARCHITECTURE.md` (adapter extensibility paragraph).

**Acceptance criteria:**
- At least the following tradeoff areas are covered: database engine choice, WAL mode, adapter extensibility pattern, single-binary vs. daemon architecture.
- Each tradeoff entry references the relevant ADL entry in `design/architecture-decision-log.md` where one exists.

#### C-06 — `design/rationale/deprecated-concepts.md`

**Purpose:** Synthesize the two superseded design documents into a single reference that
records what was superseded, why, and what replaced it.

**Source material:**
- `design/superseeded/v1-lifecycle-baseline-superseded.md` (295 lines)
- `design/superseeded/web-control-plane-initial-extension-superseded.md` (162 lines)

**Expected content structure:**
- Deprecation registry table: (Concept, Superseded document, Superseded date/version, Replacement, Reason for deprecation)
- One-paragraph summary per deprecated concept

**Acceptance criteria:**
- Both superseded documents are represented in the deprecation registry.
- The document does not restate the full superseded content — it summarises and cross-references.

#### C-13 — `planning/migration-roadmap.md` (stub)

**Purpose:** Create a stub planning document recording the intent to define a migration
roadmap. This is a planning artefact, not a migration specification.

**Expected content:** Title, status (`stub — not yet authored`), a description of what
the roadmap will cover when authored, and a note that schema migration documentation is
covered by `critical-architecture-completion-plan.md`.

**Acceptance criteria:**
- File exists with at least a title, status, and one-paragraph scope description.
- File does not contain any migration specification content.

### Dependencies

- Chunk B must be completed (C-04 `domain-model.md` references `design/architecture/` files that Chunk B creates).
- Chunk A must be completed (C-03, C-05 complete partial files produced by A-1l and A-1m respectively).
- `critical-architecture-completion-plan.md` Chunks A and C should be completed or in progress before Chunk C of this plan produces `invariants.md` (to avoid duplicating state machine invariants that are being documented separately).

### Boundaries (Explicitly Out of Scope)

- C-07 (`migrations/schema-v1.md`) — out of scope, v1→v2 migration excluded.
- C-08 (`migrations/schema-v2.md`) — deferred to critical-architecture-completion-plan.md.
- C-09 (`migrations/upgrade-guide.md`) — out of scope, versioning policy excluded.
- C-10 (`docs/operator/maintenance.md`) — out of scope, operator maintenance excluded. (File may exist as a structural stub from Chunk A but no content is authored here.)
- C-11 (`docs/operator/failure-scenarios.md`) — out of scope, operator maintenance excluded.
- C-12 (`docs/deployment/versioning-policy.md`) — out of scope, versioning policy excluded.
- C-14 (`/design/web/` category) — completed in Chunk B; no further work in this chunk.
- `design/architecture/state-machine.md` — produced by critical-architecture-completion-plan.md, not this plan.
- Planning restructuring (collapsing existing planning files into flat structure) — a separate future initiative; this chunk only creates the single new stub file `planning/migration-roadmap.md`.

### Expected Output

After Chunk C, the repository will have the following new or completed files:
- `design/architecture/invariants.md`
- `design/domain/glossary.md` (completed)
- `design/domain/domain-model.md`
- `design/rationale/tradeoffs.md` (completed)
- `design/rationale/deprecated-concepts.md`
- `planning/migration-roadmap.md` (stub)

### Acceptance Criteria

- All six in-scope files listed above exist and contain substantive content (not zero-byte stubs).
- No content has been authored in out-of-scope files.
- All content in new files is traceable to source documents or to the implementation (no speculative content).
- After Chunk C, `grep -r "MISSING\|TODO\|stub" design/domain/ design/rationale/ design/architecture/invariants.md` returns no results except for intentional stub notes.

---

## Coordination with `critical-architecture-completion-plan.md`

This plan and `critical-architecture-completion-plan.md` are parallel execution tracks.
They share certain target files:

| File | Owner plan | Dependency note |
|------|-----------|-----------------|
| `design/architecture/state-machine.md` | critical-architecture-completion-plan.md Chunk A | This plan must not create this file; deferred as C-01 |
| `design/architecture/live-photo-pair-lifecycle.md` | critical-architecture-completion-plan.md Chunk B | Not in this plan's scope at all |
| `design/architecture/schema-and-migrations.md` | critical-architecture-completion-plan.md Chunk C | Not in this plan's scope at all |
| `design/architecture/` directory | Chunk B of this plan creates it; critical-architecture plan populates it | No conflict — directory creation is idempotent |
| `design/architecture/observability.md` | This plan (Chunk A extracts into it; Chunk C does not modify it) | No conflict |

Both plans may be executed concurrently as long as they do not touch the same files in
the same turn.
