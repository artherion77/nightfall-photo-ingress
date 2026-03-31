"""Ingest decision engine for the ingest pipeline.

This module takes staged candidates from the OneDrive client, computes authoritative
content hashes, applies registry-backed policy decisions, and persists files in
accepted queue storage without touching the permanent library.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..registry import Registry
from ..storage import (
    commit_staging_to_accepted,
    choose_collision_safe_destination,
    render_storage_relative_path,
    sha256_file,
)


class IngestError(RuntimeError):
    """Raised when ingest engine processing fails."""


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
    accepted_count: int
    discarded_count: int
    prefilter_discard_count: int


class IngestDecisionEngine:
    """Apply ingest policy matrix for staged files.

    Decision matrix:
    - unknown hash: persist into accepted queue and mark accepted
    - accepted/rejected/purged known hash: discard staged file
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def process_batch(
        self,
        *,
        candidates: list[StagedCandidate],
        accepted_root: Path,
        storage_template: str,
        staging_on_same_pool: bool,
    ) -> IngestBatchResult:
        """Process staged candidates and return batch summary."""

        outcomes: list[IngestOutcome] = []

        for candidate in candidates:
            outcome = self._process_one(
                candidate=candidate,
                accepted_root=accepted_root,
                storage_template=storage_template,
                staging_on_same_pool=staging_on_same_pool,
            )
            outcomes.append(outcome)

        accepted_count = sum(1 for item in outcomes if item.action == "accepted")
        discarded_count = sum(
            1
            for item in outcomes
            if item.action in {"discard_accepted", "discard_rejected", "discard_purged", "missing_staged"}
        )
        prefilter_discard_count = sum(1 for item in outcomes if item.prefilter_hit)

        return IngestBatchResult(
            outcomes=tuple(outcomes),
            accepted_count=accepted_count,
            discarded_count=discarded_count,
            prefilter_discard_count=prefilter_discard_count,
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

    def _process_one(
        self,
        *,
        candidate: StagedCandidate,
        accepted_root: Path,
        storage_template: str,
        staging_on_same_pool: bool,
    ) -> IngestOutcome:
        """Process one staged candidate through prefilter and hash decisioning."""

        path = candidate.staging_path
        if not path.exists():
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action="missing_staged",
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
        record = self._registry.get_file(sha256=file_hash)

        if record is None:
            relative = render_storage_relative_path(
                storage_template=storage_template,
                sha256=file_hash,
                original_filename=candidate.original_filename,
                modified_time_iso=candidate.modified_time,
            )
            destination = choose_collision_safe_destination(accepted_root / relative)
            commit_staging_to_accepted(
                source_path=path,
                destination_path=destination,
                staging_on_same_pool=staging_on_same_pool,
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
            return IngestOutcome(
                account_name=candidate.account_name,
                onedrive_id=candidate.onedrive_id,
                action="accepted",
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
                WHERE m.account = ?
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
        if status not in {"accepted", "rejected", "purged"}:
            return None
        return status, sha256
