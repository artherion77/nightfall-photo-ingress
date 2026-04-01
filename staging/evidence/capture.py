"""Evidence capture context manager for staging runs.

Usage inside a staging test or script::

    from staging.evidence.capture import EvidenceRun

    with EvidenceRun(base_dir="/var/lib/ingress/evidence") as run:
        run.record_counter("requests", 3)
        run.record_counter("throttles", 0)
        run.snapshot("pre_registry", {"row_count": 0})
        run.audit("config_check", result="pass", detail="config valid")
        ...
        run.snapshot("post_registry", {"row_count": 5})
    # On exit, finishes manifest and writes summary.json

The run_id is a timestamp-prefixed UUIDv4 string suitable for sorting.
Use ``run.run_id`` to retrieve it for external reference.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id() -> str:
    """Return a sortable run-id: yyyymmddTHHMMSS-<uuid4>."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{uuid.uuid4()}"


class EvidenceRun:
    """Context manager that owns a single evidence run directory."""

    def __init__(self, base_dir: str | Path, run_id: str | None = None) -> None:
        self._base = Path(base_dir)
        self.run_id: str = run_id or _make_run_id()
        self._dir: Path = self._base / self.run_id
        self._counters: dict[str, int] = {}
        self._audit_rows: list[dict[str, Any]] = []
        self._started_at: str = ""

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "EvidenceRun":
        self._dir.mkdir(parents=True, exist_ok=True)
        self._started_at = _now_iso()
        self._write_jsonl(
            "manifest.jsonl",
            {"event": "run_started", "run_id": self.run_id, "ts": self._started_at},
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        finished_at = _now_iso()
        ok = exc_type is None

        # Persist counters
        (self._dir / "counters.json").write_text(
            json.dumps(self._counters, indent=2),
            encoding="utf-8",
        )

        # Persist audit rows
        audit_path = self._dir / "audit.jsonl"
        with audit_path.open("w", encoding="utf-8") as fh:
            for row in self._audit_rows:
                fh.write(json.dumps(row) + "\n")

        # Summary
        summary = {
            "run_id": self.run_id,
            "started_at": self._started_at,
            "finished_at": finished_at,
            "success": ok,
            "counters": self._counters,
            "audit_row_count": len(self._audit_rows),
        }
        (self._dir / "summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        self._write_jsonl(
            "manifest.jsonl",
            {"event": "run_finished", "run_id": self.run_id, "ts": finished_at, "success": ok},
        )
        # Never suppress exceptions
        return False

    # ── public API ────────────────────────────────────────────────────────────

    def record_counter(self, name: str, value: int) -> None:
        """Set or increment a named counter."""
        self._counters[name] = self._counters.get(name, 0) + value

    def audit(self, assertion: str, *, result: str, detail: str = "") -> None:
        """Append one assertion audit row (result: 'pass' | 'fail' | 'skip')."""
        row: dict[str, Any] = {
            "assertion": assertion,
            "result": result,
            "detail": detail,
            "ts": _now_iso(),
        }
        self._audit_rows.append(row)
        self._write_jsonl("assertions.jsonl", row)

    def snapshot(self, label: str, state: dict[str, Any]) -> None:
        """Write a named state snapshot to <label>.json."""
        path = self._dir / f"snapshot-{label}.json"
        path.write_text(json.dumps({"label": label, "ts": _now_iso(), "state": state}, indent=2))

    def write_file(self, name: str, content: str | bytes) -> Path:
        """Write an arbitrary artefact into the evidence directory."""
        path = self._dir / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    @property
    def directory(self) -> Path:
        return self._dir

    # ── internal ─────────────────────────────────────────────────────────────

    def _write_jsonl(self, filename: str, row: dict[str, Any]) -> None:
        path = self._dir / filename
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
