# photo-ingress Deferred Items for V2

Status: deferred backlog
Date: 2026-03-31
Reviewed: 2026-04-03

## Staleness review (2026-04-03)

No items in this backlog have been silently implemented in V1. All items remain correctly
deferred. Key observations:

- **§3.1–3.2 Live Photo advanced features**: Module 5 (V1 Live Photo pairing) is now
  implemented, but the items in this section (merge/export workflows, improved heuristics)
  are genuinely V2-scope and remain deferred.
- **§7.1 MCP exposure**: The `nightfall-mcp` project exists as a separate repository
  providing MCP tools for system-operator diagnostics. Photo-ingress has not been wired
  into this project. If ingest-domain MCP tools are needed, coordination with the
  `nightfall-mcp` project is the implementation path rather than adding MCP tooling
  directly to this package.
- **§1.1–1.2 Container packaging / orchestration**: A staging container environment
  (`systemd/container/`) exists for controlled smoke testing of Module 8. This is a
  test harness, not the production container image described in §1.1. The V2 container
  packaging item remains deferred.
- All other items unchanged.

---

## 1. V2 Candidate Themes

This list contains items explicitly deferred from the V1 baseline. V1-first stability, auditability, and predictable operations take priority.

---

## 2. Deployment and Runtime Platform

### 1.1 Container packaging
- Build and publish a dedicated ingest container image.
- Add container hardening profile and read-only root filesystem where feasible.
- Preserve host filesystem access model via strict bind mounts.

### 1.2 Orchestration upgrades
- Optional migration from pure systemd timers to container scheduler patterns.
- Multi-instance rollout and canary strategy.

---

## 3. Secret Management Enhancements

### 2.1 Encrypted token cache at rest
- Optional age-encrypted MSAL cache files.
- Key rotation and bootstrap tooling.

### 2.2 Advanced credential posture
- Optional split-privilege runtime users for poller and maintenance commands.

---

## 4. Live Photo Advanced Features

### 3.1 Merge and export workflows
- Optional logical package export for paired assets.
- Optional sidecar metadata generation for consumer tools.

### 3.2 Pairing accuracy improvements
- Improved pairing heuristics using additional metadata fields.
- Pair confidence scoring and conflict resolution policies.

---

## 5. Permanent Library Workflow Automation

### 4.1 Assisted operator workflow
- Optional helper CLI to produce move plans from accepted queue to permanent library.
- Safety checks before move, with rollback manifests.

### 4.2 Optional controlled copy mode
- Explicit opt-in copy into a staging handoff area under operator controls.
- Keep strict no-direct-write policy as default.

---

## 6. Data Model and Performance Enhancements

### 5.1 Extended registry analytics
- Additional materialized views for trend analysis and ingest reports.
- Optional retention partitioning for very large audit datasets.

### 5.2 Advanced import sources
- Support additional hash cache formats besides `.hashes.sha1`.
- Optional rolling verification of imported advisory hashes.

---

## 7. Observability and Operations

### 6.1 Metrics integration
- Prometheus metrics endpoint or textfile collector output.
- SLO-aligned dashboards and alert rules.

### 6.2 Event notifications
- Optional webhook notification for ingest/reject events.
- Optional enriched alert digests.

---

## 8. API and Control Surface

### 7.1 MCP exposure
- Add MCP tools for read-only diagnostics and controlled maintenance operations.

### 7.2 Administrative API
- Optional local admin API for controlled automation.

### 7.3 Identity provider abstraction
- Split authentication concerns out of the `onedrive` adapter into a provider-agnostic identity layer.
- Introduce an identity abstraction (for example: `IdentityProvider`) so adapters consume established tokens without owning auth flow details.
- Reframe current OneDrive auth implementation as a dedicated Microsoft consumer account identity provider (live.com / Microsoft account flow).

---

## 9. Security and Compliance

### 8.1 Integrity attestations
- Optional signed audit snapshots.
- Tamper-evident audit chains.

### 8.2 Policy controls
- Configurable account-level policy constraints and deny lists.

---

## 10. Exit Criteria to Pull a V2 Item Forward

A V2 item can be promoted when:
- V1 acceptance criteria have remained stable in production.
- Operational overhead of manual processes justifies automation.
- Added complexity does not compromise auditability or failure containment.
