# Technology Choices and Tradeoffs

**Status:** active (partial — tech stack section extracted from domain-architecture-overview.md §8)  
**Source:** extracted from `design/domain-architecture-overview.md` §8  
**See also:** [domain/constraints.md](../domain/constraints.md), [architecture/data-flow.md](../architecture/data-flow.md)

---

## Tech Stack Rationale

| Component | Choice | Justification |
|---|---|---|
| Language | Python 3.11+ | Matches nightfall-mcp conventions; stdlib-first; full type hints |
| HTTP client | `httpx` | Streaming / chunked download support; better timeout control than `requests` |
| OAuth2 / token lifecycle | `msal` | Microsoft's official Python library; device-code flow; transparent token refresh; serializable cache |
| Registry | `sqlite3` (stdlib) | ACID transactions; no extra deps; auditable via SQL; portable |
| Schema types | `TypedDict` (stdlib) | Matches nightfall-mcp style — no Pydantic dependency |
| Logging | `logging` + JSON formatter | Structured English logs; feeds journald via stdout |
| Process model | systemd timer + `.path` unit inside `photo-ingress` LXC | Matches current production/staging deployment model |

**Runtime dependencies:** `httpx`, `msal`  
**Dev dependencies:** `pytest`, `pytest-mock`

---

## Key Design Tradeoffs

### SQLite over a network database

SQLite was chosen for the registry over a network database (e.g. PostgreSQL) because:
- No extra infrastructure dependencies — the service runs inside a single LXC container.
- ACID transactions with WAL mode provide sufficient concurrency for the single-writer, single-process model.
- Registry data is small (file metadata only); no performance requirement for a server DB.
- `PRAGMA integrity_check` and ZFS snapshots provide the backup/recovery story.

The tradeoff: the registry cannot be accessed concurrently across containers. This is an accepted constraint; all ingest operations are serialized through the process lock.

### stdlib-first (TypedDict, no Pydantic)

The project is stdlib-first to minimize the dependency surface. `TypedDict` provides static typing without a runtime validation library. The tradeoff is less ergonomic validation at runtime, mitigated by explicit `config_version` gating and startup validation in `config.py`.

### Delegated auth only (no client secret)

The service uses delegated (user-context) OAuth2 with device-code flow and MSAL token refresh. A client secret is explicitly not used, which means:
- No credential rotation management.
- Auth is tied to a user identity; if the user account is deactivated, the token refresh will fail.
- `auth_failure_threshold` monitoring and `auth_failed` status state provide the operator signal.

### No Immich write path

Immich has no write path to the ingest queue by design. Immich scans the permanent library as a read-only external library. The tradeoff is that a new file in `accepted/` is not visible in Immich until the operator manually moves it to the permanent library and Immich completes a library scan.

---

## WAL Mode

SQLite WAL (Write-Ahead Log) mode is enabled at first `initialize()` call and is the
only supported journal mode for the registry. WAL was chosen over the default rollback
journal for two reasons:

1. **Concurrent reads during writes.** WAL allows readers to proceed without blocking
   while a write transaction is in progress. This matters when the CLI (e.g. `status`)
   reads the registry concurrently with a running poll service.
2. **Better write throughput for append-heavy workloads.** The `audit_log` table
   accumulates one row per ingest decision per file. WAL appends are faster than
   rollback-journal writes for this pattern.

The tradeoff: WAL mode creates additional checkpoint files (`-wal`, `-shm`) alongside
`registry.db`. These must be preserved in any backup or ZFS snapshot to maintain
registry consistency. ZFS snapshot semantics (crash-consistent point-in-time) naturally
capture all three files together.

ADL reference: implied by DEC-20260331-02 (storage topology rationale).

---

## Adapter Extensibility Pattern

The `adapters/` layer is designed as a collection of pluggable source connectors. The
domain layer (`domain/`) is source-agnostic; it accepts a
`DownloadedHandoffCandidate` dataclass from any adapter and applies the same policy
matrix regardless of origin.

The tradeoff this design accepts:

- **More indirection at the M3 → M4 boundary.** The `DownloadedHandoffCandidate`
  dataclass is the explicit contract between the adapter and the domain. Adding a
  new adapter requires authoring this contract for the new source.
- **No shared state between adapters.** Each adapter manages its own token cache, delta
  cursor, and retry policy. There is no cross-adapter scheduling or quota management.
  This is an accepted constraint for the current single-adapter deployment.
- **Future adapters must match the same handoff contract.** The domain layer is
  extensible by adding a new `adapters/<provider>/` subtree and wiring it into the
  CLI orchestrator. No changes to `domain/` are required.

This pattern was specifically chosen to avoid the tight coupling of the pre-refactor
monolithic layout, where OneDrive specifics were entangled with domain policy.

ADL reference: DEC-20260403-02 in `design/architecture-decision-log.md`.

---

## Systemd Timer vs. Daemon Architecture

The service runs as a **systemd one-shot timer** (invoked by
`nightfall-photo-ingress.timer`) rather than as a long-running daemon. This is a
deliberate tradeoff:

**Advantages of the timer model:**
- Clean process state per poll run — no accumulated in-memory state, no memory leaks
  over weeks of operation.
- Systemd handles scheduling, restart on failure, and dependency ordering without
  any in-process scheduler code.
- Simpler operational model: `systemctl start nightfall-photo-ingress.service` runs
  one poll immediately; no daemon lifecycle commands needed.
- The `Type=oneshot` + process lock combination means concurrent invocations
  (timer + manual CLI) are handled safely without daemon-specific logic.

**Tradeoffs accepted:**
- Per-invocation startup overhead (Python interpreter, MSAL cache load, SQLite open).
  This is negligible given the 8–24 hour poll cadence.
- No in-process event queue — a file arriving between polls is not seen until the next
  scheduled poll. This is acceptable because OneDrive sync latency is already measured
  in minutes.
- The trash-watch path unit (`nightfall-photo-ingress-trash.path`) runs as a separate
  always-on systemd path unit to provide near-real-time rejection response. This
  partially compensates for the timer-and-exit model.

ADL reference: DEC-20260403-02 (process model context); deployment model described in
`design/domain-architecture-overview.md` §8.

---

*For full system constraints, see [domain/constraints.md](../domain/constraints.md).*  
*For architecture decision log, see [architecture-decision-log.md](../architecture-decision-log.md).*
