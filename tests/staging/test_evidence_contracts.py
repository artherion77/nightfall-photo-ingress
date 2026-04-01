"""Evidence contract tests — no container required.

These tests verify the EvidenceRun context manager and its output shapes
using only the local evidence library. They are co-located with staging
tests for discoverability, but run fine without a container.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys
_STAGING_DIR = Path(__file__).parent.parent.parent / "staging"
if str(_STAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_STAGING_DIR))

from evidence.capture import EvidenceRun

pytestmark = pytest.mark.staging


class TestEvidenceRunId:
    """run_id is stable and sortable."""

    def test_run_id_has_timestamp_prefix(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            rid = run.run_id
        # yyyymmddTHHMMSS-<uuid4>
        assert len(rid) > 20
        parts = rid.split("-")
        assert len(parts) >= 6, f"unexpected run_id format: {rid}"
        assert parts[0].startswith("20"), f"timestamp prefix missing: {rid}"

    def test_run_id_is_stable_within_context(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            first = run.run_id
            second = run.run_id
        assert first == second

    def test_run_id_is_used_as_directory_name(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            rid = run.run_id
        assert (tmp_path / rid).is_dir()


class TestManifestShape:
    """manifest.jsonl has run_started + run_finished events."""

    def test_manifest_has_two_events(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            pass
        manifest_path = run.directory / "manifest.jsonl"
        assert manifest_path.exists()
        rows = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
        assert len(rows) == 2
        events = [r["event"] for r in rows]
        assert events[0] == "run_started"
        assert events[1] == "run_finished"

    def test_manifest_events_have_run_id(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            rid = run.run_id
        rows = _read_jsonl(run.directory / "manifest.jsonl")
        for row in rows:
            assert row["run_id"] == rid, f"row missing/wrong run_id: {row}"

    def test_manifest_events_have_ts(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            pass
        rows = _read_jsonl(run.directory / "manifest.jsonl")
        for row in rows:
            assert "ts" in row, f"row missing ts: {row}"
            assert row["ts"].endswith("Z"), f"ts not UTC: {row['ts']}"

    def test_manifest_finished_event_has_success_true_on_clean_exit(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            pass
        rows = _read_jsonl(run.directory / "manifest.jsonl")
        finished = next(r for r in rows if r["event"] == "run_finished")
        assert finished["success"] is True

    def test_manifest_finished_event_has_success_false_on_exception(self, tmp_path):
        try:
            with EvidenceRun(base_dir=tmp_path) as run:
                raise RuntimeError("intentional test error")
        except RuntimeError:
            pass
        rows = _read_jsonl(run.directory / "manifest.jsonl")
        finished = next((r for r in rows if r["event"] == "run_finished"), None)
        assert finished is not None
        assert finished["success"] is False


class TestCounters:
    """record_counter accumulates and persists to counters.json."""

    def test_counters_written_to_file(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.record_counter("requests", 5)
            run.record_counter("throttles", 2)
        data = json.loads((run.directory / "counters.json").read_text())
        assert data["requests"] == 5
        assert data["throttles"] == 2

    def test_counter_values_accumulate(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.record_counter("retries", 1)
            run.record_counter("retries", 3)
        data = json.loads((run.directory / "counters.json").read_text())
        assert data["retries"] == 4

    def test_zero_counters_are_persisted(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.record_counter("deltas", 0)
        data = json.loads((run.directory / "counters.json").read_text())
        assert data["deltas"] == 0


class TestAuditRows:
    """audit() appends a JSONL row and writes assertions.jsonl."""

    def test_assertions_jsonl_written(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.audit("check_a", result="pass", detail="ok")
            run.audit("check_b", result="fail", detail="something went wrong")
        rows = _read_jsonl(run.directory / "assertions.jsonl")
        assert len(rows) == 2

    def test_assertion_row_shape(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.audit("my_assertion", result="pass", detail="all good")
        rows = _read_jsonl(run.directory / "assertions.jsonl")
        row = rows[0]
        assert row["assertion"] == "my_assertion"
        assert row["result"] == "pass"
        assert row["detail"] == "all good"
        assert "ts" in row

    def test_audit_row_count_in_summary(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.audit("a1", result="pass")
            run.audit("a2", result="pass")
            run.audit("a3", result="fail")
        summary = json.loads((run.directory / "summary.json").read_text())
        assert summary["audit_row_count"] == 3


class TestStateSnapshots:
    """snapshot() writes labelled JSON state files."""

    def test_snapshot_file_created(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.snapshot("pre_state", {"row_count": 0, "accepted": []})
        assert (run.directory / "snapshot-pre_state.json").exists()

    def test_snapshot_contains_state_and_ts(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.snapshot("post_state", {"row_count": 5})
        data = json.loads((run.directory / "snapshot-post_state.json").read_text())
        assert data["label"] == "post_state"
        assert data["state"]["row_count"] == 5
        assert "ts" in data

    def test_multiple_snapshots_are_independent(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.snapshot("pre", {"x": 1})
            run.snapshot("post", {"x": 99})
        pre = json.loads((run.directory / "snapshot-pre.json").read_text())
        post = json.loads((run.directory / "snapshot-post.json").read_text())
        assert pre["state"]["x"] == 1
        assert post["state"]["x"] == 99


class TestSummaryFile:
    """summary.json has all required top-level keys."""

    def test_summary_has_required_keys(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            pass
        summary = json.loads((run.directory / "summary.json").read_text())
        required = {"run_id", "started_at", "finished_at", "success", "counters", "audit_row_count"}
        missing = required - set(summary.keys())
        assert not missing, f"summary.json missing keys: {missing}"

    def test_summary_counters_matches_recorded_values(self, tmp_path):
        with EvidenceRun(base_dir=tmp_path) as run:
            run.record_counter("requests", 7)
        summary = json.loads((run.directory / "summary.json").read_text())
        assert summary["counters"]["requests"] == 7


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
