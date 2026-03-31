"""Lifecycle journal helpers for ingest crash-boundary recovery.

The journal is append-only JSONL and records phase transitions for each ingest
operation. It supports durable writes and lightweight rotation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class JournalRecord:
    """One lifecycle entry parsed from the ingest operation journal."""

    op_id: str
    phase: str
    ts: str
    account: str
    onedrive_id: str
    staging_path: str
    destination_path: str | None
    sha256: str | None


class IngestOperationJournal:
    """Append-only lifecycle journal with durable writes and rotation."""

    def __init__(self, *, path: Path, max_bytes: int = 5 * 1024 * 1024) -> None:
        self._path = path
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        """Return configured journal path."""

        return self._path

    def append(
        self,
        *,
        op_id: str,
        phase: str,
        account: str,
        onedrive_id: str,
        staging_path: Path,
        destination_path: Path | None = None,
        sha256: str | None = None,
    ) -> None:
        """Append one durable JSONL entry to the journal."""

        self._rotate_if_needed()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "op_id": op_id,
            "phase": phase,
            "ts": datetime.now(UTC).isoformat(),
            "account": account,
            "onedrive_id": onedrive_id,
            "staging_path": str(staging_path),
            "destination_path": str(destination_path) if destination_path is not None else None,
            "sha256": sha256,
        }
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read_all(self) -> list[JournalRecord]:
        """Read and parse all valid journal records."""

        if not self._path.exists():
            return []

        records: list[JournalRecord] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                op_id = str(raw.get("op_id", "")).strip()
                phase = str(raw.get("phase", "")).strip()
                if not op_id or not phase:
                    continue
                records.append(
                    JournalRecord(
                        op_id=op_id,
                        phase=phase,
                        ts=str(raw.get("ts", "")),
                        account=str(raw.get("account", "")),
                        onedrive_id=str(raw.get("onedrive_id", "")),
                        staging_path=str(raw.get("staging_path", "")),
                        destination_path=(
                            str(raw.get("destination_path"))
                            if raw.get("destination_path") is not None
                            else None
                        ),
                        sha256=str(raw.get("sha256")) if raw.get("sha256") is not None else None,
                    )
                )
        return records

    def clear(self) -> None:
        """Delete active journal file after successful replay/reconcile."""

        self._path.unlink(missing_ok=True)

    def _rotate_if_needed(self) -> None:
        if not self._path.exists():
            return
        if self._path.stat().st_size < self._max_bytes:
            return
        rotated = self._path.with_suffix(self._path.suffix + ".1")
        rotated.unlink(missing_ok=True)
        self._path.replace(rotated)
