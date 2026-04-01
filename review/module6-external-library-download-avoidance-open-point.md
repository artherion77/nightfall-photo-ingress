# Module 6 External Library Download Avoidance Open Point

Status: Open
Date: 2026-04-01
Owner: Systems Engineering

## Summary

The current Module 6 implementation imports advisory SHA1 data from read-only `.hashes.sha1` files in the permanent library and falls back to re-hashing directories for import when those files are missing or invalid.

That import layer is complete, but the runtime optimization layer is intentionally not implemented yet.

## Open Point

We need a reliable way to skip downloading more than 80-90% of files from the Microsoft Graph API when that content is already present in the external library.

This must be wired and hardened only after the remaining relevant modules are in place.

## Why This Is Still Open

The current runtime path does not yet safely connect all required pieces:

- OneDrive boundary payloads are not yet carrying the advisory hash metadata needed for this decision path.
- Ingest currently trusts canonical server-side SHA-256 and metadata-index history, not advisory external-library hash matches.
- `verify_sha256_on_first_download` requires a deliberate one-time verification workflow, not a shortcut.
- A partial implementation would risk false skips and silent data loss or missed ingest events.

## Required Future Work

1. Extend the Graph candidate model to capture and propagate advisory hash metadata when available.
2. Add an advisory prefilter stage that checks imported external-library hash cache entries before download.
3. Implement the `verify_sha256_on_first_download` state transition safely:
   - advisory match found
   - one verification download performed when required
   - verified SHA-256 persisted for future authoritative skip behavior
4. Add hardening and integration tests for:
   - cache hit skip behavior
   - one-time verification behavior
   - false-positive protection
   - poll-after-import download reduction
   - multi-account correctness

## Acceptance Target

This open point is closed only when the system can reliably avoid downloading the large majority of already archived files from Graph API in normal operation, while preserving canonical SHA-256 authority and auditability.

## Current Constraint

Until this is implemented, sync-import should be treated as registry preparation work only, not as a complete download-avoidance optimization.
