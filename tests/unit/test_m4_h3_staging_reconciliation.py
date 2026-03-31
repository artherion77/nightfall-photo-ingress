"""M4-H3 tests for staging reconciliation and drift reporting."""

from __future__ import annotations

import os
import time
from pathlib import Path

from nightfall_photo_ingress.domain.ingest import IngestDecisionEngine
from nightfall_photo_ingress.domain.registry import Registry


def _init_registry(tmp_path: Path) -> Registry:
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    return registry


def _touch(path: Path, payload: bytes, age_seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    now = time.time()
    os.utime(path, (now - age_seconds, now - age_seconds))


def test_reconcile_classifies_and_quarantines_drift(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"

    _touch(staging / "a.tmp", b"tmp", age_seconds=3600)
    _touch(staging / "b.bin", b"old-complete", age_seconds=8000)
    _touch(staging / "c.bin", b"orphan", age_seconds=90000)
    _touch(staging / "fresh.tmp", b"fresh", age_seconds=10)

    report = engine.reconcile_staging_drift(
        staging_dir=staging,
        quarantine_dir=quarantine,
        tmp_ttl_minutes=10,
        failed_ttl_hours=1,
        orphan_ttl_days=1,
        warning_threshold=2,
    )

    assert report.stale_temp_count == 1
    assert report.completed_unpersisted_count == 1
    assert report.orphan_unknown_count == 1
    assert report.quarantined_count == 3
    assert (quarantine / "stale_temp" / "a.tmp").exists()
    assert (quarantine / "completed_unpersisted" / "b.bin").exists()
    assert (quarantine / "orphan_unknown" / "c.bin").exists()
    assert (staging / "fresh.tmp").exists()


def test_reconcile_emits_threshold_warnings(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"

    _touch(staging / "t1.tmp", b"x", age_seconds=3600)
    _touch(staging / "t2.tmp", b"y", age_seconds=3600)

    report = engine.reconcile_staging_drift(
        staging_dir=staging,
        quarantine_dir=quarantine,
        tmp_ttl_minutes=10,
        failed_ttl_hours=1,
        orphan_ttl_days=1,
        warning_threshold=2,
    )

    assert any(item.startswith("stale_temp_threshold_exceeded:") for item in report.warnings)


def test_reconcile_empty_staging_returns_zero_counts(tmp_path: Path) -> None:
    registry = _init_registry(tmp_path)
    engine = IngestDecisionEngine(registry)

    report = engine.reconcile_staging_drift(
        staging_dir=tmp_path / "missing",
        quarantine_dir=tmp_path / "quarantine",
        tmp_ttl_minutes=10,
        failed_ttl_hours=1,
        orphan_ttl_days=1,
    )

    assert report.stale_temp_count == 0
    assert report.completed_unpersisted_count == 0
    assert report.orphan_unknown_count == 0
    assert report.quarantined_count == 0
