# photo-ingress Design Decisions Log

Status: active
Last Updated (UTC): 2026-03-31 16:03:18 UTC

---

## 1. Purpose

This file records iterative architecture and implementation decisions for photo-ingress.
Each decision is written as an append-only record to keep rationale and change history auditable.

---

## 2. Record Format (Extensible)

Use one section per decision with the following fields.

### Template

```md
## DEC-YYYYMMDD-XX: <short-title>
- Status: proposed | accepted | superseded | rejected
- Date (UTC): YYYY-MM-DD HH:MM:SS UTC
- Scope: naming | storage | registry | pipeline | observability | security | other
- Decision:
  - <what is being decided>
- Rationale:
  - <why this is the selected option>
- Alternatives Considered:
  - <option A>
  - <option B>
- Consequences:
  - <positive/negative effects>
- Implementation Notes:
  - <concrete constraints for docs/code>
- Supersedes:
  - <decision id or none>
- References:
  - <file paths, issue ids, or links>
```

Field notes:
- `DEC-YYYYMMDD-XX` is sequential for the day.
- Keep entries immutable; when a decision changes, add a new entry and mark the old one `superseded`.
- `References` should point to affected design documents and implementation files.

---

## 3. Decision Records

## DEC-20260331-01: Primary service naming policy
- Status: accepted
- Date (UTC): 2026-03-31 16:03:18 UTC
- Scope: naming
- Decision:
  - Use `photo-ingress` as the primary project and service name.
  - Keep `onedrive` explicit as the source adapter name.
- Rationale:
  - `photo-ingress` is concise and remains valid if future source adapters are added.
  - Explicit adapter naming avoids ambiguity in account config and module boundaries.
- Alternatives Considered:
  - `onedrive-ingress`
  - `onedrive-photo-ingress`
- Consequences:
  - Service, config, status file, and path naming align to `photo-ingress`.
  - Adapter-specific fields remain adapter-scoped (`provider=onedrive`, `onedrive_root`).
- Implementation Notes:
  - CLI command is `photo-ingress`.
  - Config path is `/etc/nightfall/photo-ingress.conf`.
- Supersedes:
  - none
- References:
  - `design/architecture.md`
  - `design/configspec.md`
  - `design/refinements.md`
  - `design/v1-baseline-spec.md`

## DEC-20260331-02: Canonical storage and dataset/container naming
- Status: accepted
- Date (UTC): 2026-03-31 16:03:18 UTC
- Scope: storage
- Decision:
  - Standardize storage naming to:
    - `ssdpool/photo-ingress` mounted at `/mnt/ssd/photo-ingress`
    - `nightfall/media/photo-ingress` mounted at `/nightfall/media/photo-ingress`
  - Keep permanent library root at `/nightfall/media/pictures`.
- Rationale:
  - Provides clear separation between always-on ingest state and operator-controlled media boundaries.
  - Aligns path names with service naming and reduces operator confusion.
- Alternatives Considered:
  - Keep legacy `* /onedrive-ingress` naming for datasets and paths.
- Consequences:
  - Existing docs and examples must use the canonical `photo-ingress` paths.
  - Migration plan may be needed if legacy datasets already exist.
- Implementation Notes:
  - `accepted/` and `trash/` remain under `/nightfall/media/photo-ingress`.
  - Ingress remains read-only with respect to `/nightfall/media/pictures`.
- Supersedes:
  - none
- References:
  - `design/architecture.md`
  - `design/configspec.md`
  - `design/v1-baseline-spec.md`

## DEC-20260331-03: Accepted queue boundary and dedupe persistence
- Status: accepted
- Date (UTC): 2026-03-31 16:03:18 UTC
- Scope: pipeline
- Decision:
  - `accepted_path` is an ingress queue only.
  - Operator manually moves files into permanent library.
  - Registry must persist acceptance history so moved files are never re-downloaded.
  - CLI `sync-import` reuses existing `.hashes.sha1` files from the permanent library to pre-seed dedupe.
- Rationale:
  - Keeps ingest authority and permanent library ownership clearly separated.
  - Preserves dedupe safety despite manual move workflows and limited ingress permissions.
- Alternatives Considered:
  - Direct auto-copy by ingress into permanent library.
  - Re-hash full permanent library periodically.
- Consequences:
  - Requires accepted provenance records and advisory external hash cache import.
  - Sync-import becomes an operational task in initial rollout.
- Implementation Notes:
  - Canonical hash identity remains server-computed SHA-256.
  - Imported SHA1 remains advisory for pre-filtering.
- Supersedes:
  - none
- References:
  - `design/architecture.md`
  - `design/configspec.md`
  - `design/v1-baseline-spec.md`
  - `design/refinements.md`

## DEC-20260331-04: Deterministic multi-account order and Live Photo/SHA1 anti-drift config defaults
- Status: accepted
- Date (UTC): 2026-03-31 18:00:00 UTC
- Scope: pipeline
- Decision:
  - Process enabled accounts serially in declaration order from the config file.
  - Expose Live Photo pairing heuristics as configuration parameters with defaults:
    - `live_photo_capture_tolerance_seconds = 3`
    - `live_photo_stem_mode = exact_stem`
    - `live_photo_component_order = photo_first`
    - `live_photo_conflict_policy = nearest_capture_time`
  - Add `verify_sha256_on_first_download = true` default to protect against advisory SHA1 collisions.
- Rationale:
  - Prevent implementation drift by encoding ordering and heuristics as explicit contract.
  - Keep V1 behavior stable while preserving forward-compatible configuration surface.
  - Ensure canonical identity remains server-side SHA-256 even when using imported SHA1 caches for optimization.
- Alternatives Considered:
  - Deterministic but sorted account order instead of config declaration order.
  - Hard-coded Live Photo heuristics without config surface.
  - Trust imported SHA1 cache without first-download SHA-256 verification.
- Consequences:
  - Config parser must preserve declaration order and validate new keys.
  - V1 may still enforce default heuristic values while exposing parameters.
  - Sync-import path must branch behavior based on verification flag.
- Implementation Notes:
  - OneDrive/account loops should not reorder enabled accounts.
  - Advisory SHA1 matches are never canonical identity; SHA-256 remains the source of truth.
- Supersedes:
  - none
- References:
  - `design/configspec.md`
  - `design/v1-baseline-spec.md`
  - `design/refinements.md`
  - `planning/iterative-implementation-roadmap.md`

## DEC-20260402-01: Pending-first ingest with explicit accept and purge workflows
- Status: accepted
- Date (UTC): 2026-04-02 00:00:00 UTC
- Scope: pipeline
- Decision:
  - Ingest no longer auto-accepts unknown files.
  - Unknown files transition to `pending` with files written to `pending_path`.
  - Operator `accept` transitions `pending -> accepted` and writes `accepted_records`.
  - Operator `reject` moves files to `rejected_path` (trash-like retention).
  - Operator `purge` transitions `rejected -> purged` and removes retained files.
- Rationale:
  - Makes operator intent explicit and auditable.
  - Avoids silently promoting new data into accepted state.
  - Adds safe retention for rejected files before irreversible deletion.
- Alternatives Considered:
  - Keep auto-accept as ingest default.
  - Delete rejected files immediately on reject.
- Consequences:
  - Registry schema expands status model with `pending` and migration support.
  - Ingest terminal events report `pending` for unknown hashes.
  - Config requires/uses separate queue roots and templates for pending and accepted flows.
- Implementation Notes:
  - `storage_template` is used for pending placement.
  - `accepted_storage_template` is used only by explicit accept transitions.
  - `rejected_path` retains artifacts until explicit purge/manual deletion.
- Supersedes:
  - none
- References:
  - `src/nightfall_photo_ingress/domain/registry.py`
  - `src/nightfall_photo_ingress/domain/ingest.py`
  - `src/nightfall_photo_ingress/reject.py`
  - `src/nightfall_photo_ingress/cli.py`
  - `design/configspec.md`
