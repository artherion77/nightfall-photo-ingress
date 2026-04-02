"""Ingest decision engine for the ingest pipeline.

This module takes staged candidates from the OneDrive client, computes authoritative
content hashes, applies registry-backed policy decisions, and persists files in
accepted queue storage without touching the permanent library.
"""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..live_photo import DeferredPairQueue, LivePhotoCandidate, LivePhotoHeuristics
from .registry import Registry
from .storage import (
    commit_staging_to_accepted,
    choose_collision_safe_destination_with_threshold,
    lint_storage_template,
    render_storage_relative_path,
    sha256_file,
)
from .journal import IngestOperationJournal


class IngestError(RuntimeError):
    """Raised when ingest engine processing fails."""


INGEST_INPUT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StagedCandidate:
    """Candidate file and metadata passed from download stage to ingest stage."""

    account_name: str
    onedrive_id: str
    original_filename: str
    relative_path: str
    modified_time: str
    size_bytes: int | None
    staging_path: Path


@dataclass(frozen=True)
class IngestOutcome:
    """Result for processing one staged candidate."""

    account_name: str
    onedrive_id: str
    action: str
    sha256: str | None
    destination_path: Path | None
    prefilter_hit: bool


@dataclass(frozen=True)
class IngestBatchResult:
    """Summary of one ingest batch run."""

    outcomes: tuple[IngestOutcome, ...]
    pending_count: int
    discarded_count: int
    prefilter_discard_count: int
    prefilter_hit_count: int
    prefilter_miss_count: int
    size_mismatch_count: int
    zero_byte_reject_count: int
    zero_byte_quarantine_count: int


@dataclass(frozen=True)
class StagingDriftReport:
    """Classification summary for staging reconciliation passes."""

    stale_temp_count: int
    completed_unpersisted_count: int
    orphan_unknown_count: int
    quarantined_count: int
    warnings: tuple[str, ...]


class IngestDecisionEngine:
    """Apply ingest policy matrix for staged files.

    Decision matrix:
    - unknown hash: persist into accepted queue and mark accepted
    - accepted/rejected/purged known hash: discard staged file
    """

    def __init__(
        self,
        registry: Registry,
        *,
        journal_path: Path | None = None,
        journal_max_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self._registry = registry
        self._journal = (
            IngestOperationJournal(path=journal_path, max_bytes=journal_max_bytes)
            if journal_path is not None
            else None
        )

    def process_batch(
        self,
        *,
        candidates: list[StagedCandidate],
        pending_root: Path | None = None,
        storage_template: str,
        staging_on_same_pool: bool,
        input_schema_version: int = INGEST_INPUT_SCHEMA_VERSION,
        pre_hash_size_verify: bool = True,
        zero_byte_policy: str = "allow",
        quarantine_dir: Path | None = None,
        worker_count: int = 1,
        size_aware_scheduling: bool = True,
        collision_max_attempts: int = 10_000,
        live_photo_heuristics: LivePhotoHeuristics | None = None,
        accepted_root: Path | None = None,  # deprecated: use pending_root instead
    ) -> IngestBatchResult:
        """Process staged candidates and return batch summary."""

        # Support legacy accepted_root kwarg as alias for pending_root
        _pending_root = pending_root if pending_root is not None else accepted_root
        if _pending_root is None:
            raise IngestError("pending_root is required")

        self._validate_batch_contract(
            candidates=candidates,
            input_schema_version=input_schema_version,
        )
        if zero_byte_policy not in {"allow", "quarantine", "reject"}:
            raise IngestError(
                "Invalid zero_byte_policy: "
                f"{zero_byte_policy}. Expected one of allow/quarantine/reject"
            )
        if worker_count < 1:
            raise IngestError("worker_count must be >= 1")
        if collision_max_attempts < 1:
            raise IngestError("collision_max_attempts must be >= 1")

        template_findings = lint_storage_template(storage_template)
        if template_findings:
            raise IngestError(
                "Unsafe storage template detected: " + ",".join(template_findings)
            )

        outcomes: list[IngestOutcome] = []
        batch_run_id = uuid4().hex
        sequence_no = 0
        pair_queue = DeferredPairQueue(live_photo_heuristics) if live_photo_heuristics is not None else None
        sha_by_onedrive_id: dict[str, str] = {}

        indexed_candidates = list(enumerate(candidates))
        if size_aware_scheduling:
            indexed_candidates.sort(
                key=lambda item: ((item[1].size_bytes if item[1].size_bytes is not None else -1), -item[0]),
                reverse=True,
            )

        if worker_count <= 1:
            ordered_results = [
                (
                    index,
                    candidate,
                    self._process_one(
                        candidate=candidate,
                        pending_root=_pending_root,
                        storage_template=storage_template,
                        staging_on_same_pool=staging_on_same_pool,
                        pre_hash_size_verify=pre_hash_size_verify,
                        zero_byte_policy=zero_byte_policy,
                        quarantine_dir=quarantine_dir,
                        collision_max_attempts=collision_max_attempts,
                    ),
                )
                for index, candidate in indexed_candidates
            ]
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(
                        self._process_one,
                        candidate=candidate,
                        pending_root=_pending_root,
                        storage_template=storage_template,
                        staging_on_same_pool=staging_on_same_pool,
                        pre_hash_size_verify=pre_hash_size_verify,
                        zero_byte_policy=zero_byte_policy,
                        quarantine_dir=quarantine_dir,
                        collision_max_attempts=collision_max_attempts,
                    ): (index, candidate)
                    for index, candidate in indexed_candidates
                }
                ordered_results = [
                    (index, candidate, future.result())
                    for future, (index, candidate) in futures.items()
                ]

        ordered_results.sort(key=lambda item: item[0])

        for _index, candidate, outcome in ordered_results:
            outcomes.append(outcome)
            if outcome.sha256 is not None:
                sha_by_onedrive_id[candidate.onedrive_id] = outcome.sha256

            if pair_queue is not None:
                pair = pair_queue.ingest(
                    LivePhotoCandidate(
                        account=candidate.account_name,
                        onedrive_id=candidate.onedrive_id,
                        filename=candidate.original_filename,
                        captured_at=candidate.modified_time,
                    )
                )
                if pair is not None:
                    photo_sha = sha_by_onedrive_id.get(pair.photo_onedrive_id)
                    video_sha = sha_by_onedrive_id.get(pair.video_onedrive_id)
                    if photo_sha is not None and video_sha is not None:
                        self._registry.upsert_live_photo_pair(
                            pair_id=_live_photo_pair_id(
                                account=pair.account,
                                stem=pair.stem,
                                photo_sha256=photo_sha,
                                video_sha256=video_sha,
                            ),
                            account=pair.account,
                            stem=pair.stem,
                            photo_sha256=photo_sha,
                            video_sha256=video_sha,
                            status="paired",
                        )

            sequence_no += 1
            self._registry.append_ingest_terminal_event(
                batch_run_id=batch_run_id,
                sequence_no=sequence_no,
                account=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                sha256=outcome.sha256,
                action=outcome.action,
                reason=self._terminal_reason_from_outcome(outcome),
                actor="ingest_pipeline",
            )

        pending_count = sum(1 for item in outcomes if item.action == "pending")
        discarded_count = sum(
            1
            for item in outcomes
            if item.action in {"discard_accepted", "discard_rejected", "discard_purged", "discard_pending", "missing_staged"}
        )
        prefilter_discard_count = sum(1 for item in outcomes if item.prefilter_hit)
        prefilter_hit_count = sum(1 for item in outcomes if item.prefilter_hit)
        prefilter_miss_count = sum(1 for item in outcomes if not item.prefilter_hit)
        size_mismatch_count = sum(1 for item in outcomes if item.action == "size_mismatch")
        zero_byte_reject_count = sum(1 for item in outcomes if item.action == "reject_zero_byte")
        zero_byte_quarantine_count = sum(1 for item in outcomes if item.action == "quarantine_zero_byte")

        return IngestBatchResult(
            outcomes=tuple(outcomes),
            pending_count=pending_count,
            discarded_count=discarded_count,
            prefilter_discard_count=prefilter_discard_count,
            prefilter_hit_count=prefilter_hit_count,
            prefilter_miss_count=prefilter_miss_count,
            size_mismatch_count=size_mismatch_count,
            zero_byte_reject_count=zero_byte_reject_count,
            zero_byte_quarantine_count=zero_byte_quarantine_count,
        )

    def cleanup_staging_tmp_files(self, *, staging_dir: Path, tmp_ttl_minutes: int) -> int:
        """Remove expired .tmp files from staging.

        Returns the number of removed temp files.
        """

        if not staging_dir.exists():
            return 0

        now = datetime.now(UTC).timestamp()
        ttl_seconds = max(1, tmp_ttl_minutes) * 60
        removed = 0

        for tmp in staging_dir.rglob("*.tmp"):
            try:
                age = now - tmp.stat().st_mtime
            except OSError:
                continue
            if age > ttl_seconds:
                tmp.unlink(missing_ok=True)
                removed += 1

        return removed

    def reconcile_staging_drift(
        self,
        *,
        staging_dir: Path,
        quarantine_dir: Path,
        tmp_ttl_minutes: int,
        failed_ttl_hours: int,
        orphan_ttl_days: int,
        warning_threshold: int = 10,
    ) -> StagingDriftReport:
        """Reconcile staging drift with explicit classification and quarantine.

        Categories:
        - stale temp: expired .tmp files
        - completed-but-unpersisted: completed files older than failed TTL
        - orphan unknown: files older than orphan TTL
        """

        if not staging_dir.exists():
            return StagingDriftReport(
                stale_temp_count=0,
                completed_unpersisted_count=0,
                orphan_unknown_count=0,
                quarantined_count=0,
                warnings=(),
            )

        now = datetime.now(UTC).timestamp()
        stale_temp = 0
        completed_unpersisted = 0
        orphan_unknown = 0
        quarantined = 0

        tmp_ttl_seconds = max(1, tmp_ttl_minutes) * 60
        failed_ttl_seconds = max(1, failed_ttl_hours) * 3600
        orphan_ttl_seconds = max(1, orphan_ttl_days) * 86400

        for candidate in staging_dir.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                age = now - candidate.stat().st_mtime
            except OSError:
                continue

            category: str | None = None
            if candidate.suffix == ".tmp" and age > tmp_ttl_seconds:
                stale_temp += 1
                category = "stale_temp"
            elif candidate.suffix != ".tmp" and age > orphan_ttl_seconds:
                orphan_unknown += 1
                category = "orphan_unknown"
            elif candidate.suffix != ".tmp" and age > failed_ttl_seconds:
                completed_unpersisted += 1
                category = "completed_unpersisted"

            if category is None:
                continue

            quarantine_path = quarantine_dir / category / candidate.name
            quarantine_path.parent.mkdir(parents=True, exist_ok=True)
            if quarantine_path.exists():
                quarantine_path = quarantine_path.with_name(
                    f"{quarantine_path.stem}-{int(now)}{quarantine_path.suffix}"
                )
            candidate.replace(quarantine_path)
            quarantined += 1

        warnings: list[str] = []
        if stale_temp >= warning_threshold:
            warnings.append(f"stale_temp_threshold_exceeded:{stale_temp}")
        if completed_unpersisted >= warning_threshold:
            warnings.append(f"completed_unpersisted_threshold_exceeded:{completed_unpersisted}")
        if orphan_unknown >= warning_threshold:
            warnings.append(f"orphan_unknown_threshold_exceeded:{orphan_unknown}")

        return StagingDriftReport(
            stale_temp_count=stale_temp,
            completed_unpersisted_count=completed_unpersisted,
            orphan_unknown_count=orphan_unknown,
            quarantined_count=quarantined,
            warnings=tuple(warnings),
        )

    def replay_interrupted_operations(self) -> dict[str, object]:
        """Reconcile interrupted ingest operations recorded in lifecycle journal."""

        if self._journal is None:
            return {
                "interrupted_total": 0,
                "quarantined_destinations": 0,
                "removed_staging": 0,
                "unresolved_op_ids": tuple(),
            }

        records = self._journal.read_all()
        by_op: dict[str, list] = {}
        for record in records:
            by_op.setdefault(record.op_id, []).append(record)

        interrupted_total = 0
        quarantined_destinations = 0
        removed_staging = 0
        unresolved_op_ids: list[str] = []

        for op_id, op_records in by_op.items():
            phases = {item.phase for item in op_records}
            if "registry_persisted" in phases:
                continue

            interrupted_total += 1
            unresolved_op_ids.append(op_id)
            latest = op_records[-1]
            staging_path = Path(latest.staging_path)
            destination_path = Path(latest.destination_path) if latest.destination_path else None

            if destination_path is not None and destination_path.exists():
                quarantine = destination_path.with_suffix(destination_path.suffix + ".orphaned")
                destination_path.replace(quarantine)
                quarantined_destinations += 1

            if staging_path.exists():
                staging_path.unlink(missing_ok=True)
                removed_staging += 1

            if latest.sha256 is not None and self._registry.get_file(sha256=latest.sha256) is not None:
                self._registry.append_audit_event(
                    sha256=latest.sha256,
                    action="recovery_interrupted_ingest",
                    reason=f"journal_replay:{op_id}",
                    actor="ingest_pipeline",
                )

        self._journal.clear()
        return {
            "interrupted_total": interrupted_total,
            "quarantined_destinations": quarantined_destinations,
            "removed_staging": removed_staging,
            "unresolved_op_ids": tuple(unresolved_op_ids),
        }

    def _process_one(
        self,
        *,
        candidate: StagedCandidate,
        pending_root: Path,
        storage_template: str,
        staging_on_same_pool: bool,
        pre_hash_size_verify: bool,
        zero_byte_policy: str,
        quarantine_dir: Path | None,
        collision_max_attempts: int,
    ) -> IngestOutcome:
        """Process one staged candidate through prefilter and hash decisioning."""

        path = candidate.staging_path
        op_id = f"{candidate.account_name}:{candidate.onedrive_id}:{uuid4().hex[:12]}"

        self._journal_append(
            op_id=op_id,
            phase="ingest_started",
            candidate=candidate,
        )

        if not path.exists():
            self._journal_append(
                op_id=op_id,
                phase="missing_staged",
                candidate=candidate,
            )
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action="missing_staged",
                sha256=None,
                destination_path=None,
                prefilter_hit=False,
            )

        actual_size = path.stat().st_size
        if pre_hash_size_verify and candidate.size_bytes is not None and candidate.size_bytes != actual_size:
            self._journal_append(
                op_id=op_id,
                phase="size_mismatch",
                candidate=candidate,
            )
            self._handle_quarantine_or_delete(
                path=path,
                quarantine_dir=quarantine_dir,
                category="size_mismatch",
            )
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action="size_mismatch",
                sha256=None,
                destination_path=None,
                prefilter_hit=False,
            )

        if actual_size == 0:
            if zero_byte_policy == "reject":
                path.unlink(missing_ok=True)
                return IngestOutcome(
                    account_name=candidate.account_name,
                    onedrive_id=candidate.onedrive_id,
                    action="reject_zero_byte",
                    sha256=None,
                    destination_path=None,
                    prefilter_hit=False,
                )
            if zero_byte_policy == "quarantine":
                self._handle_quarantine_or_delete(
                    path=path,
                    quarantine_dir=quarantine_dir,
                    category="zero_byte",
                )
                return IngestOutcome(
                    account_name=candidate.account_name,
                    onedrive_id=candidate.onedrive_id,
                    action="quarantine_zero_byte",
                    sha256=None,
                    destination_path=None,
                    prefilter_hit=False,
                )

        # Metadata prefilter can skip expensive hashing for known OneDrive id+metadata.
        prefiltered = self._prefilter_status(candidate)
        if prefiltered is not None:
            path.unlink(missing_ok=True)
            self._registry.append_audit_event(
                sha256=prefiltered[1],
                action=f"prefilter_{prefiltered[0]}",
                reason="metadata_index_match",
                actor="ingest_pipeline",
            )
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action=f"discard_{prefiltered[0]}",
                sha256=prefiltered[1],
                destination_path=None,
                prefilter_hit=True,
            )

        file_hash = sha256_file(path)
        self._journal_append(
            op_id=op_id,
            phase="hash_completed",
            candidate=candidate,
            sha256=file_hash,
        )
        record = self._registry.get_file(sha256=file_hash)

        if record is None:
            relative = render_storage_relative_path(
                storage_template=storage_template,
                sha256=file_hash,
                original_filename=candidate.original_filename,
                modified_time_iso=candidate.modified_time,
            )
            destination = choose_collision_safe_destination_with_threshold(
                base_path=pending_root / relative,
                max_attempts=collision_max_attempts,
            )
            commit_staging_to_accepted(
                source_path=path,
                destination_path=destination,
                staging_on_same_pool=staging_on_same_pool,
                destination_root=pending_root,
            )
            self._journal_append(
                op_id=op_id,
                phase="storage_committed",
                candidate=candidate,
                destination_path=destination,
                sha256=file_hash,
            )

            size_bytes = destination.stat().st_size
            self._registry.finalize_unknown_ingest(
                sha256=file_hash,
                size_bytes=size_bytes,
                original_filename=candidate.original_filename,
                current_path=str(destination),
                account=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                source_path=candidate.relative_path,
                modified_time=candidate.modified_time,
                actor="ingest_pipeline",
            )
            self._journal_append(
                op_id=op_id,
                phase="registry_persisted",
                candidate=candidate,
                destination_path=destination,
                sha256=file_hash,
            )
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action="pending",
                sha256=file_hash,
                destination_path=destination,
                prefilter_hit=False,
            )

        known_size = path.stat().st_size
        path.unlink(missing_ok=True)
        self._registry.finalize_known_ingest(
            sha256=file_hash,
            known_status=record.status,
            account=candidate.account_name,
            onedrive_id=candidate.onedrive_id,
            source_path=candidate.relative_path,
            modified_time=candidate.modified_time,
            size_bytes=known_size,
            actor="ingest_pipeline",
        )
        self._journal_append(
            op_id=op_id,
            phase="registry_persisted",
            candidate=candidate,
            sha256=file_hash,
        )
        return IngestOutcome(
            account_name=candidate.account_name,
            onedrive_id=candidate.onedrive_id,
            action=f"discard_{record.status}",
            sha256=file_hash,
            destination_path=None,
            prefilter_hit=False,
        )

    def _prefilter_status(self, candidate: StagedCandidate) -> tuple[str, str] | None:
        """Return (status, sha256) when metadata index exactly matches known record."""

        db_path = self._registry.db_path
        if not db_path.exists():
            return None

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT m.sha256 AS sha256, f.status AS status
                FROM metadata_index AS m
                JOIN files AS f ON f.sha256 = m.sha256
                                WHERE m.account_name = ?
                  AND m.onedrive_id = ?
                  AND m.size_bytes = ?
                  AND m.modified_time = ?
                LIMIT 1
                """,
                (
                    candidate.account_name,
                    candidate.onedrive_id,
                    candidate.size_bytes if candidate.size_bytes is not None else -1,
                    candidate.modified_time,
                ),
            ).fetchone()

        if row is None:
            return None

        status = str(row["status"])
        sha256 = str(row["sha256"])
        if status not in {"pending", "accepted", "rejected", "purged"}:
            return None
        return status, sha256

    def _validate_batch_contract(
        self,
        *,
        candidates: list[StagedCandidate],
        input_schema_version: int,
    ) -> None:
        """Fail fast when ingest boundary payload is incompatible or malformed."""

        if input_schema_version != INGEST_INPUT_SCHEMA_VERSION:
            raise IngestError(
                "Incompatible ingest input schema version: "
                f"got={input_schema_version} expected={INGEST_INPUT_SCHEMA_VERSION}"
            )

        for index, candidate in enumerate(candidates):
            if not candidate.account_name.strip():
                raise IngestError(f"Malformed candidate[{index}]: account_name is required")
            if not candidate.onedrive_id.strip():
                raise IngestError(f"Malformed candidate[{index}]: onedrive_id is required")
            if not candidate.original_filename.strip():
                raise IngestError(f"Malformed candidate[{index}]: original_filename is required")
            if not candidate.relative_path.startswith("/"):
                raise IngestError(
                    f"Malformed candidate[{index}]: relative_path must start with '/': {candidate.relative_path}"
                )
            try:
                datetime.fromisoformat(candidate.modified_time.replace("Z", "+00:00"))
            except ValueError as exc:
                raise IngestError(
                    f"Malformed candidate[{index}]: modified_time is not valid ISO-8601"
                ) from exc
            if candidate.size_bytes is not None and candidate.size_bytes < 0:
                raise IngestError(f"Malformed candidate[{index}]: size_bytes must be >= 0")

    def _journal_append(
        self,
        *,
        op_id: str,
        phase: str,
        candidate: StagedCandidate,
        destination_path: Path | None = None,
        sha256: str | None = None,
    ) -> None:
        if self._journal is None:
            return
        self._journal.append(
            op_id=op_id,
            phase=phase,
            account=candidate.account_name,
            onedrive_id=candidate.onedrive_id,
            staging_path=candidate.staging_path,
            destination_path=destination_path,
            sha256=sha256,
        )

    @staticmethod
    def _terminal_reason_from_outcome(outcome: IngestOutcome) -> str:
        """Return normalized reason metadata for terminal outcome events."""

        if outcome.prefilter_hit:
            return "metadata_prefilter"
        if outcome.action == "pending":
            return "unknown_hash"
        if outcome.action.startswith("discard_"):
            return "known_hash"
        if outcome.action in {"missing_staged", "size_mismatch", "reject_zero_byte", "quarantine_zero_byte"}:
            return outcome.action
        return "terminal_outcome"

    @staticmethod
    def _handle_quarantine_or_delete(*, path: Path, quarantine_dir: Path | None, category: str) -> None:
        """Move problematic files to quarantine when configured, else delete."""

        if quarantine_dir is None:
            path.unlink(missing_ok=True)
            return

        target = quarantine_dir / category / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.stem}-{int(datetime.now(UTC).timestamp())}{target.suffix}")
        path.replace(target)


def _live_photo_pair_id(
    *,
    account: str,
    stem: str,
    photo_sha256: str,
    video_sha256: str,
) -> str:
    """Build deterministic pair ID stable across ingest replays."""

    raw = f"{account}|{stem}|{photo_sha256}|{video_sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
