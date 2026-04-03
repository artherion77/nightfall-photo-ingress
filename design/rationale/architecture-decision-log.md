# photo-ingress Design Decisions Log

Status: active
Last Updated (UTC): 2026-04-03 00:00:00 UTC

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
- Status: superseded
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
- Superseded by:
  - DEC-20260403-01 (CLI naming portion only; service/data path naming unchanged)
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

## DEC-20260403-01: CLI and systemd unit naming finalization
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: naming
- Decision:
  - The installed CLI command is `nightfall-photo-ingress` (not `photo-ingress`).
  - systemd units use the `nightfall-` prefix throughout:
    - `nightfall-photo-ingress.service` (poll run, invoked by timer)
    - `nightfall-photo-ingress.timer` (scheduled activation)
    - `nightfall-photo-ingress-trash.path` (inotify watch on trash directory)
    - `nightfall-photo-ingress-trash.service` (processes trash events)
  - Service-level naming (config path, status file, ZFS dataset) retains `photo-ingress`
    without the `nightfall-` prefix.
- Rationale:
  - Binary names published to `$PATH` carry the `nightfall-` prefix for consistency
    with all other nightfall tooling (`nightfall-zfs-snapshot-*`,
    `nightfall-health-report`, etc.) and to avoid collision with any upstream
    `photo-ingress` package in system package managers.
  - Config and data paths (`/etc/nightfall/photo-ingress.conf`,
    `/mnt/ssd/photo-ingress`, `/run/nightfall-status.d/photo-ingress.json`) omit
    the prefix to keep paths concise and readable in operator workflows.
- Alternatives Considered:
  - `photo-ingress` for all names (original DEC-20260331-01 intent).
  - `nightfall-photo-ingress` for all names including config paths.
- Consequences:
  - DEC-20260331-01 is partially superseded: the service-level naming policy
    (`photo-ingress`) is retained; the CLI/unit naming policy changes to
    `nightfall-photo-ingress`.
  - `design/domain-architecture-overview.md` §1.1 is corrected to reflect
    actual installed names.
- Implementation Notes:
  - `pyproject.toml` console_scripts entry:
    `nightfall-photo-ingress = "nightfall_photo_ingress.cli:main"`
  - Operator docs must always use `nightfall-photo-ingress` for all
    invocation examples; never abbreviate to `photo-ingress`.
- Supersedes:
  - DEC-20260331-01 (CLI naming portion only; service/data path naming unchanged)
- References:
  - `pyproject.toml`
  - `systemd/nightfall-photo-ingress.service`
  - `systemd/nightfall-photo-ingress.timer`
  - `systemd/nightfall-photo-ingress-trash.path`
  - `systemd/nightfall-photo-ingress-trash.service`
  - `design/domain-architecture-overview.md` (§1.1)

## DEC-20260403-02: Domain/adapters/runtime module separation
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: other
- Decision:
  - Refactor package layout from monolithic `onedrive/` and `pipeline/` subdirectories
    into a three-layer structure:
    - `domain/` — pure business logic; no adapter dependencies
      (registry, ingest, storage, journal)
    - `adapters/onedrive/` — Microsoft Graph/MSAL integration; isolated source-adapter
      (auth, client, retry, cache_lock, errors, safe_logging)
    - `runtime/` — process lifecycle helpers not specific to any adapter
      (process_lock)
  - Top-level CLI modules (`poll.py`, `accept.py`, `reject.py`, `purge.py`,
    `process_trash.py`, `sync_import.py`, `status_export.py`, `config_check.py`)
    remain at the package root and are thin orchestrators only.
- Rationale:
  - The monolithic layout entangled OneDrive specifics with domain logic, making
    the boundary opaque and the domain layer difficult to test without mocking
    adapter internals.
  - A future source adapter (e.g. local-path, S3) can be added under
    `adapters/<provider>/` without touching `domain/`.
  - The `runtime/` layer provides shared lifecycle helpers (process lock) that
    are not OneDrive-specific.
- Alternatives Considered:
  - Continue with monolithic layout and rely on import discipline.
  - Full hexagonal ports-and-adapters with explicit interface protocols.
- Consequences:
  - All domain unit tests can be run without any MSAL/httpx imports.
  - Adapter integration tests are isolated under `tests/integration/`.
  - Adding a second source adapter requires only a new `adapters/<provider>/`
    subtree and CLI orchestration.
- Implementation Notes:
  - The domain layer must never import from `adapters/`.
  - The `DownloadedHandoffCandidate` dataclass (in `adapters/onedrive/client.py`)
    is the M3→M4 boundary contract; domain `IngestDecisionEngine` accepts it as
    opaque input.
- Supersedes:
  - none
- References:
  - `src/nightfall_photo_ingress/domain/`
  - `src/nightfall_photo_ingress/adapters/onedrive/`
  - `src/nightfall_photo_ingress/runtime/`
  - `design/domain-architecture-overview.md` (§9 File Layout)
  - `ARCHITECTURE.md`

## DEC-20260403-03: Append-only JSONL lifecycle journal for crash recovery
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: pipeline
- Decision:
  - Maintain a separate JSONL append-only journal (`IngestOperationJournal`) alongside
    the SQLite `audit_log` for crash-boundary operation recovery.
  - The journal records phase transitions (`download_started`, `hash_computed`,
    `decision_applied`, `finalized`) for each ingest operation.
  - Each write is durable: `handle.flush()` + `os.fsync()` before returning.
  - Journal rotates at `max_bytes` (default 5 MB), renaming to `.1` before restarting.
  - On startup, `reconcile_interrupted_operations()` reads all journal records and
    replays any operation that reached `hash_computed` or `decision_applied` but
    not `finalized`.
- Rationale:
  - The SQLite registry cannot detect partially-completed multi-step operations:
    a file may be moved to `pending_path` but the registry row commit may not
    have followed due to a crash. The journal provides a lighter-weight phase
    marker that survives the crash and enables correct replay.
  - Replay is safe because all downstream registry operations use
    `ON CONFLICT DO UPDATE` and `INSERT OR IGNORE` guards.
  - Keeping the journal separate from the audit_log avoids locking the registry
    database during the recovery scan at startup.
- Alternatives Considered:
  - SQLite-only recovery using a `status='in_progress'` sentinel row.
  - Two-phase commit with a separate `staging_ops` table in the registry.
- Consequences:
  - The journal file path must be configured (`journal_path`); if absent, the
    journal is disabled and crash recovery falls back to manual staging reconciliation.
  - Zero-byte files discovered during replay are quarantined (not silently discarded)
    with an audit record written.
  - The journal is ephemeral crash-boundary state; the audit_log remains the
    authoritative permanent record.
- Implementation Notes:
  - `IngestOperationJournal.append()` is called at each phase boundary.
  - Each `JournalRecord` carries: `op_id`, `phase`, `ts` (UTC ISO-8601),
    `account`, `onedrive_id`, `staging_path`, `destination_path`, `sha256`.
  - The journal file is stored under the staging working directory, not under
    the permanent library.
- Supersedes:
  - none
- References:
  - `src/nightfall_photo_ingress/domain/journal.py`
  - `design/domain-architecture-overview.md` (§14 Ingest Lifecycle Journal)

## DEC-20260403-04: URL and token redaction at all adapter raise sites
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: security
- Decision:
  - All exception raise sites in the OneDrive adapter must call `redact_url()`
    before attaching a URL to an exception message, `safe_hint`, or log record.
  - `redact_url()` contract:
    1. If the URL contains a query string, strip it entirely and append
       ` [query redacted]` to the base URL.  Pre-authenticated OneDrive download
       URLs embed bearer tokens in query parameters (`tempauth`, `sig`, `sv`, `sp`,
       etc.).
    2. Base URL (netloc+path) is truncated to 80 chars for readability.
    3. Never raises; returns fixed sentinels `<empty-url>` or `<unparseable-url>`
       on degenerate input.
  - Safe (no query string) URLs are passed through up to 120 chars.
  - `redact_token()` is used for access tokens: shows only the first 6 chars and
    total length.
  - `sanitize_extra()` (`adapters/onedrive/safe_logging.py`) strips any `extra=`
    dict key matching known credential patterns before it reaches the logging
    handler.
- Rationale:
  - Pre-authenticated OneDrive/SharePoint download URLs carry full bearer material
    in query strings. Any unredacted URL in a log line, exception message, or
    traceback constitutes a credential leak.
  - Enforcing redaction at raise sites (not at log-format time) ensures the URL
    is safe regardless of how the exception is later logged or surfaced.
- Alternatives Considered:
  - Log-formatter-level redaction (fragile: depends on all paths routing through
    the filterer).
  - Avoid storing URLs in exceptions at all (loses diagnostically useful domain
    information).
- Consequences:
  - Every `GraphError`, `DownloadError`, or `AuthError` raised with a URL must
    use `redact_url()` before passing the URL.
  - Code review and testing must verify no raw pre-authenticated URLs appear in
    exception messages, `str(exc)`, or log output.
- Implementation Notes:
  - `redact_url()` and `redact_token()` are defined in
    `src/nightfall_photo_ingress/adapters/onedrive/errors.py`.
  - `sanitize_extra()` is defined in
    `src/nightfall_photo_ingress/adapters/onedrive/safe_logging.py`.
  - The `_SECRET_PARAMS` regex in `errors.py` enumerates the full set of
    redaction targets as documentation; the actual redaction strips the entire
    query string (belt-and-suspenders).
- Supersedes:
  - none
- References:
  - `src/nightfall_photo_ingress/adapters/onedrive/errors.py`
  - `src/nightfall_photo_ingress/adapters/onedrive/safe_logging.py`
  - `design/domain-architecture-overview.md` (§15 Error Taxonomy and Resilience)

## DEC-20260403-05: Per-account singleton lock for concurrent poll safety
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: security
- Decision:
  - A non-blocking advisory file lock (`account_singleton_lock`) is acquired for
    each account before any MSAL token cache operation.
  - The lock is stored in a sibling `.runtime.lock` file in the token cache
    directory, separate from the cache file itself.
  - If the lock cannot be acquired (another process holds it), a
    `SingletonLockBusyError` is raised and the account is skipped for that run.
  - A separate `cache_file_lock` (blocking) serializes reads and writes of the
    MSAL cache file within a single process.
- Rationale:
  - The global process lock (`runtime/process_lock.py`) serialises poll runs
    within a single scheduled invocation but does not protect against an
    operator manually running a second poll concurrently in a separate shell.
  - MSAL's `SerializableTokenCache` is not safe for concurrent writers: two
    simultaneous writes will corrupt the cache. The per-account singleton lock
    closes this gap for cross-process scenarios.
  - A non-blocking acquire (LOCK_NB) is correct here: a busy lock means another
    process is actively using the account; the current run should skip that
    account rather than waiting.
- Alternatives Considered:
  - Rely solely on the global process lock (insufficient for manual concurrent usage).
  - Use a database row lock in the registry (adds RTT overhead for an in-process
    concern).
- Consequences:
  - If an operator runs two concurrent poll invocations, the second invocation
    skips all accounts currently locked by the first; no cache corruption occurs.
  - The lock is advisory (POSIX `fcntl.flock`): it provides no protection if a
    rogue process bypasses the lock entirely.
- Implementation Notes:
  - `account_singleton_lock(cache_path, lock_name=".runtime.lock")` in
    `src/nightfall_photo_ingress/adapters/onedrive/cache_lock.py`.
  - Lock granularity is per-account: accounts sharing no token cache directory
    do not contend.
  - Lock files are created automatically; they are never deleted (deletion between
    lock and use could allow races).
- Supersedes:
  - none
- References:
  - `src/nightfall_photo_ingress/adapters/onedrive/cache_lock.py`
  - `src/nightfall_photo_ingress/runtime/process_lock.py`
  - `design/domain-architecture-overview.md` (§7 Process Model and Concurrency)

## DEC-20260403-06: Separate development container lifecycle from staging
- Status: accepted
- Date (UTC): 2026-04-03 00:00:00 UTC
- Scope: other
- Decision:
  - Adopt a dedicated development container named `dev-photo-ingress`.
  - Keep staging container (`staging-photo-ingress`) focused on release-rehearsal
    validation (wheel-first install, smoke/live checks, evidence).
  - Prefer separate command surfaces for dev and staging lifecycle management,
    while sharing common orchestration helpers to avoid duplicated shell logic.
- Rationale:
  - Staging should remain policy-constrained and production-like; frontend dev
    toolchain churn (Node/npm, Vite, hot reload) increases drift risk.
  - A dedicated dev container allows fast iteration without forcing host-level
    Node/npm installation.
  - Distinct tools improve operator clarity: staging commands are operational
    contracts, dev commands are iterative workflows.
- Alternatives Considered:
  - Continue hosting web UI development in staging.
  - Keep a single controller (`stagingctl`) for both staging and dev workflows.
- Consequences:
  - Documentation now separates environment responsibilities across dev, staging,
    and production.
  - A new dev lifecycle controller is expected (proposed `dev/devctl`).
  - Shared helper extraction is required to prevent maintenance duplication between
    controllers.
- Implementation Notes:
  - Target-state docs: `design/architecture/environment-separation-and-container-lifecycle.md`
    and `docs/deployment/dev-container-workflow.md`.
  - Command implementation is deferred; this decision records the architecture
    boundary and migration direction first.
- Supersedes:
  - none
- References:
  - `design/architecture/environment-separation-and-container-lifecycle.md`
  - `docs/deployment/dev-container-workflow.md`
  - `staging/README.md`
  - `docs/deployment/environment-setup.md`
