# Documentation Structure Mapping Report

**Type:** Audit  
**Status:** Active  
**Date:** 2026-04-03  
**Author:** Documentation Sufficiency & Drift Audit  
**Scope:** `nightfall-photo-ingress` — full documentation corpus

---

## Purpose

This report maps every existing documentation file to the proposed target folder
architecture. For each document it records: where it belongs, whether it fits cleanly or
requires decomposition, and whether any proposed target categories are missing content or
missing entirely.

The proposed target structure evaluated against is:

```
/design
    /architecture    state-machine.md  lifecycle.md  invariants.md
                     data-flow.md  storage-topology.md  error-model.md
    /domain          glossary.md  domain-model.md  constraints.md
    /specs           accept.md  reject.md  purge.md  ingest.md  registry.md  config.md
    /rationale       design-decisions.md  tradeoffs.md  deprecated-concepts.md
/planning
    planned.md  in-progress.md  done.md  backlog.md  migration-roadmap.md
/docs
    /operator        cli-guide.md  troubleshooting.md  operational-playbook.md
                     failure-scenarios.md  maintenance.md
    /deployment      environment-setup.md  config-guide.md  versioning-policy.md
/audit
    drift-analysis.md  threat-model.md  review-history.md
/migrations
    schema-v1.md  schema-v2.md  upgrade-guide.md
```

---

## Section 1 — `/design/` Mapping

### 1.1 `design/domain-architecture-overview.md` (773 lines)

**Fit quality: Does not fit cleanly — decomposition required**

This is the primary omnibus design document. It spans at least eight proposed targets:

| Section(s) | Proposed target |
|---|---|
| §2 pipeline diagram, §4 storage layout | `design/architecture/storage-topology.md` |
| §2 high-level pipeline flow | `design/architecture/data-flow.md` |
| §6.1 poll cycle, §14 journal, §6.1.1 cursor commit rule | `design/architecture/lifecycle.md` |
| §15 error taxonomy | `design/architecture/error-model.md` |
| §5 registry schema + properties | `design/specs/registry.md` |
| §6.1 pipeline behavior, §6.3 sync import | `design/specs/ingest.md` |
| §6.5 accept flow | `design/specs/accept.md` |
| §6.4 rejection flow | `design/specs/reject.md` |
| §6.5 purge flow | `design/specs/purge.md` |
| §3 design constraints | `design/domain/constraints.md` |
| §1.1 naming matrix | `design/domain/glossary.md` |
| §8 tech stack rationale | `design/rationale/tradeoffs.md` |

Recommended action: retain as-is at current path as a navigational anchor document, but
extract individual sections into dedicated spec/architecture files and replace those
sections with cross-references.

---

### 1.2 `design/ingest-lifecycle-and-crash-recovery.md` (258 lines)

**Fit quality: Fits with minor split**

Primary home: `design/architecture/lifecycle.md` (StagingDriftReport, journal crash
recovery, zero-byte policy).

Minor overflow: zero-byte quarantine policy and the `quarantine` action taxonomy lean
toward `design/architecture/invariants.md`.

---

### 1.3 `design/error-taxonomy-and-resilience.md` (291 lines)

**Fit quality: Fits cleanly — 1:1 mapping**

Maps directly to `design/architecture/error-model.md`.

---

### 1.4 `design/cli-config-specification.md` (202 lines)

**Fit quality: Mostly fits — location mismatch**

Content maps to `docs/deployment/config-guide.md`. Currently filed under `design/`
rather than `docs/deployment/`, which misrepresents it as a design concern rather than
an operator reference document. Validation rules and constraint rationale may also
contribute to `design/domain/constraints.md`.

---

### 1.5 `design/architecture-decision-log.md` (438 lines)

**Fit quality: Fits cleanly — 1:1 mapping**

Maps directly to `design/rationale/design-decisions.md`.

---

### 1.6 `design/auth-design.md` (160 lines)

**Fit quality: Splits across two targets**

- Auth principles, MSAL integration rationale, token cache security model, scope
  normalization design → `design/rationale/design-decisions.md` (as an ADL entry or
  appendix).
- Auth setup procedure, error diagnostic hints, operator configuration examples →
  `docs/operator/cli-guide.md`.

---

### 1.7 `design/observability.md` (226 lines)

**Fit quality: No exact mapping exists — missing category**

The structured log schema, run-ID threading, diagnostic counter table, and status
snapshot contract are specification-grade material. The proposed structure does not have
an `/architecture/observability.md` or `/specs/observability.md` target.

Recommended addition to proposed structure: `design/architecture/observability.md` or
`design/specs/observability.md`.

---

### 1.8 `design/webui-architecture-phase1.md` (329 lines)

**Fit quality: No mapping — structural blind spot**

The proposed target structure has no web/API documentation section. This document (and
the four below) have ~2,800 lines of content and no place to land.

Recommended addition to proposed structure: `/design/web/` category with at minimum:
`api-spec.md`, `ui-architecture.md`, `web-control-plane.md`.

---

### 1.9 `design/webui-component-mapping-phase1.md` (354 lines)

**Fit quality: No mapping** — same structural blind spot as 1.8.

---

### 1.10 `design/webui-design-tokens-phase1.md` (312 lines)

**Fit quality: No mapping** — same structural blind spot as 1.8.

---

### 1.11 `design/web-control-plane-architecture-phase2.md` (792 lines)

**Fit quality: No mapping** — same structural blind spot as 1.8.

---

### 1.12 `design/web-control-plane-architecture-phase3.md` (1,083 lines)

**Fit quality: No mapping** — same structural blind spot as 1.8.

---

### 1.13 `design/superseeded/v1-lifecycle-baseline-superseded.md` (295 lines)

**Fit quality: Fits cleanly**  
Maps to `design/rationale/deprecated-concepts.md`.

---

### 1.14 `design/superseeded/web-control-plane-initial-extension-superseded.md` (162 lines)

**Fit quality: Fits cleanly**  
Maps to `design/rationale/deprecated-concepts.md` (alongside 1.13).

---

## Section 2 — `/docs/` Mapping

### 2.1 `docs/operations-runbook.md` (602 lines)

**Fit quality: Does not fit cleanly — decomposition required**

This is a composite operator document spanning five proposed targets:

| Section(s) | Proposed target |
|---|---|
| §Operator Workflows (accept/reject/purge/trash/sync-import), §Status File Interpretation | `docs/operator/operational-playbook.md` |
| §Config check, §auth-setup, §poll, §Registered Application Instance | `docs/operator/cli-guide.md` |
| §Failure handling, §Staged File Recovery, §Troubleshooting P2/P3 failures, §Status File Interpretation | `docs/operator/troubleshooting.md` |
| §Install and uninstall, §Runtime layout, §Packaged units, §How To: Register Entra App | `docs/deployment/environment-setup.md` |
| §Staging Flow: P2/P3, §Controlled-environment validation | `docs/operator/maintenance.md` |

Recommended action: decompose into the five target documents listed above and remove the
combined runbook. Retain internal cross-references between the resulting files.

---

### 2.2 `docs/app-registration-design.md` (99 lines)

**Fit quality: Mostly fits with partial overlap**

Operator provisioning steps and validation checklist → `docs/deployment/environment-setup.md`.  
Auth principles overlap with `design/auth-design.md` and `design/rationale/design-decisions.md` (already cross-referenced in the document itself).

---

## Section 3 — Root Files Mapping

### 3.1 `ARCHITECTURE.md` (175 lines)

**Fit quality: Splits across targets**

| Section | Proposed target |
|---|---|
| Module responsibilities (domain/, adapters/, runtime/) | `design/domain/domain-model.md` |
| Adapter extensibility pattern, future adapter example | `design/rationale/tradeoffs.md` |
| Test organization | No proposed target — test structure documentation has no home in the proposed tree |

Recommended addition to proposed structure: `docs/deployment/testing-guide.md` or a
`/tests/README.md` in-tree reference.

---

## Section 4 — `/audit/` Mapping

| Existing file | Proposed target | Fit quality |
|---|---|---|
| `audit/drift-analysis.md` | `/audit/drift-analysis.md` | **1:1 — but currently empty (0 bytes)** |
| `audit/review-history.md` | `/audit/review-history.md` | **1:1 — but currently empty (0 bytes)** |
| `audit/security-threat-model.md` | `/audit/threat-model.md` | **Maps cleanly but: (a) empty, (b) was previously misnamed (missing `.md` extension, typo); renamed as housekeeping** |
| `audit/open-points/` directory | No proposed target | **No mapping — directory was previously misnamed (typo + space in dirname; renamed as housekeeping); content has no home in proposed structure; recommend adding `/audit/open-points/`** |
| `audit/archive/` (10 files) | No proposed target | **No mapping — historical review artifacts; recommend folding into `/audit/review-history.md` as a summary appendix, then archiving** |

---

## Section 5 — `/planning/` Mapping

The proposed structure flattens the planning layer to five flat files; the current
structure uses a subdirectory tree with 10 files across four subdirectories.

| Current file(s) | Proposed target | Action needed |
|---|---|---|
| `planning/implemented/*.md` (3 files) | `/planning/done.md` | Merge — all three describe delivered phases |
| `planning/planned/doc-reconciliation-plan.md` | `/planning/done.md` | Merge — all 18 chunks ✅ complete |
| `planning/planned/cli-domain-post-audit-next-steps.md` | `/planning/in-progress.md` | Gates partially evaluated; ongoing |
| `planning/planned/cli-v2-deferred-backlog.md` | `/planning/backlog.md` | 1:1 mapping |
| `planning/planned/web-control-plane-integration-plan.md` | `/planning/planned.md` | All phases Not Started |
| `planning/planned/web-control-plane-phase1-scope.md` | `/planning/planned.md` | Merge into web control plane planned section |
| `planning/planned/web-control-plane-project-structure.md` | `/planning/planned.md` | Merge |
| `planning/planned/web-control-plane-techstack-decision.md` | `/planning/planned.md` or `design/rationale/design-decisions.md` | Tech decisions belong in rationale |
| `planning/proposed/web-control-plane-phase2-implementation-roadmap.md` | `/planning/planned.md` | Proposed but not started |
| `planning/superseeded/*.md` | discard or archive | No proposed target; historical only |

---

## Section 6 — Missing Proposed Targets (No Existing Source Content)

The following proposed files have no existing source document and would need to be
authored from scratch:

| Proposed file | Current status | Notes |
|---|---|---|
| `design/architecture/state-machine.md` | **MISSING** | No dedicated state machine document exists |
| `design/architecture/invariants.md` | **MISSING** | Invariants are scattered in prose, never consolidated |
| `design/domain/glossary.md` | **MISSING** | Naming matrix exists (§1.1 of domain-overview) but no formal domain glossary |
| `design/domain/domain-model.md` | **PARTIAL** | Module map in `ARCHITECTURE.md` is partial; cross-cutting domain model does not exist |
| `design/rationale/tradeoffs.md` | **PARTIAL** | Trade-off rationale is embedded in ADL entries but never extracted |
| `design/rationale/deprecated-concepts.md` | **PARTIAL** | Superseded docs exist but are not synthesized into a deprecated-concepts reference |
| `migrations/schema-v1.md` | **MISSING** | No `/migrations/` directory or documents exist |
| `migrations/schema-v2.md` | **MISSING** | — |
| `migrations/upgrade-guide.md` | **MISSING** | — |
| `docs/operator/maintenance.md` | **MISSING** | No maintenance procedures documented (DB vacuum, ZFS snapshots, log rotation, cleanup cadence) |
| `docs/operator/failure-scenarios.md` | **PARTIAL** | Failure handling exists in runbook but not as a structured scenarios catalog |
| `docs/deployment/versioning-policy.md` | **MISSING** | No versioning or release policy document |
| `planning/migration-roadmap.md` | **MISSING** | — |
| *(web/API category)* | **MISSING FROM PROPOSED STRUCTURE** | ~2,800 lines of web control plane design docs have no target category |

---

## Section 7 — Structural Defects in Existing Layout

| Defect | Location | Recommended fix |
|---|---|---|
| Old security stub had no `.md` extension | `audit/` | Renamed to `security-threat-model.md` ✅ done (was misnamed) |
| `audit/open-points/` directory contained a typo in the name | `audit/` | Renamed to `audit/open-points/` ✅ done (was misnamed) |
| `audit/drift-analysis.md`, `audit/review-history.md`, `audit/security-threat-model.md` are all empty stubs | `audit/` | Author or delete |
| Web control plane design docs (~2,800 lines) live flat under `design/` alongside core CLI design docs | `design/` | Move to `design/web/` subdirectory |
| `docs/app-registration-design.md` is named as a design document but is an operator setup guide | `docs/` | Rename and reclassify |

---

## Summary and Recommendations

### What maps cleanly (no work needed)

- `design/error-taxonomy-and-resilience.md` → `design/architecture/error-model.md`
- `design/architecture-decision-log.md` → `design/rationale/design-decisions.md`
- `design/superseeded/` files → `design/rationale/deprecated-concepts.md`
- `planning/planned/cli-v2-deferred-backlog.md` → `/planning/backlog.md`
- `audit/drift-analysis.md` and `audit/review-history.md` (once authored) → same paths

### What requires decomposition (high effort)

Two composite documents account for most of the structural debt:

1. `design/domain-architecture-overview.md` — 773-line omnibus; maps to 12 distinct
   proposed targets. **Recommended approach:** keep as a navigational entry point and
   anchor document; extract each major section into a dedicated file with a backlink.
2. `docs/operations-runbook.md` — 602-line composite; maps to 5 distinct proposed
   targets. **Recommended approach:** decompose into five operator documents; remove the
   combined runbook.

### What requires structural additions to the proposed target

The proposed structure as stated is missing two categories that have extensive existing
content and cannot be omitted:

1. **Web/API documentation section** (`/design/web/` minimum): Five documents totalling
   ~2,800 lines describe the web control plane and have no target home. Without this
   category the proposed structure would require discarding or misplacing a large part of
   the design corpus.
2. **Observability specification** (`/design/architecture/observability.md` or
   `/design/specs/observability.md`): The structured log format, diagnostic counters,
   status snapshot contract, and run-ID threading are spec-grade material that does not
   fit into any current proposed target.

### What requires new authoring (gaps, not misplacement)

See Section 6. The highest-priority items for authoring are:

1. `design/architecture/state-machine.md` — Critical (see Sufficiency Report)
2. `migrations/` directory and contents — Critical (see Sufficiency Report)
3. `design/architecture/invariants.md` — High
4. `design/domain/glossary.md` — High
5. `docs/deployment/versioning-policy.md` + upgrade guide — Medium

### Structural defects to fix immediately (housekeeping, no content work)

1. Rename old misnamed security file → `audit/security-threat-model.md` ✅ done
2. Rename old misnamed open-points directory → `audit/open-points/` ✅ done
3. Author or remove the three empty stub files in `audit/`
