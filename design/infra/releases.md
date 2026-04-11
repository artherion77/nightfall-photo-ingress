# Staging Release Versioning and Rollback (Phase 2 C4)

Status: Active
Date: 2026-04-11
Owner: Systems Engineering

## 1. Purpose

Define deterministic artifact versioning and rollback behavior for Phase-2 staging deployment.

Scope:
- versioned backend wheel + web build artifacts
- active release mapping
- deterministic rollback execution and validation

Out of scope:
- production deployment orchestration
- host-level service mutation outside staging release directories

## 2. Release Directory Strategy

Release artifacts are stored under repository-local release directories:

- Root: `artifacts/releases`
- Versioned releases: `artifacts/releases/versions/<release-id>/`
- Active release pointer: `artifacts/releases/active` (symlink to `versions/<release-id>`)
- Release audit log: `artifacts/releases/release-events.jsonl`

Each release directory contains:

- `backend/<wheel>.whl`
- `webui/build/` (static web build)
- `manifest.json` with release id, timestamp, and artifact hashes

## 3. Install Flow (Deploy from Versioned Artifacts)

`stagingctl install [wheel]` always performs:

1. Materialize a new versioned release from wheel + `webui/build`.
2. Switch active release mapping to the new release id.
3. Deploy wheel and web assets from that versioned release only.
4. Validate and restart in-container services.
5. Refresh clean snapshot and append release audit events.

This ensures staging deploys are auditable and reproducible from immutable release directories.

## 4. Rollback Flow

`stagingctl rollback <release-id>` performs deterministic rollback:

1. Verify target release exists in `artifacts/releases/versions/`.
2. Switch active release symlink to target release.
3. Redeploy artifacts from target release.
4. Validate API service, Caddy service, and config-check.
5. Append rollback start/validation events to release audit log.

## 5. Constraints and Invariants

1. Host mutation is limited to `artifacts/releases/**` for release-state changes.
2. Evidence and log behavior is unchanged and remains host-persistent by existing policy.
3. Staging container remains the only deployment target for Phase 2.

## 6. Validation Checklist

1. `stagingctl install` creates a new `versions/<release-id>` directory with manifest and both artifact classes.
2. `artifacts/releases/active` points to the deployed release id.
3. `stagingctl rollback <release-id>` switches active mapping, redeploys, and validates services/config.
4. `release-events.jsonl` contains release creation, active switch, deploy, and rollback validation events.