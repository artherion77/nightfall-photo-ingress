# Refinement List for photo-ingress
This document synthesizes all refinement requirements derived from the architectural plan, user constraints, and structural analysis. Claude Code should use this list to refine the architecture, validate assumptions, and guide implementation decisions.

---

## 0. Naming and Adapter Policy

- Primary service/project name: `photo-ingress`.
- Current source adapter name: `onedrive`.
- Canonical datasets and mountpoints:
  - `ssdpool/photo-ingress` → `/mnt/ssd/photo-ingress`
  - `nightfall/media/photo-ingress` → `/nightfall/media/photo-ingress`
- Permanent library boundary remains `/nightfall/media/pictures`.

---

## A. Configuration & System Boundaries

### A1 — Central Versioned Configuration File
- Use a single INI-based configuration file.
- Support default values and strict validation.
- Include `config_version` and implement schema migration logic.
- Document all keys clearly.
- Configuration must define:
  - OneDrive accounts
  - Storage templates
  - ZFS paths (staging, accepted, trash)
  - Token cache paths
  - Delta cursor paths
  - Logging configuration
  - Move strategy (same-pool vs cross-pool)
  - Poll interval

### A2 — Multi-User / Multi-Account Support
- Support multiple OneDrive personal accounts.
- Each account has:
  - Its own token cache
  - Its own delta cursor
- All accounts share a global SHA-256 registry.
- Add an account-to-file mapping table for auditability.

### A3 — Configurable Storage Template
- Default template: `{yyyy}/{mm}/{sha8}-{original}`
- Template engine must support:
  - `{yyyy}`, `{mm}`, `{dd}`
  - `{sha256}`, `{sha8}`
  - `{original}`
  - `{account}`

### A4 — Accepted Queue vs Permanent Library Boundary
- `accepted_path` is an ingress queue, not the permanent library.
- Operator manually moves files from `accepted_path` to `/nightfall/media/pictures/...` outside ingress visibility.
- Ingress must preserve acceptance history in the registry so manual moves do not trigger re-downloads.

---

## B. Registry & Data Model

### B1 — Registry Schema Versioning
- Use `PRAGMA user_version` for schema versioning.
- Provide migration scripts for future schema changes.
- Keep audit_log append-only and immutable.

### B2 — Global Registry
- Maintain a single global registry for all accounts.
- Track file status: accepted, rejected, purged.
- Maintain metadata_index for fast pre-filtering.
- Maintain audit_log for all state transitions.
- Add an accepted provenance table to persist account/source metadata for accepted hashes even if files leave `accepted_path`.

### B3 — Concurrency Control
- Use SQLite EXCLUSIVE transactions for registry writes.
- Ensure poll runs are serialized across accounts.
- Implement a global lock to avoid race conditions.

---

## C. Token & Secret Management

### C1 — Hardened Token Cache
- Use MSAL SerializableTokenCache.
- Store token cache files with mode 0600.
- Avoid environment variables or keyring dependencies.
- Consider optional age-encrypted token caches in the future.

### C2 — Multi-Account Token Lifecycle
- Each account uses its own token cache.
- Detect and alert on:
  - Authentication failures
  - Refresh failures
  - Repeated failures (≥3 consecutive)

---

## D. Pipeline Robustness

### D1 — Delta Cursor Robustness
- Maintain one delta cursor per account.
- On cursor loss:
  - Try delta recovery with latest link bootstrap
  - Then optional bounded backfill (for example 30-day scope)
  - Fall back to full rescan as last resort
- Registry idempotency must guarantee safety.

### D2 — Backpressure & Rate Limiting
- Limit number of downloads per poll run.
- Limit maximum runtime per poll run.
- Implement exponential backoff for retries.
- Handle OneDrive rate limits gracefully.

### D3 — Staging Cleanup Policy
- TTL for `.tmp` files.
- TTL for failed downloads.
- TTL for orphaned files.

### D4 — Cross-Pool Atomicity
- If staging and accepted are on different pools:
  - Use copy2 → verify → unlink.
- Add config flag: `staging_on_same_pool = false`.

---

## E. Observability & Health

### E1 — Health State Machine
Define explicit states:
- healthy
- degraded
- auth_failed
- disk_full
- ingest_error
- registry_corrupt

### E2 — Status Export
- Write status JSON to:
  `/run/nightfall-status.d/photo-ingress.json`
- Must be compatible with nightfall-mcp HealthService.

### E3 — Structured Logging
- JSON logs by default for systemd service execution.
- Optional human log format for interactive CLI debugging.
- Include context fields:
  - sha256
  - account
  - filename
  - status
  - action

---

## F. Immich Independence

### F1 — Dedicated Container
- V1 runs as host-level Python service managed by systemd.
- No dependency on Immich container internals.
- No dependency on Immich ingest logic.
- Containerization is deferred to V2.

### F2 — External Library as Read-Only Source
- Immich reads only from permanent library (`/nightfall/media/pictures/...`).
- Ingress does not write directly to Immich-visible library.
- Immich DB purges or upgrades must not affect ingest.
- Immich is not part of the ingest authority.

---

## G. Media-Specific Considerations

### G1 — Video Support
- Support MOV, MP4, HEVC.
- Use chunked streaming for large files.
- Hashing identical to photos.

### G2 — Live Photo Support in V1
- Live Photo support is required in V1.
- Detect and track paired assets (typically HEIC/JPEG + MOV).
- Keep components as separate physical files while preserving pair metadata for search/audit.
- Optional merge/export workflows are deferred to V2.

### G3 — Hash Sync Import from Permanent Library
- Provide CLI-driven sync mode that imports known hashes from read-only permanent library data.
- Reuse existing `.hashes.sha1` artifacts generated by `nightfall-immich-rmdups.sh` to reduce compute and avoid full re-hashing.
- Sync import must pre-seed accepted records to avoid unnecessary OneDrive downloads.

---

## H. CLI Extensions

### H1 — Account-Aware CLI
- Support:
  - `--account <name>`
  - `--all-accounts`
- Reject command must be account-agnostic.

### H2 — Dry-Run Mode
- No registry writes.
- No file operations.
- Full decision logging.

---

## I. Summary
This refinement list defines the structural, architectural, and operational requirements needed to finalize the design of the photo-ingress service. Claude Code should use this as the authoritative checklist for architecture refinement and implementation planning.
