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

*For full system constraints, see [domain/constraints.md](../domain/constraints.md).*  
*For architecture decision log, see [architecture-decision-log.md](../architecture-decision-log.md).*
