# Module 4 Production-Readiness Review (Ingest Decision Engine + Storage Commit Workflow)

Date: 2026-03-31
Scope reviewed:
- `nightfall_photo_ingress/pipeline/ingest.py`
- `nightfall_photo_ingress/storage.py`
- `nightfall_photo_ingress/registry.py`
- `tests/test_ingest_decisions.py`
- `tests/test_staging_recovery.py`

This review is analysis-only and focuses on end-to-end production readiness.

---

## 1) Decision correctness and idempotency

### Remaining weaknesses
- **No transactional boundary that spans file move + registry updates** (high).
  - The ingest path commits file storage first, then updates multiple registry tables in separate calls.
- **Crash gap between hash decision and registry persistence** (high).
  - A crash after commit to accepted queue but before registry updates can lead to repeated work, duplicate acceptance history, or ambiguity.
- **Idempotency is good for known hashes but weak for partially completed unknown-hash acceptance flow** (medium).
  - `accepted_records`, `file_origins`, and `metadata_index` can diverge temporarily under partial failure.
- **Table-level consistency invariants are not enforced as one operation** (medium).
  - `files`, `accepted_records`, `metadata_index`, and `file_origins` updates are not wrapped in one registry transaction API.

### Why this matters
- Production crashes and restarts are expected. Without atomic ingest state transitions, data correctness can drift and require manual repair.

### Recommendations
- Add one registry API for atomic ingest-finalize:
  - Upsert `files`
  - Insert acceptance event
  - Upsert metadata index
  - Upsert origin
  - Append audit
  - All in a single transaction.
- Add ingest lifecycle journal checkpoints and replay logic (started, hashed, committed, persisted).
- Add consistency audit utility to detect and repair divergent rows.

### Severity
- High: 2
- Medium: 2

---

## 2) Storage commit integrity

### Remaining weaknesses
- **No fsync durability guarantees on cross-pool copy path** (medium).
  - `copy2` + hash verify is good for integrity, but there is no explicit flush/fsync before final rename.
- **No staging->accepted operation journal marker** (medium).
  - If crash occurs mid-copy, temp artifacts may persist and require manual interpretation.
- **Directory creation race handling relies on `mkdir(..., exist_ok=True)` only** (low).
  - Usually correct, but no explicit logging/metric for repeated race conditions.
- **Collision strategy is numeric suffix only** (low).
  - Safe, but no cap telemetry when nearing suffix loop limits.

### Why this matters
- Durability and recoverability under power loss or abrupt process termination need explicit guarantees.

### Recommendations
- On cross-pool writes, flush file handle and fsync destination before final replace.
- Persist an operation record for copy-in-progress and finalize states.
- Add collision-loop telemetry and explicit alert when suffix search exceeds threshold.

### Severity
- Medium: 2
- Low: 2

---

## 3) Staging recovery and crash-boundary safety

### Remaining weaknesses
- **Recovery only handles `.tmp` age-based cleanup** (high).
  - Completed-but-uncommitted non-`.tmp` files are not reconciled.
- **No partial hash recovery state** (medium).
  - Hashing progress/state is not checkpointed, so restart always rehashes from scratch.
- **No explicit staging drift report** (medium).
  - There is no periodic count/report for orphaned, stale, unknown staging files.

### Why this matters
- Staging is a crash boundary. Missing recovery semantics can create silent backlog and duplicate processing.

### Recommendations
- Add startup reconciliation categories:
  - stale tmp
  - committed-but-unpersisted candidates
  - unknown artifacts
- Emit staging drift metrics and warning thresholds.
- Add quarantine folder for suspicious leftovers instead of direct delete.

### Severity
- High: 1
- Medium: 2

---

## 4) Download integrity guarantees (as consumed by ingest)

### Remaining weaknesses
- **Ingest trusts staged file as complete when hashing starts** (medium).
  - Integrity against early EOF is mostly delegated to OneDrive client behavior.
- **No explicit pre-hash size sanity check against candidate metadata in ingest path** (medium).
  - Candidate `size_bytes` is available but not used to gate hash/commit.
- **No explicit guardrail for zero-byte acceptance policy** (low).
  - It currently accepts unknown zero-byte content if not otherwise blocked.

### Why this matters
- Defense-in-depth should exist at ingress boundary and ingest boundary.

### Recommendations
- Add optional ingest-side size check before hash/commit.
- Add configurable zero-byte policy (allow, quarantine, reject).
- Record size mismatch audit reason when metadata and actual size differ.

### Severity
- Medium: 2
- Low: 1

---

## 5) Audit trail completeness

### Remaining weaknesses
- **Audit event coverage is good but not comprehensive for every failure branch** (medium).
  - Example: missing staged file path returns outcome but no explicit audit event.
- **Event ordering depends on multi-call sequence and wall-clock timestamps** (medium).
  - No explicit monotonic per-batch sequence number.
- **Actor value is static and clear, but no sub-actor context** (low).
  - Useful context like `prefilter`, `hash`, `storage_copy` is only in action/reason text.

### Why this matters
- Strong auditability is required for forensic analysis and compliance.

### Recommendations
- Emit audit event for `missing_staged` and reconcile actions.
- Add batch run id + sequence number for strict intra-batch ordering.
- Add structured audit metadata fields (phase, method, account).

### Severity
- Medium: 2
- Low: 1

---

## 6) Integration boundary with OneDrive client

### Remaining weaknesses
- **No explicit schema version or typed contract guard between OneDrive client output and ingest input** (high).
  - `StagedCandidate` assumes stable fields and semantics.
- **No compatibility validator for required fields before ingest batch processing** (medium).
  - Missing/invalid inputs can surface late.
- **Duplicate handling depends on current onedrive_id and metadata assumptions** (medium).
  - Drift in upstream semantics can reduce prefilter quality.

### Why this matters
- Module coupling without explicit contract versioning is fragile under independent hardening changes.

### Recommendations
- Introduce ingest input contract validator + version field.
- Add strict pre-batch schema checks and fail-fast with actionable error.
- Add adapter-level normalization checksum to ensure candidate determinism.

### Severity
- High: 1
- Medium: 2

---

## 7) Performance and scalability

### Remaining weaknesses
- **Hashing is single-threaded and per-file serial in this engine** (medium).
- **No adaptive batching by file size/class** (medium).
- **Storage layout can create deep directory hotspots depending on template choices** (low).
- **Potential unnecessary I/O on known files when metadata index misses** (medium).

### Why this matters
- Throughput can degrade significantly on large backlog ingestion windows.

### Recommendations
- Add optional bounded worker pool for hashing/ingest finalize.
- Add size-aware scheduling (small files first or bounded mixed queue).
- Add template validation/performance guidance and stats.
- Improve metadata index hit diagnostics and optimize key strategy.

### Severity
- Medium: 3
- Low: 1

---

## 8) Security

### Remaining weaknesses
- **Path traversal defense is partially implicit** (medium).
  - Sanitization is filename-focused; template/path normalization checks are limited.
- **No explicit safe-root enforcement before final write** (medium).
  - Destination should be strictly verified as under accepted root after rendering.
- **Permission safety for accepted outputs is filesystem-default dependent** (low).
  - No explicit mode policy is set.

### Why this matters
- Ingress and storage boundaries are high-risk trust zones.

### Recommendations
- Enforce resolved destination path must stay within accepted root.
- Normalize and reject unsafe path components in template rendering.
- Optionally enforce output file mode policy.

### Severity
- Medium: 2
- Low: 1

---

## Consolidated severity-ranked list of remaining issues

### High severity
1. Missing atomic ingest finalize transaction across all registry tables and audit.
2. Crash gap after file commit but before registry persistence.
3. Staging recovery handles tmp age only, not completed-but-unpersisted artifacts.
4. Integration contract between OneDrive client and ingest lacks explicit versioned validation.

### Medium severity
1. No fsync durability guarantees on cross-pool copy finalize path.
2. No operation journal marker for storage phase transitions.
3. No partial hash/state checkpointing.
4. No staging drift metrics and threshold alerts.
5. Ingest lacks optional pre-hash metadata size guard.
6. Missing audit events/sequence metadata for some non-happy paths.
7. No strict pre-batch candidate contract validation.
8. Hashing/ingest finalize throughput is serial-only.
9. No adaptive batching by file size or queue pressure.
10. Metadata index misses can trigger unnecessary hash I/O without diagnostics.
11. Path safety checks should explicitly enforce destination root containment.
12. Template/path normalization checks can be stricter.

### Low severity
1. Directory-creation race telemetry is minimal.
2. Collision suffix loop lacks threshold telemetry.
3. Zero-byte policy is implicit rather than explicit.
4. Audit actor metadata granularity can be improved.
5. Output permission policy is implicit.

---

## Short summary of the most critical risks

The most critical production risks are **crash-boundary consistency** and **contract hardening**. The ingest pipeline can still enter ambiguous states when a crash occurs after storage commit but before all registry/audit updates complete atomically. In addition, the handoff from OneDrive client to ingest lacks explicit schema/version validation, which increases drift risk under upstream changes. Addressing these two areas first will deliver the highest gains in correctness and operational safety.
