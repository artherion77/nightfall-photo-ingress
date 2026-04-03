# Ingest Lifecycle and Crash Recovery

**Status:** active  
**Source:** extracted from `design/domain-architecture-overview.md` §6.1, §6.1.1, §14  
**See also:** [specs/ingest.md](../specs/ingest.md), [architecture/data-flow.md](data-flow.md), [architecture/state-machine.md](state-machine.md)

---

## Poll Cycle Overview

The poll cycle runs on an 8–24h production cadence via the systemd timer. Each poll run:

1. Acquires an OAuth2 token silently (MSAL refresh token flow).
2. Calls the Graph API delta endpoint for the configured OneDrive folder.
3. Processes each changed file item through the metadata pre-filter and ingest decision engine.
4. Advances the cursor checkpoint after each page's side effects are durable.

For full step-by-step detail see [specs/ingest.md](../specs/ingest.md).

---

## Authoritative Cursor Commit Rule

The streaming page-commit model is authoritative. Cursor advancement is a **commit acknowledgement**, not a fetch acknowledgement.

- Never advance cursor before page ingest side effects are durable.
- If a poll run is interrupted before cursor advance, replaying the same page must be safe via registry idempotency.
- If interrupted after cursor advance, the next run resumes from the next page without missing committed work.

**Account execution rule:** enabled accounts are processed serially in declaration order from the configuration file.

---

## Ingest Lifecycle Journal

The `IngestOperationJournal` (`domain/journal.py`) is a per-operation append-only JSONL file recording coarse phase transitions during the staging-to-pending commit path. It exists as a crash-boundary recovery mechanism, separate from and complementary to the SQLite `audit_log`.

### Role and Relationship to audit_log

| Concern | IngestOperationJournal | audit_log |
|---------|----------------------|-----------|
| Scope | One file per ingest operation, ephemeral | All state transitions, permanent |
| Format | JSONL on disk | SQLite rows |
| Retention | Cleared after successful commit | Append-only, never deleted |
| Purpose | Crash recovery / replay | Audit, operator visibility |

### Phase Sequence

Each ingest operation for one `DownloadedHandoffCandidate` records the following phases in order:

1. `download_started` — download began (recorded by adapter before first byte written)
2. `hash_computed` — SHA-256 computed and canonical identity established
3. `decision_applied` — registry policy decision resolved (pending/discard/duplicate)
4. `finalized` — file moved to destination and registry row committed

### Crash Recovery

On startup (before the first poll), `IngestDecisionEngine.reconcile_interrupted_operations()` reads all journal records and replays any operation that reached `hash_computed` or `decision_applied` but not `finalized`. Replay is safe because all downstream operations are idempotent via `ON CONFLICT DO UPDATE` and `INSERT OR IGNORE` guards.

If `journal_path` is not configured, the journal is disabled and crash recovery falls back to manual staging reconciliation.

---

## StagingDriftReport

The `StagingDriftReport` dataclass classifies the staging directory content on each reconciliation pass:

| Classification | Meaning |
|---------------|---------|
| `stale_temp_count` | `.tmp` files from interrupted downloads; safe to delete |
| `completed_unpersisted_count` | Downloaded files with no journal record; require hash + ingest pass |
| `orphan_unknown_count` | Files in staging with no corresponding journal or registry entry |
| `quarantined_count` | Files quarantined due to zero-byte or integrity check failures |

Zero-byte files discovered during ingest are quarantined (moved to a quarantine directory) and an audit record is appended. They are never silently discarded.

---

## Manual Recovery After Interrupted Poll

If the poll service crashes or is killed mid-run:

**Step 1: Stop the timer**

```bash
systemctl stop nightfall-photo-ingress.timer
```

**Step 2: Inspect staging**

```bash
find /var/lib/ingress/staging -name "*.tmp" -ls
find /var/lib/ingress/staging -type f -ls
```

`.tmp` files are incomplete downloads. Non-`.tmp` files with a corresponding `pending` registry record were downloaded successfully but not finalized.

**Step 3: Run config-check**

```bash
nightfall-photo-ingress config-check --path /etc/nightfall/photo-ingress.conf
```

**Step 4: Remove stale `.tmp` files**

```bash
find /var/lib/ingress/staging -name "*.tmp" -delete
```

**Step 5: Restart the timer**

```bash
systemctl start nightfall-photo-ingress.timer
```

The next triggered poll re-enumerates from the last committed cursor. Registry idempotency ensures already-pending files are not re-ingested.

---

*For the full operator troubleshooting guide, see [docs/operator/troubleshooting.md](../../docs/operator/troubleshooting.md).*  
*For state machine transitions, see [state-machine.md](state-machine.md).*
