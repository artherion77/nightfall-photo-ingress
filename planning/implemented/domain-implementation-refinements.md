# Refinement Requirements — Domain and CLI Layer

Status: Implemented (used as guide for Modules 0–4)
Date: 2026-03-31
Owner: Systems Engineering

Implementation status:
- This document was the implementation guide for CLI/domain Modules 0–4.
- Items A–F (configuration, registry, pipeline, observability, CLI, security) are reflected
  in the current codebase under `src/nightfall_photo_ingress/`.
- Web control plane refinements (API, UI) are addressed by `design/web/webui-architecture-phase1.md`,
  `design/web/web-control-plane-architecture-phase2.md`, and `design/web/web-control-plane-architecture-phase3.md`.
- This document is retained as the authoritative requirements record for the implemented domain layer.

---

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
- Process enabled accounts serially in deterministic declaration order from the configuration file.
- Add an account-to-file mapping table for auditability.

### A3 — Configurable Storage Template
- Default template: `{yyyy}/{mm}/{original}`
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
- Authoritative model: streaming page commit. Polling must process one page at a time, commit ingest side effects, then advance cursor.
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
- Pairing heuristics must be configurable in config with defaults:
  - `live_photo_capture_tolerance_seconds = 3`
  - `live_photo_stem_mode = exact_stem`
  - `live_photo_component_order = photo_first`
  - `live_photo_conflict_policy = nearest_capture_time`
- V1 implementation may only support these default values, but parser/validation must still expose the parameters.
- Optional merge/export workflows are deferred to V2.

### G3 — Hash Sync Import from Permanent Library
- Provide CLI-driven sync mode that imports known hashes from read-only permanent library data.
- Reuse existing `.hashes.sha1` artifacts generated by `nightfall-immich-rmdups.sh` to reduce compute and avoid full re-hashing.
- Sync import must pre-seed accepted records to avoid unnecessary OneDrive downloads.
- Add `verify_sha256_on_first_download = true` default so advisory SHA1 matches require one canonical server-side SHA-256 verification before long-term trust.

Design boundary note:
- SHA-256 remains the canonical registry identity key.
- When Microsoft Graph provides SHA-256 metadata for a file item, it may be used as canonical identity input.
- SHA1 (including sync-import advisory data) remains non-canonical unless explicitly verified against canonical SHA-256.

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
