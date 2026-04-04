from __future__ import annotations

import json
from pathlib import Path

from metrics.runner.backend_collector import collect_dependency_graph, collect_loc, run_backend_collection


def test_collect_loc_counts_python_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text("# comment\nprint('x')\n", encoding="utf-8")
    (tmp_path / "api").mkdir(parents=True)
    (tmp_path / "api" / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    payload = collect_loc(tmp_path, ["src", "api", "tests"])
    assert payload["status"] == "success"
    assert payload["files"] == 2
    assert payload["total_lines"] == 4
    assert payload["total_code_lines"] == 3


def test_collect_dependency_graph_extracts_imports(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "imports.py").write_text(
        "import os\nfrom collections import defaultdict\n",
        encoding="utf-8",
    )

    payload = collect_dependency_graph(tmp_path, ["src"])
    assert payload["status"] == "success"
    assert payload["nodes"] == ["src/imports.py"]
    assert {edge["to"] for edge in payload["edges"]} == {"os", "collections"}


def test_run_backend_collection_writes_latest_and_history_artifacts(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "api").mkdir(parents=True)
    (tmp_path / "api" / "m.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    run_backend_collection(
        repo_root=tmp_path,
        run_id="module2-test",
        pytest_target="tests",
        skip_pytest=True,
    )

    latest_manifest = tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json"
    latest_metrics = tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json"
    history_manifest = tmp_path / "artifacts" / "metrics" / "history" / "module2-test" / "manifest.json"
    history_metrics = tmp_path / "artifacts" / "metrics" / "history" / "module2-test" / "metrics.json"
    backend_output = tmp_path / "metrics" / "output" / "backend" / "module2-test" / "backend_metrics.json"

    assert latest_manifest.exists()
    assert latest_metrics.exists()
    assert history_manifest.exists()
    assert history_metrics.exists()
    assert backend_output.exists()

    manifest_payload = json.loads(latest_manifest.read_text(encoding="utf-8"))
    metrics_payload = json.loads(latest_metrics.read_text(encoding="utf-8"))

    assert manifest_payload["schema_version"] == 1
    assert metrics_payload["schema_version"] == 1
    assert manifest_payload["run_id"] == "module2-test"
    assert metrics_payload["run_id"] == "module2-test"
    assert metrics_payload["modules"]["backend"]["metrics"]["coverage"]["status"] == "not_available"
