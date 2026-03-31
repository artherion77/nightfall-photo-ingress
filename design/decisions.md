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
