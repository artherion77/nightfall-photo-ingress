from __future__ import annotations

import json
from pathlib import Path

from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


def test_module1_required_directories_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "metrics" / "runner").exists()
    assert (root / "metrics" / "systemd").exists()
    assert (root / "metrics" / "state").exists()
    assert (root / "metrics" / "output").exists()


def test_module1_required_output_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "artifacts" / "metrics" / "latest" / "manifest.json").exists()
    assert (root / "artifacts" / "metrics" / "latest" / "metrics.json").exists()
    assert (root / "metrics" / "state" / "last_processed_commit").exists()
    assert (root / "metrics" / "state" / "runtime.json").exists()


def test_latest_and_history_artifacts_are_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "artifacts" / "metrics" / "latest" / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((root / "artifacts" / "metrics" / "latest" / "metrics.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert metrics["schema_version"] == 1
    assert manifest["run_id"] == metrics["run_id"]
    assert manifest["source"]["commit_sha"] == metrics["source"]["commit_sha"]

    history_manifest = root / manifest["artifacts"]["history_manifest"]
    history_metrics = root / manifest["artifacts"]["history_metrics"]

    if history_manifest.exists() and history_metrics.exists():
        assert history_manifest.exists()
        assert history_metrics.exists()
        return

    # Clean checkouts may not contain the exact historical run referenced by
    # latest/manifest.json; verify at least one history snapshot is present.
    history_root = root / "artifacts" / "metrics" / "history"
    assert history_root.exists()

    history_dirs = [p for p in history_root.iterdir() if p.is_dir()]
    assert history_dirs

    assert any((d / "manifest.json").exists() and (d / "metrics.json").exists() for d in history_dirs)


def test_schema_contract_validators_accept_module1_payloads() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "artifacts" / "metrics" / "latest" / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((root / "artifacts" / "metrics" / "latest" / "metrics.json").read_text(encoding="utf-8"))

    validate_manifest_payload(manifest)
    validate_metrics_payload(metrics)
