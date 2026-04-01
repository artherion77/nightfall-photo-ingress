# photo-ingress Web Control Plane Architecture Extension

Status: Proposed
Date: 2026-04-01
Owner: Systems Engineering

## 1. Intent

This extension introduces an operator-facing web control plane for staging visibility and triage, built as:
- Backend: FastAPI service exposing a versioned API
- Frontend: Svelte SPA for timeline, triage, and blocklist workflows

The extension is additive. It does not replace CLI or timer-based ingest execution.

## 2. Non-Goals

- No direct writes from UI/API to permanent library roots.
- No replacement of systemd-driven poll scheduling in V1.
- No AI-based auto-classification in initial rollout.
- No bypass of existing ingest domain decision and registry transaction rules.

## 3. Invariants To Preserve

- Registry authority remains the source of truth for status and history.
- Mutating actions are idempotent and audit-first.
- Permanent library path is out of bounds for web control plane writes.
- Operator actions must be reconstructable from immutable audit events.

## 4. Bounded Architecture

## 4.1 Components

- `photo-ingress-core` (existing): config, registry, ingest decision engine, storage policy, adapters
- `photo-ingress-api` (new): FastAPI boundary, request validation, auth, response shaping
- `photo-ingress-ui` (new): Svelte operator interface
- `thumbnail-worker` (new, optional in phase 2+): on-demand thumbnail generation and disk cache

## 4.2 Backend Layering

1. API routers accept requests and perform auth/rate-limit checks.
2. Application services translate requests into domain-level operations.
3. Domain operations execute transactional writes through existing registry/storage primitives.
4. Audit append happens before state transition commit for mutating actions.

## 4.3 Frontend Layering

- Route-level pages: staging, timeline, item detail, blocklist
- State management: optimistic UI only when idempotency key is present
- Actions: explicit confirmation for destructive operations
- Accessibility: keyboard-first list and triage controls

## 5. API Surface (v1)

All API routes are under `/api/v1`.

Read-only endpoints:
- `GET /health`
- `GET /staging?cursor=&limit=&status=`
- `GET /items/{item_id}`
- `GET /audit-log?cursor=&limit=&action=&actor=`
- `GET /config/effective`
- `GET /blocklist`

Mutating endpoints:
- `POST /triage/{item_id}/accept`
- `POST /triage/{item_id}/reject`
- `POST /triage/{item_id}/defer`
- `POST /metadata/{item_id}/sidecar-fetch`
- `POST /blocklist`
- `PATCH /blocklist/{rule_id}`
- `DELETE /blocklist/{rule_id}`

Mutating request requirements:
- Header `X-Idempotency-Key` is mandatory.
- Response includes stable action correlation id.
- Server returns prior result on duplicate idempotency key.

## 6. Data Model Extension

This extension does not alter existing `files` and `audit_log` semantics. It adds optional support tables:

- `ui_action_idempotency`
  - key, actor, request_hash, response_blob, created_at, expires_at
- `sidecar_jobs`
  - id, item_id, state (`queued|running|done|failed`), attempts, last_error, created_at, updated_at
- `blocked_rules`
  - id, pattern, pattern_type, reason, enabled, created_by, created_at, updated_at
- `thumbnails`
  - item_id, cache_key, width, height, mime_type, path, created_at, expires_at

All new tables are migration-gated and backward compatible.

## 7. Security Model

Initial deployment profile:
- LAN-only bind address.
- Static token auth (header bearer token) for operator sessions.
- CORS allowlist limited to configured UI origin.

Required controls:
- Input validation for all query/path/body parameters.
- Per-route rate limiting for mutating endpoints.
- Structured audit for auth failures and permission denials.
- Redaction policy for tokens, credentials, and external URLs in logs.

Deferred controls:
- OIDC/OAuth operator SSO.
- Fine-grained RBAC roles.

## 8. Observability Model

- Structured logs with request id and action correlation id.
- Metrics: request latency, error rates, triage throughput, sidecar queue depth, thumbnail cache hit ratio.
- Health views: dependency checks for registry access and queue worker status.

## 9. Deployment Topology

Recommended baseline:
- Keep existing poll/timer and CLI on host.
- Run API as a systemd service on same host initially.
- Run UI as static assets served by API or reverse proxy.
- Keep registry DB local; avoid remote DB in first rollout.

Progressive hardening path:
1. Localhost-only API and static UI.
2. LAN exposure with token auth.
3. Reverse proxy TLS termination and hardened headers.

## 10. Migration Strategy

1. Introduce read-only API endpoints and UI views first.
2. Add mutating triage actions behind feature flags.
3. Enable sidecar and blocklist management after write-path validation.
4. Enable automation features only after manual triage metrics are stable.

Rollback:
- UI/API can be disabled without impacting timer-driven ingest.
- Existing CLI remains authoritative fallback for all actions.

## 11. Risk Register

- Risk: UI action duplication during network retries.
  - Mitigation: mandatory idempotency keys and response replay.
- Risk: mismatch between API and CLI behavior.
  - Mitigation: shared domain service layer and integration parity tests.
- Risk: high I/O from thumbnail generation.
  - Mitigation: on-demand cache with TTL and size cap.
- Risk: audit drift.
  - Mitigation: enforce audit-first transaction wrapper in mutating service methods.

## 12. Acceptance Conditions For Architecture Adoption

- API writes demonstrably preserve existing ingest invariants.
- Feature-flag rollback verified in staging.
- Security baseline (token auth, CORS, rate limiting, redaction) validated.
- Architecture and roadmap linked from canonical docs.
