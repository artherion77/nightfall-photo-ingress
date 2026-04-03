# Web Control Plane — Phase 3 Architecture Proposals

Status: Proposed
Date: 2026-04-03
Owner: Systems Engineering
Depends on: planning/planned/web-control-plane-phase1-scope.md,
            design/web/web-control-plane-architecture-phase2.md,
            planning/proposed/web-control-plane-phase2-implementation-roadmap.md

---

## 1. Purpose and Scope

This document defines the Phase 3 architecture proposals for the photo-ingress Web
Control Plane. Phase 3 is the intelligence and automation layer built on the stable,
LAN-exposed, hardened foundation established in Phase 2.

Phase 3 adds:

- A production-grade background worker with a sidecar processing pipeline (thumbnails,
  metadata enrichment, pHash perceptual hashing, duplicate detection).
- A declarative policy engine enabling rule-based auto-triage without operator
  intervention.
- An observability layer exposing operational metrics and structured logs.
- Optional ML-assisted classification for content annotation.
- UI extensions supporting the new capabilities: Advanced Audit UI, Policy Editor,
  Worker Dashboard integration.

Phase 3 does not introduce distributed deployment, external message brokers, cloud
services, or any infrastructure class not already present in the Phase 2
single-container topology.

### 1.1 Phase 3 Entry Gate

Phase 3 work must not begin until all of the following conditions are met:

1. All Phase 2 mandatory items are operational (P2-A through P2-H per the Phase 2
   implementation roadmap).
2. The LAN-exposure gate checklist in the Phase 2 roadmap §5 is fully signed off.
3. The system has been in stable LAN production use for a minimum validation period
   (recommended minimum: two full poll cycles covering at least one week of normal
   ingestion activity).

The validation period is intentional. Phase 3 components interact deeply with the
domain layer. Delivering Phase 3 before Phase 2 is stable under real load is a primary
source of architectural drift.

---

## 2. Architectural Principles Carried Forward

The following constraints from Phase 1 and Phase 2 govern all Phase 3 decisions.

| Principle | Carried Forward As |
|-----------|-------------------|
| Minimalism | No new dependency class unless it removes a larger class of Phase 2 complexity or enables a clearly defined operator capability |
| Anti-entropy | Each Phase 3 addition has an offset: it removes operator burden, or it is not added |
| Domain independence | Domain logic (policy evaluation, pHash computation, metadata extraction) is never aware of the API layer or the UI |
| Clean dependency direction | Domain → Data; Worker → Domain; API → Domain; UI → API. No reverse edges. The worker never calls the API. |
| No external message broker | A single-container personal server does not warrant Kafka, RabbitMQ, or NATS. SQLite WAL queue is the Phase 3 default; Redis is optional and trigger-gated. |
| No cloud services | Personal photo archive. No image data leaves the LXC container for classification, hashing, or storage. All ML inference must be local. |
| Fail visible, not fail silent | Worker failures, policy evaluation errors, and ML pipeline errors surface in the Audit log and Worker Dashboard. Nothing swallows errors. |

---

## 3. Vector Evaluations

Each proposal vector is evaluated below. Decision: ACCEPT, MODIFIED ACCEPT,
or REJECT. Justification is provided for all three outcomes.

---

### 3.1 Background Worker Architecture

**Proposal:** Introduce a persistent background worker process for asynchronous jobs.

**Evaluation:** This vector is already accepted as Phase 2 optional
(web-control-plane-architecture-phase2.md §9). Phase 3 does not re-evaluate that decision — it graduates
the worker from optional to the mandatory foundation on which Phase 3.1 (Sidecar
Pipeline) and Phase 3.2 (Policy Engine) depend.

**Decision: MODIFIED ACCEPT — Phase 3.0 Foundations.**

**Modifications to the Phase 2 worker design:**

1. **Job type registry.** The worker gains a job type registry: a Python dict mapping
   job type strings to handler callables. New job types (thumbnail, pHash, metadata,
   ML classification) are registered at worker startup without modifying the dispatch
   loop. The flat if/elif pattern described in Phase 2 §9.2 does not scale across three
   or more distinct job types.

2. **Per-type retry policy.** Each registered job type declares `max_attempts` and
   `retry_delay_seconds`. The dispatcher enforces these per-type. This replaces a
   single global retry constant.

3. **Dead letter partition.** A `dead_letter` boolean column is added to the job table.
   Jobs that exhaust all retry attempts are marked dead-letter rather than deleted.
   The operator can inspect and re-enqueue them via the API.

**Justification:** These three modifications are minimal and backward compatible with
the Phase 2 job table definition. They are preconditions for the sidecar pipeline — the
pipeline requires ordered job dependencies (Phase 3.1) and observable failure modes
(dead letter) that the Phase 2 design does not provide.

---

### 3.2 Task Queue: SQLite → Optional Redis

**Proposal:** Begin with a SQLite-backed job queue; provide an upgrade path to Redis.

**Evaluation:** The SQLite WAL queue is correct for Phase 3 default. The Phase 2
design (§9.4) already documents the interface abstraction required for a future Redis
implementation. Redis is only warranted under specific throughput conditions that are
unlikely for a personal archival server.

**Decision: ACCEPT SQLite as Phase 3 default; ACCEPT Redis as Phase 3.5 optional
(trigger-gated).**

**Modified form:**

- The job queue is abstracted behind a `JobQueue` interface in
  `nightfall_photo_ingress/worker/queue.py`.
- The `SqliteJobQueue` implementation is the Phase 3.0 default.
- `RedisJobQueue` is implemented only if the trigger conditions defined in §8.6 are met.
- The worker dispatch loop is unaware of which implementation is active; it receives an
  injected `JobQueue` instance.

**Rejection of immediate Redis introduction:** Any introduction of Redis in Phase 3.0
or Phase 3.1 is rejected. Redis adds a new process class — daemon, auth, network socket,
memory pressure, and operational monitoring surface — for no benefit until queue
throughput becomes measurably problematic.

**Trigger conditions for Redis (Phase 3.5):**

- SQLite job queue pick-up latency: p95 > 500ms under normal ingestion load.
- More than three concurrent worker processes contending on the same queue (SQLite WAL
  handles one writer at a time; many concurrent writers cause lock contention).
- ML batch processing (Phase 3.4) produces enqueue bursts that cause measurable
  scheduler starvation for other job types.

---

### 3.3 Domain-Level Event Bus

**Proposal:** Introduce a domain-level event bus for internal publish/subscribe between
domain modules.

**Evaluation:** The intent is to decouple the policy engine (which must react to item
state transitions) from the domain service that performs those transitions. Without an
event bus, the domain service must directly call the policy engine — creating a coupling
that makes both harder to test and extend.

An external broker (Kafka, NATS, Redis Pub/Sub) would solve the decoupling problem but
introduces a network boundary and process boundary for a system that runs in a single
Python process. This is disproportionate.

**Decision: MODIFIED ACCEPT — in-process Python observer only.**

**Modified form:**

The event bus is a lightweight in-process Python observer. It is implemented in
`nightfall_photo_ingress/events.py`:

- `DomainEvent` is a dataclass with `event_type: str`, `payload: dict`,
  `occurred_at: datetime`.
- `EventBus` holds a dict mapping event type strings to lists of handler callables.
- `EventBus.publish(event)` calls all registered handlers synchronously, in
  registration order.
- Handlers are registered at application startup (in the worker's main module or a
  startup hook). No handler registration is scattered across business logic.
- The worker process has its own `EventBus` instance; events do not cross process
  boundaries.

**Scope restriction.** The event bus is used exclusively for:

| Event type | Published by | Consumed by |
|-----------|-------------|-------------|
| `item.ingested` | Registry domain service (on new item insert) | Worker (enqueue sidecar jobs); Policy Engine handler |
| `item.state_changed` | Triage domain service | Audit domain service; Policy Engine handler |
| `job.completed` | Worker dispatcher | Policy Engine handler (to trigger post-pipeline evaluations) |

**Rejected uses:** The event bus is not used for API request/response observability
(handled by the observability layer, §3.5), cache invalidation, or UI push
notifications (which would require WebSocket infrastructure that is out of Phase 3
scope).

**Justification for rejection of an external broker:** Synchronous in-process pub/sub
introduces no asynchrony, no serialization, no network dependency, and no new process.
It is a plain Python dispatch mechanism. For the volume of events a personal photo
archive generates, synchronous dispatch is never a bottleneck.

---

### 3.4 Policy Engine

**Proposal:** A declarative rule engine for auto-accept, auto-reject, and
metadata-driven triage decisions.

**Evaluation:** As the volume of ingested items grows, requiring the operator to
manually triage every item becomes operationally expensive. A policy engine allows
defining rules such as "auto-accept all items from album X" or "auto-reject video files
over 500MB" without per-item operator interaction. This is the primary operator
time-saving capability in Phase 3.

**Decision: ACCEPT — Phase 3.2, mandatory.**

**Policy rule structure:**

A policy rule is a database row with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | UUID | Unique identifier, generated on create |
| `name` | string | Operator-assigned display label |
| `priority` | integer | Evaluation order; lower value evaluated first |
| `conditions` | JSON | List of field matchers (see below) |
| `action` | enum | `accept`, `reject`, or `defer` |
| `active` | boolean | Inactive rules are skipped entirely |

**Condition structure (single condition):**

```
{
  "field": "file_type",
  "operator": "equals",
  "value": "image/jpeg"
}
```

Rules evaluate conditions with AND logic: all conditions must match for the rule to
fire. OR logic is achieved by creating two separate rules with the same action and
adjacent priorities.

**Condition fields available at Phase 3.2 launch:**

- `file_type` — MIME type string (e.g., `image/jpeg`, `video/mp4`).
- `file_size_bytes` — integer; supports `equals`, `greater_than`, `less_than`.
- `source_album` — OneDrive album/folder name string.
- `filename_pattern` — glob pattern matched against the filename (not full path).

**Condition fields added after Phase 3.1 is operational:**

- `metadata.*` — any key in the `item_metadata` table (e.g., `metadata.camera_make`,
  `metadata.original_datetime`). These require the sidecar metadata extraction pipeline
  to be running.

**Evaluation semantics:**

- Rules are evaluated in ascending priority order.
- The first matching rule wins; evaluation stops.
- If no rule matches, the item remains in the default pending state. No automatic action
  is taken.
- Policy-driven state transitions are written to the audit log with
  `actor = policy:{rule_id}`. This maintains the audit trail for all triage decisions
  regardless of whether they were manual or automated.

**Rejection of external rules frameworks:** Drools, Rego, OPA, CEL, and similar
frameworks are rejected. The policy rule model above is expressible as a sequential
Python evaluation loop in under 200 lines. Introducing an external rules engine adds a
new language runtime dependency, a new learning surface, and a new failure mode for
zero benefit at this scale.

**Rejection of dynamic code execution:** Policy condition values are data, not code.
No `eval()`, no embedded Python expressions, no template languages. Policy conditions
are matched by the engine's comparators only.

---

### 3.5 Observability Layer

**Proposal:** Metrics endpoint (Prometheus), structured logs, and distributed tracing.

**Evaluation:**

For a single-container personal server, the observability requirements are:

1. **Metrics:** Queue depth, job latency distribution, policy evaluation counts, item
   state distribution, API request counts and latencies.
2. **Structured logs:** Already present in the Python logging configuration. The Phase 3
   improvement is upgrading to a machine-parseable JSON log format.
3. **Distributed tracing:** Not applicable. There is no distributed system. Tracing
   across a single process's call stack adds OTLP exporter overhead, a trace backend
   (Jaeger, Tempo), and SDK complexity for a system with no service boundaries to
   observe.

**Decision: ACCEPT metrics and structured logs — Phase 3.3, mandatory. REJECT
distributed tracing.**

**Metrics — modified form:**

The FastAPI application gains a `GET /metrics` endpoint returning Prometheus text
format. Metrics are recorded in-process using the `prometheus-client` Python library.
No push gateway is required for a scrape-based deployment.

Metric catalogue:

| Metric name | Kind | Labels |
|------------|------|--------|
| `photo_ingress_items_total` | Counter | `state` (pending/accepted/rejected/deferred/purged) |
| `photo_ingress_queue_depth` | Gauge | `job_type` |
| `photo_ingress_job_duration_seconds` | Histogram | `job_type`, `status` (success/failure) |
| `photo_ingress_policy_evaluations_total` | Counter | `action` (accept/reject/defer/no_match) |
| `photo_ingress_api_requests_total` | Counter | `method`, `endpoint`, `status_code` |
| `photo_ingress_api_request_duration_seconds` | Histogram | `method`, `endpoint` |

The `/metrics` endpoint is unauthenticated (standard Prometheus scrape convention;
scraping is LAN-internal and the metric data contains no personal content). Caddy can
restrict it to a LAN-only source IP range if the operator prefers.

**Structured logging — modified form:**

Phase 1 uses Python's stdlib `logging` with a simple text format. Phase 3.3 upgrades
to structured JSON output using `python-json-logger` or `structlog` (minimal
dependency; either is acceptable). Log entries gain a `correlation_id` field — a UUID
generated per API request, propagated to all log calls within that request via
`contextvars.ContextVar`. Worker jobs gain a `job_id` field in all log calls.

**Distributed tracing — rejection justification:**

OpenTelemetry distributed tracing is rejected for Phase 3. The system runs in a single
LXC container with no microservice boundary. There is no "distributed" component to
trace. The OTLP SDK, trace context propagation, sampling configuration, and a trace
backend collectively add more complexity than the entire Phase 3.3 deliverable. The
Prometheus metrics endpoint provides equivalent operational insight in a form already
compatible with the nightfall monitoring infrastructure.

---

### 3.6 Sidecar Pipeline

**Proposal:** Background jobs for thumbnail generation, EXIF/XMP metadata enrichment,
and pHash perceptual hashing for duplicate detection.

**Evaluation:** This is the primary use case for the background worker and delivers
tangible operator value: visual previews in the Staging Queue UI, duplicate detection
without manual comparison, and searchable metadata fields that policy rules (Phase 3.2)
can reference.

**Decision: ACCEPT — Phase 3.1, mandatory. Requires Phase 3.0 worker foundation.**

**Pipeline stage definitions:**

| Stage | Job type | Tool | Output | Storage |
|-------|----------|------|--------|---------|
| Thumbnail | `thumbnail` | Pillow | 256×256 WebP | `/mnt/ssd/photo-ingress/thumbnails/{sha256[0:2]}/{sha256}.webp` |
| Metadata extraction | `metadata_extract` | exiftool (subprocess) | Structured key-value JSON | `item_metadata` table, `source = exiftool` |
| Perceptual hash | `phash` | imagehash (pure Python) | 64-bit perceptual hash string | `phash` column on `items` |
| Duplicate detection | `phash_dedup` | SQL Hamming query | Proximity candidate pairs | `duplicate_candidates` table |

**Tool selection justification:**

- `Pillow` — already a Python dependency for any image handling; no new dependency
  class.
- `exiftool` — available on the nightfall host for media processing; no new language
  runtime. The worker invokes `exiftool -json {filepath}` as a subprocess and parses
  stdout. This is the established pattern for calling exiftool from Python.
- `imagehash` — pure Python, minimal dependency, no GPU requirement. pHash computation
  is adequate for near-duplicate detection of photos from the same camera. For
  identical-file detection, SHA-256 (already present in the registry) is sufficient;
  pHash adds fuzzy similarity detection.

**Pipeline triggering:**

Jobs are enqueued when an item transitions to `pending` state, triggered by the
`item.ingested` domain event. Three job rows are inserted simultaneously:
`thumbnail`, `metadata_extract`, and `phash` for the same `item_id`. `phash_dedup` is
inserted only after the `phash` job completes, via the `depends_on_job_id` column.

This ensures duplicate detection only runs once the pHash value is available, without
polling or tight coupling in the dispatcher.

**Thumbnail API and caching:**

`GET /api/v1/items/{item_id}/thumbnail` streams the cached WebP from disk. Returns 404
if the thumbnail has not yet been generated. The UI renders a placeholder skeleton
until the thumbnail is available. On-demand thumbnail generation via the API is not
supported — thumbnails are always produced by the worker.

**pHash duplicate detection:**

`phash_dedup` queries the `items` table for all items with a Hamming distance ≤ 8
to the current item's pHash. A Hamming distance of 8 out of 64 bits corresponds to
near-identical images tolerating minor crop, compression, or metadata differences.
Candidates are written to `duplicate_candidates`. The operator inspects candidates in
the Staging Queue UI via a badge on affected items and optionally in the Advanced Audit
UI.

---

### 3.7 Optional ML Layer

**Proposal:** Image classification and auto-tagging via local ML inference (CLIP or
similar).

**Evaluation:** ML-based classification adds semantic metadata (content category, scene
type) without operator manual entry. However, it introduces material operational risk:
model size (~350MB for CLIP ViT-B/32), inference latency (1–3 seconds per image on CPU
without GPU), dependency chain (ONNX Runtime), and potential for incorrect annotations
that silently influence policy rule evaluations.

**Decision: MODIFIED ACCEPT — Phase 3.4, optional, with strict constraints.**

**Constraint set (all constraints are mandatory if the ML layer is adopted):**

1. **Local inference only.** No API calls to external ML services. No cloud providers.
   Images never leave the LXC container for classification. This is non-negotiable for
   a personal photo archive.

2. **ONNX Runtime, not PyTorch.** ONNX Runtime's CPU inference is significantly lighter
   than a full PyTorch installation. The CLIP model is used in ONNX-exported form.
   No GPU dependency.

3. **ML output is annotation only, not triage input by default.** Classification results
   are stored as a flat string list in the `item_metadata` table under
   `source = ml`, `key = ml_tags`. They are never inputs to the Policy Engine unless
   the operator explicitly creates a policy rule referencing a `metadata.ml_tags`
   condition. The ML layer produces suggestions; automated decisions require a policy
   rule.

4. **Opt-in via feature flag.** `[worker] ml_classification_enabled = true` in
   `photo-ingress.conf`. Disabled by default. The ONNX Runtime dependency and model
   file are not required unless this flag is enabled.

5. **Model management is a manual operator task.** Model files are operator-managed
   artifacts at a configurable path. No automatic model downloads or updates. A
   missing or corrupt model file is a misconfiguration, not a runtime error.

6. **Graceful degradation.** ML classification failure (model file missing, inference
   error, timeout) does not block other sidecar pipeline stages. The job transitions to
   dead letter; all other sidecar stages proceed. The operator sees the failure in the
   Worker Dashboard.

**Rejection scope:** Multi-model pipelines, fine-tuning, training, active learning,
model serving infrastructure (TorchServe, Triton), and any cloud ML API are rejected
for Phase 3. They exceed the complexity budget for a single-container personal archival
tool, and they introduce operational burden that has no commensurate benefit at this
scale.

---

### 3.8 Optional Postgres Migration

**Proposal:** Complete the SQLite → Postgres migration path.

**Evaluation:** The migration path is fully specified in web-control-plane-architecture-phase2.md §8.
Phase 3 is not the right document to re-specify it. The migration decision is
trigger-driven; if the triggers have not fired by end of Phase 2, Phase 3 does not
cause them to fire. However, the Phase 3 sidecar pipeline adds a new potential trigger:
sustained write throughput from worker job completions.

**Decision: NOT A NEW PHASE 3 ITEM. Stays Phase 2 optional.**

Phase 3 adds one new trigger condition to web-control-plane-architecture-phase2.md §8.2 (via amendment
note, not a new section):

> If the Phase 3 sidecar pipeline worker produces sustained write throughput exceeding
> ten job completions per second, and this produces p95 write latency on triage
> actions above 100ms, then the Postgres migration trigger is met.

**Justification for not re-specifying:** Creating a Phase 3 section for Postgres
migration would implicitly promote it from optional to Phase 3 scope, creating planning
pressure to include it in Phase 3 delivery. Its optionality must be preserved. The
existing trigger conditions in web-control-plane-architecture-phase2.md §8.2 remain authoritative.

---

### 3.9 Optional Distributed Deployment

**Proposal:** Support for multi-server or container-orchestrated deployment.

**Evaluation:** The system is a personal archival server for a single operator,
running in a single LXC container on a private LAN host. Distributed deployment
introduces:

- A new infrastructure class (Kubernetes, Nomad, or equivalent).
- Distributed state concerns (session storage, worker coordination, queue partitioning,
  cache invalidation across nodes).
- New failure modes (network partition, split-brain, rolling update coordination,
  distributed transaction semantics).
- Operational burden that scales with node count, not with photo count.

None of these trade-offs are justified by the use case. There is no credible scenario
in which a personal photo archive requires horizontal scaling.

**Decision: REJECT — definitively, not deferred.**

This is not a deferral to Phase 4. Definitively rejecting distributed deployment
preserves the single-container design constraint as a feature. If the project scope
ever changes to a multi-user, multi-site organisation deployment, the correct response
is a new architectural foundation, not a Phase 3+ extension.

Documenting a definitive rejection here prevents future planning sessions from
reopening this question without explicitly acknowledging and overturning this record.

---

### 3.10 Advanced Audit UI

**Proposal:** Richer audit timeline with time-range filtering, action-type breakdown,
export, and inline item preview.

**Evaluation:** The Phase 2 Audit Timeline supports cursor-based infinite scroll and
action-type single-select. As the audit log grows to cover months of ingestion activity,
unfiltered browsing becomes impractical. Policy-driven triage entries (introduced in
Phase 3.2) require actor filtering to distinguish automated from manual actions.

**Decision: ACCEPT — Phase 3 UI, delivered with Phase 3.2 Policy Engine.**

Extensions defined in §5.1.

---

### 3.11 Policy Editor UI

**Proposal:** UI for creating, editing, prioritising, and previewing policy rules.

**Evaluation:** The Policy Engine (§3.4) stores rules in the database and exposes
full CRUD through the API. The Policy Editor UI is the operator-facing management
interface. Direct API calls are acceptable for a technical operator but are not
ergonomic for ongoing rule management.

**Decision: ACCEPT — Phase 3 UI, delivered with Phase 3.2 Policy Engine.**

Details defined in §5.2.

---

### 3.12 Worker Dashboard

**Proposal:** Operator-facing visibility into background worker job status, queue
depth, and pipeline health.

**Evaluation:** Without this, the Phase 3.1 sidecar pipeline is operationally opaque.
The operator has no way to know whether thumbnail generation is keeping pace with
ingestion, or how many jobs are in the dead letter queue.

**Decision: ACCEPT — Phase 3 UI, delivered with Phase 3.1 Sidecar Pipeline.**

Details defined in §5.3.

---

## 4. System Extensions

### 4.1 Domain Layer Extensions

The `nightfall_photo_ingress` Python package is extended with the following structure
in Phase 3:

```
nightfall_photo_ingress/
  events.py                 ← DomainEvent, EventBus (Phase 3.0)
  worker/
    __init__.py
    queue.py                ← JobQueue interface + SqliteJobQueue (Phase 3.0)
    dispatcher.py           ← job type registry, dispatch loop, retry policy (Phase 3.0)
    jobs/
      thumbnail.py          ← ThumbnailJob (Phase 3.1)
      metadata.py           ← MetadataExtractJob (Phase 3.1)
      phash.py              ← PHashJob, PHashDedupJob (Phase 3.1)
      ml_classify.py        ← MlClassifyJob (Phase 3.4, optional)
  policy/
    __init__.py
    engine.py               ← PolicyEngine.evaluate() (Phase 3.2)
    models.py               ← PolicyRule, PolicyCondition, PolicyAction (Phase 3.2)
    repository.py           ← PolicyRuleRepository CRUD (Phase 3.2)
  observability/
    __init__.py
    metrics.py              ← Prometheus metric registrations (Phase 3.3)
    logging.py              ← structured JSON log formatter config (Phase 3.3)
```

**Dependency direction within the package:**

- `events.py` — no imports from within the package; pure data + dispatch.
- `worker/` — imports from domain services and `events.py`; never imports from `api/`.
- `policy/` — imports from domain models and `events.py`; never imports from `worker/`
  or `api/`.
- `observability/` — imports from stdlib only; can be imported by any layer without
  creating a cycle.

The existing domain services (`registry.py`, `triage.py`, `audit.py`, etc.) are
extended to fire domain events via `EventBus.publish()`. They do not import from
`worker/` or `policy/`.

### 4.2 API Layer Extensions

All new endpoints are additive under `/api/v1/`. No existing endpoint is modified in
a breaking way.

| Endpoint | Method | Phase 3 chunk | Auth | Notes |
|----------|--------|---------------|------|-------|
| `/metrics` | GET | 3.3 | None | Prometheus scrape; LAN-internal |
| `/items/{id}/thumbnail` | GET | 3.1 | Bearer | Streams WebP from disk cache |
| `/items/{id}/duplicates` | GET | 3.1 | Bearer | Returns pHash candidate list |
| `/worker/queue-stats` | GET | 3.1 | Bearer | Per-type depth + timestamps |
| `/worker/dead-letter` | GET | 3.1 | Bearer | Failed job list + error detail |
| `/worker/dead-letter/{job_id}/retry` | POST | 3.1 | Bearer | Re-enqueue a dead-letter job |
| `/policy/rules` | GET | 3.2 | Bearer | List rules in priority order |
| `/policy/rules` | POST | 3.2 | Bearer | Create rule (idempotency key) |
| `/policy/rules/{rule_id}` | PATCH | 3.2 | Bearer | Update rule |
| `/policy/rules/{rule_id}` | DELETE | 3.2 | Bearer | Delete rule |
| `/policy/rules/reorder` | PATCH | 3.2 | Bearer | Reorder by priority (ordered ID list) |
| `/policy/preview` | POST | 3.2 | Bearer | Draft rule → match count + sample items |
| `/audit-log` (extended) | GET | 3.3 UI | Bearer | Adds `from_dt`, `to_dt`, `action`, `actor`, `format` params |

All mutating endpoints follow Phase 1 patterns: Pydantic validation, idempotency keys,
audit-first writes, and structured audit log entries.

### 4.3 Worker Layer Extensions

The Phase 2 optional background worker (`nightfall-photo-ingress-worker.service`) is promoted
to Phase 3.0 mandatory foundation. Extensions to the Phase 2 design:

- Job type registry at startup replaces flat if/elif dispatch (§3.1).
- Per-type `max_attempts` and `retry_delay_seconds` (§3.1).
- Dead letter partition in the job table (§3.1).
- `depends_on_job_id` column enabling `phash_dedup` to fire after `phash` without
  polling (§3.6).
- `JobQueue` interface enables the Phase 3.5 Redis implementation as a drop-in
  replacement without changing the dispatch loop.

### 4.4 Data Model Extensions

All schema changes are applied via numbered migration files in
`nightfall_photo_ingress/migrations/`. All changes are additive only: new tables or
new nullable/defaulted columns. No Phase 1 or Phase 2 table is altered in a breaking
way, consistent with the compatibility guarantee in web-control-plane-architecture-phase2.md §18.

**New and extended tables:**

| Table | Phase 3 chunk | Key columns |
|-------|---------------|-------------|
| `sidecar_jobs` (updated) | 3.0 | Extended with: `job_type`, `max_attempts`, `attempt_count`, `depends_on_job_id`, `dead_letter` |
| `item_metadata` (new) | 3.1 | `item_id`, `source` (exiftool / ml), `key`, `value`, `recorded_at` |
| `duplicate_candidates` (new) | 3.1 | `item_a_id`, `item_b_id`, `hamming_distance`, `resolved`, `created_at` |
| `policy_rules` (new) | 3.2 | `rule_id`, `name`, `priority`, `conditions` (JSON), `action`, `active`, `created_at`, `updated_at` |

The migration runner (`python -m nightfall_photo_ingress.migrations`) is already in
the Phase 2 deployment procedure and remains the only migration entry point. No ORM
migration framework is introduced.

### 4.5 Deployment Topology (Phase 3)

Phase 3 adds zero new infrastructure classes. The service inventory from Phase 2
is extended minimally:

```
LXC Container: photo-ingress
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  caddy.service                   :443 (LAN-facing)           │
│    ↓ /             → webui/current/  (static assets)         │
│    ↓ /api/         → 127.0.0.1:8000 (Uvicorn)               │
│                                                              │
│  nightfall-photo-ingress-api.service       127.0.0.1:8000              │
│    ↓ FastAPI + Uvicorn                                       │
│    ↓ Imports domain modules from nightfall_photo_ingress     │
│    ↓ SQLite registry (WAL mode)                              │
│                                                              │
│  nightfall-photo-ingress-worker.service    (no socket)       │
│    ↓ Polls job queue via JobQueue interface                   │
│    ↓ Dispatches to registered job type handlers              │
│    ↓ SQLite registry (WAL mode, shared)              ← Phase 3.0 promoted │
│                                                              │
│  nightfall-photo-ingress.timer             (no socket)       │
│  nightfall-photo-ingress-trash.path        (no socket)       │
│                                                              │
│  /mnt/ssd/photo-ingress/thumbnails/  ← WebP cache (Phase 3.1) │
│                                                              │
│  Optional Phase 3.4:                                         │
│  /opt/photo-ingress/models/       ← ONNX CLIP model file     │
│                                                              │
│  Optional Phase 3.5:                                         │
│  redis.service       127.0.0.1:6379  ← job queue only        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

The Caddy, API, and CLI timer topology from Phase 2 is unchanged.

---

## 5. UI Extensions

### 5.1 Advanced Audit UI

**Page:** Existing `/audit` route — extended in place.

**New filtering controls:**

- **Date range picker** — `from_dt` and `to_dt` date inputs, applied as ISO 8601
  query parameters on the audit log API call. Defaults to unconstrained (all history).
- **Action multi-select** — chip group: Accept, Reject, Defer, Policy: Auto-Accept,
  Policy: Auto-Reject, Block, Unblock. Sent as repeated `action` query parameters.
- **Actor toggle** — three-way: All / Manual triage / Policy automated. Derived from
  the `actor` field prefix: manual triage entries carry the configured token name;
  policy entries carry the `policy:` prefix.
- **CSV export** — button triggers `GET /api/v1/audit-log?...&format=csv` with the
  current filter state. The server returns `text/csv`; the browser presents a file
  download. Export is limited to the current filter's result set up to a configurable
  row limit to avoid memory pressure on large logs.

**Inline item preview panel:**

Clicking an audit entry expands an inline detail panel (not a modal) below the row:

- Item thumbnail (if Phase 3.1 sidecar has generated it; placeholder spinner if not).
- Item filename, file type, file size, source album.
- Metadata fields from `item_metadata` (if Phase 3.1 available).
- Duplicate candidates badge if `duplicate_candidates` rows exist for this item.
- Link to the item's full Staging Queue detail view.

Audit log pagination remains cursor-based. The date-range and action filters narrow
the server-side result set; Phase 2 infinite scroll operates within the filtered set.

### 5.2 Policy Editor UI

**Page:** Settings page (`/settings`) — "Policy Rules" section added below KPI
Thresholds.

**Rule list view:**

- Table columns: Priority order, Name, Conditions summary, Action, Active toggle,
  Edit / Delete controls.
- Priority reorder controls: up/down arrow buttons per row; keyboard accessible.
  Drag-to-reorder is a Phase 3+ optional enhancement, not required at Phase 3.2 launch.
  Save of reorder calls `PATCH /api/v1/policy/rules/reorder`.
- "New Rule" button opens the rule form panel inline.

**Rule form panel (inline, not modal):**

- Name field (freeform text label for operator reference).
- Condition builder: up to five conditions per rule using AND logic.
  - Field selector (dropdown from enumerated condition fields; scoped to what is
    available — `metadata.*` fields appear only if Phase 3.1 is operational).
  - Operator selector (filtered by field type: text fields offer `equals`,
    `not_equals`, `matches`; numeric fields add `greater_than`, `less_than`).
  - Value input (text or numeric; for `file_type`, a dropdown of allowed types from the
    config store).
- Action selector: Accept / Reject / Defer.
- Active toggle.
- Priority (auto-assigned to lowest existing priority + 10 on create; editable).
- "Preview matches" button: calls `POST /api/v1/policy/preview` with the draft rule and
  shows an inline result: match count and up to three sample item filenames from the
  current staging queue. Allows the operator to verify the rule's scope before saving.
- Save (POST/PATCH with idempotency key) and Cancel.

**Interaction consistency with Phase 1 patterns:**

- Destructive delete uses the same `ConfirmationDialog` component from Phase 1
  blocklist UI.
- Error states use the same `ErrorBanner` component.
- Success confirmations use the same toast component from Phase 2 KPI threshold
  settings.

### 5.3 Worker Dashboard

**Panel location:** Existing Dashboard page — collapsible "Pipeline Status" panel,
positioned below the KPI grid. This is not a new top-level route. The Worker Dashboard
operator need is informational, not a primary workflow, and does not warrant a
dedicated page.

**Pipeline status table:**

| Job Type | Queue Depth | Last Completed | Recent Failures (1h) |
|----------|-------------|----------------|----------------------|
| thumbnail | {n} | {timestamp} | {n} |
| metadata_extract | {n} | {timestamp} | {n} |
| phash | {n} | {timestamp} | {n} |
| phash_dedup | {n} | {timestamp} | {n} |
| ml_classify | {n} (if enabled) | {timestamp} | {n} |

Data sourced from `GET /api/v1/worker/queue-stats`. Refreshed at the same interval as
the existing dashboard health polling.

**Dead-letter section:** Collapsed by default. Expands to a list of failed jobs with
job type, item filename, error message, and a "Retry" button per row. Retry calls
`POST /api/v1/worker/dead-letter/{job_id}/retry`.

**Item detail overlay extension:** The existing Staging Queue item detail overlay gains
a "Processing Status" card showing per-stage pipeline results for that item:

```
Processing Status
  Thumbnail       ● Generated  (456ms)
  Metadata        ● Extracted  (1.2s)
  pHash           ● Computed   (88ms)
  Duplicate check ● 2 candidates found  [View]
  ML tags         ○ Pending
```

Status values: Generated / Extracted / Computed / Pending / Failed.

---

## 6. Risks and Drift Control

### 6.1 Drift Vectors

| Drift vector | Risk description | Mitigation |
|-------------|-----------------|-----------|
| Policy condition language growth | Conditions expand beyond the defined field enumeration (e.g., embedded Python expressions, Jinja templates, regex with backreferences) | Condition fields are a fixed enumeration in `policy/models.py`; new condition fields require an explicit schema migration and code change |
| Worker job type proliferation | Every new feature type adds a background job; worker becomes a general-purpose task runner | Job types are restricted to sidecar pipeline stages (data enrichment for registered items); business logic orchestration jobs are rejected |
| ML annotation scope creep | Starting with classification tags creates pressure for ranking, recommendation, captioning, and generative output | `ml_tags` is a flat string list; no structured prediction, score, or ranking data is stored; the ML output model is explicitly constrained in `ml_classify.py` |
| Observability framework substitution | "Let's switch from prometheus-client to OpenTelemetry metrics for consistency" | The integration point is the Prometheus text format scrape endpoint; the specific library is an implementation detail; no OpenTelemetry SDK unless the nightfall host already runs an OTLP collector |
| Event bus misuse | Infrastructure concerns (cache invalidation, API response caching) implemented as domain events | `EventBus` is defined in the domain layer; infrastructure layers may subscribe but must never publish domain events; publisher scope is bounded to domain service modules |
| Policy rules as the dominant operator interface | The Policy Editor UI becomes the primary way operators interact with the system, causing them to under-use manual triage | Audit UI clearly marks policy-driven actions with `Policy:` actor label; operator's manual triage workflow remains the primary path; policy rules are supplementary automation |

### 6.2 Over-Engineering Boundaries

The following capabilities carry elevated over-engineering risk. Any proposal to extend
beyond these boundaries should be rejected without a separate architectural review:

- **Policy Engine:** Simple sequential rule evaluator only. No rule chaining, no
  forward-chaining inference engine, no probabilistic rules, no external framework.
- **ML Layer:** Annotation pipeline only. No automated triage decisions without an
  explicit operator-defined policy rule. No training. No cloud APIs.
- **Event Bus:** In-process synchronous dispatch only. No persistence, no replay, no
  ordering guarantees, no external broker.
- **Redis Queue:** Introduced only if Phase 3.5 trigger conditions are met and verified
  by measurement. Not adopted speculatively.

### 6.3 Prohibited Elements

The following elements are incompatible with the Phase 3 scope and must not be
introduced:

| Element | Reason |
|---------|--------|
| External message broker (Kafka, RabbitMQ, NATS, Celery) | Single container; no inter-process messaging beyond shared SQLite |
| Container orchestration (Kubernetes, Nomad, Docker Swarm) | Personal server; horizontal scaling is not a requirement |
| Cloud ML APIs | Privacy; personal photos must not leave the container |
| Dynamic code execution in policy conditions | Security; `eval()` or equivalent in user-defined conditions is a code injection vector |
| New web framework or additional runtime | FastAPI + Uvicorn is the established Phase 1 decision |
| Graph database or document store | SQLite with JSON columns is the correct model for policy rules and metadata |
| WebSocket or SSE for push notifications | Single operator; polling intervals are sufficient; push infrastructure is disproportionate |
| Background job scheduler framework (APScheduler, Celery Beat) | The systemd timer + SQLite queue pattern established in Phase 1 is adequate |

### 6.4 Phase 1 and Phase 2 Alignment

All Phase 3 additions maintain the following constraints from Phase 1 and Phase 2:

- **API contract stability:** All new endpoints are additive. No Phase 1 or Phase 2
  endpoint is renamed, removed, or response-shape-broken.
- **Auth continuity:** All new Phase 3 endpoints use the static bearer token. The auth
  dependency in `auth.py` is not modified in Phase 3.
- **CLI timer isolation:** The `nightfall-photo-ingress` timer and `nightfall-photo-ingress-trash` path unit
  do not interact with the worker's job queue directly. Domain events fired by
  CLI-invoked domain services are consumed by the worker if it is running; if not
  running, they are not buffered (the worker will process the `pending` item on its
  next queue scan regardless).
- **Schema migration discipline:** All schema changes are additive only, consistent with
  the Phase 2 compatibility guarantee (web-control-plane-architecture-phase2.md §18).
- **Worker optional fallback:** If `nightfall-photo-ingress-worker.service` is stopped, the API
  and CLI continue to function. Items accumulate without sidecar processing. The API
  returns 404 for thumbnail requests and empty arrays for duplicate and metadata
  requests. No degraded mode affects the primary triage workflow.

---

## 7. Chunked Roadmap

Each chunk is independently deliverable. Prerequisites are explicit. Optional chunks
may be skipped without blocking later mandatory chunks unless noted.

---

### 7.1 Phase 3.0 — Foundations

**Prerequisite:** All Phase 2 mandatory items complete. LAN-exposure gate signed off.

**Deliverables:**

- `nightfall_photo_ingress/events.py` — `DomainEvent`, `EventBus`.
- `nightfall_photo_ingress/worker/queue.py` — `JobQueue` interface, `SqliteJobQueue`.
- `nightfall_photo_ingress/worker/dispatcher.py` — job type registry, dispatch loop,
  per-type retry policy, dead letter routing.
- Schema migration: extend `sidecar_jobs` with `job_type`, `max_attempts`,
  `attempt_count`, `depends_on_job_id`, `dead_letter` columns.
- `nightfall-photo-ingress-worker.service` promoted from optional to required systemd unit.
- Worker API: `GET /api/v1/worker/queue-stats`, `GET /api/v1/worker/dead-letter`,
  `POST /api/v1/worker/dead-letter/{job_id}/retry`.

**Acceptance criteria:**

- Worker starts, polls the job queue, and processes a no-op test job to completion.
- Failed jobs exceeding `max_attempts` appear in the dead-letter partition.
- All worker API endpoints return correct data.
- Worker restarts cleanly under systemd on failure (confirmed via `systemctl status`).

---

### 7.2 Phase 3.1 — Sidecar Pipeline

**Prerequisite:** Phase 3.0 complete.

**Deliverables:**

- `worker/jobs/thumbnail.py` — ThumbnailJob (Pillow, 256×256 WebP output).
- `worker/jobs/metadata.py` — MetadataExtractJob (exiftool subprocess, JSON parse).
- `worker/jobs/phash.py` — PHashJob (imagehash), PHashDedupJob (Hamming query).
- Schema migrations: `item_metadata` table, `duplicate_candidates` table, `phash`
  column on `items`.
- API additions: `GET /api/v1/items/{id}/thumbnail`,
  `GET /api/v1/items/{id}/duplicates`.
- Thumbnail disk cache directory provisioned in deployment.
- `item.ingested` event subscription: enqueues thumbnail, metadata_extract, and phash
  jobs.
- UI: thumbnail in Staging Queue item card; duplicate badge on affected items; Worker
  Dashboard pipeline status panel on Dashboard page.

**Acceptance criteria:**

- Ingesting a new photo item enqueues and completes all three sidecar jobs within one
  worker poll cycle.
- Thumbnail is visible in the Staging Queue UI after worker completion.
- pHash duplicate detection correctly identifies identical files re-ingested under a
  different name.
- Worker Dashboard panel shows accurate queue depth and last-completed timestamps.
- A missing or unreadable source file causes the sidecar job to fail gracefully to
  dead letter without crashing the worker.

---

### 7.3 Phase 3.2 — Policy Engine

**Prerequisite:** Phase 3.0 complete. Phase 3.1 recommended (enables `metadata.*`
conditions) but not strictly required for the initial condition set
(`file_type`, `file_size_bytes`, `source_album`, `filename_pattern`).

**Deliverables:**

- `policy/engine.py` — `PolicyEngine`, sequential rule evaluator.
- `policy/models.py` — `PolicyRule`, `PolicyCondition`, `PolicyAction` dataclasses.
- `policy/repository.py` — `PolicyRuleRepository` (SQLite CRUD).
- Schema migration: `policy_rules` table.
- `item.ingested` event subscription: `PolicyEngine.evaluate(item)` called by the
  worker handler; result applied via triage domain service if action is non-null.
- Audit log: policy-driven actions recorded with `actor = policy:{rule_id}`.
- API additions: full policy CRUD endpoints (`/policy/rules`, `/policy/preview`,
  `/policy/rules/reorder`).
- UI: Policy Rules section on Settings page — rule list, rule form, preview, reorder.
- Advanced Audit UI: `from_dt`, `to_dt`, `action`, `actor`, `format` filter parameters;
  CSV export; inline item preview panel.

**Acceptance criteria:**

- A rule for `file_type = image/jpeg → accept` automatically accepts all JPEG items
  on ingest, creating audit entries with appropriate `policy:` actor.
- A disabled rule causes zero evaluations (confirmed via `policy_evaluations_total`
  Prometheus metric after Phase 3.3, or via audit log in Phase 3.2).
- The preview endpoint returns an accurate match count against the current staging
  queue before the rule is saved.
- Policy-driven audit entries are visually distinct from manual triage entries in the
  Advanced Audit UI using the actor filter.
- Deleting a rule does not affect items already processed under that rule.

---

### 7.4 Phase 3.3 — Observability

**Prerequisite:** Phase 3.0 complete. Can be delivered independently of Phase 3.1 and
Phase 3.2 — it instruments whatever is already running.

**Deliverables:**

- `observability/metrics.py` — Prometheus metric definitions (all metric families in
  §3.5).
- `observability/logging.py` — structured JSON log formatter configuration.
- `GET /metrics` endpoint — Prometheus text format scrape, unauthenticated.
- FastAPI middleware: per-request `correlation_id` via `contextvars`, propagated to
  all log calls within the request.
- Worker dispatch loop instrumentation: job duration histograms, attempt counters.
- Policy engine instrumentation: evaluation count by action.
- Logging upgrade: all existing log calls emit JSON with `correlation_id` or
  `job_id` context field.

**Acceptance criteria:**

- `/metrics` returns parseable Prometheus text format with all defined metric families
  present.
- Log output is valid JSON on every line, with `correlation_id` set on API-originated
  log calls and `job_id` set on worker-originated log calls.
- Prometheus gauge for `photo_ingress_queue_depth` changes as jobs are enqueued and
  processed.
- No regression in API response latency (baseline comparison before and after metrics
  middleware). Acceptable overhead: < 1ms per request.

---

### 7.5 Phase 3.4 — Optional ML Layer

**Prerequisite:** Phase 3.1 complete (ML job is a new sidecar pipeline stage).

**Entry trigger:** Operator has set `[worker] ml_classification_enabled = true` in
`photo-ingress.conf` and has placed a compatible ONNX CLIP model file at the
configured model path.

**Deliverables:**

- `worker/jobs/ml_classify.py` — `MlClassifyJob` (ONNX Runtime, CLIP model inference).
- ML classification job enqueued after `metadata_extract` completes (via
  `depends_on_job_id`).
- `ml_tags` stored in `item_metadata` under `source = ml`, `key = ml_tags`.
- Worker Dashboard pipeline status panel extended with `ml_classify` row.
- Staging Queue item card extended: ML tags displayed as secondary annotation chips
  below filename (visible only if `ml_tags` present).
- Policy Editor: `metadata.ml_tags` condition field available when ML layer is active.

**Acceptance criteria:**

- With ML enabled: ingested image items receive `ml_tags` within the worker poll cycle.
- With ML disabled: no `MlClassifyJob` is ever enqueued; `onnxruntime` module is
  never imported; worker startup is unaffected.
- ML inference failure (model missing, ONNX runtime error, timeout) transitions to
  dead letter without affecting thumbnail, metadata, or pHash stages.
- A policy rule using `metadata.ml_tags contains "screenshot"` evaluates correctly.

---

### 7.6 Phase 3.5 — Optional Redis Queue

**Prerequisite:** Phase 3.0 complete. At least one trigger condition from §3.2 verified
by measurement.

**Deliverables:**

- `worker/queue_redis.py` — `RedisJobQueue` implementation of the `JobQueue` interface.
- `redis.service` systemd unit: `127.0.0.1:6379`, no external access, systemd socket
  activation or direct start.
- Configuration key: `[worker] queue_backend = sqlite` (default) or `redis`.
- Startup `JobQueue` factory selects implementation from configuration; worker dispatch
  loop is unchanged.

**Migration procedure:**

1. Start and verify the Redis service.
2. Drain the SQLite job queue: wait for queue depth to reach zero (confirm via
   `/api/v1/worker/queue-stats`).
3. Switch `queue_backend = redis` in `photo-ingress.conf`.
4. Restart `nightfall-photo-ingress-worker.service`.
5. Verify `/api/v1/worker/queue-stats` returns data sourced from Redis.

**Rollback:** Set `queue_backend = sqlite`; restart worker. SQLite job tables are
never dropped while Redis is active.

**Acceptance criteria:**

- With `queue_backend = redis`: jobs enqueue to and dequeue from Redis.
- With `queue_backend = sqlite`: no Redis process is required; `RedisJobQueue` module
  is never instantiated; worker startup is unaffected.
- `GET /api/v1/worker/queue-stats` returns correct depth regardless of backend.

---

### 7.7 Phase 3.6 — Distributed Deployment

**Status: REJECTED.** See §3.9 for the full rejection rationale.

This chunk does not exist. It is recorded here to provide a durable decision anchor
preventing this item from being re-proposed in future planning without explicitly
acknowledging and overturning the rejection recorded in §3.9.

---

## 8. Phase 3 Compatibility Summary

All Phase 3 additions maintain the Phase 1 → Phase 2 compatibility guarantees defined
in web-control-plane-architecture-phase2.md §18. The following table documents Phase 3-specific
additions to that guarantee:

| Constraint | How maintained in Phase 3 |
|-----------|--------------------------|
| Phase 1 + Phase 2 API endpoints unchanged | No existing endpoint renamed, removed, or response-shape-broken |
| Static bearer token auth still works | Auth dependency unchanged; all new endpoints follow the same auth pattern |
| CLI timer isolation preserved | No CLI code changes; worker shares SQLite WAL with CLI using the same concurrency model as Phase 2 |
| SQLite schema additive only | All Phase 3 migrations add new tables or new nullable/defaulted columns |
| Policy auto-triage is additive | Zero rules in `policy_rules` means zero automated actions; manual triage behaviour is unchanged |
| Worker failure does not block API or CLI | `nightfall-photo-ingress-api.service` and CLI timers have no runtime dependency on the worker |
| ML classification is opt-in | Feature flag disabled by default; ONNX Runtime is never imported if flag is off |
| Redis queue has a clean rollback | SQLite job tables always present; Redis is an overlay, never a permanent replacement |
| Audit trail integrity | Policy-driven actions are indistinguishable in the audit API from manual triage except for the `actor` field prefix; audit log format is unchanged |
