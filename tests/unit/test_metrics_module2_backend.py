from __future__ import annotations

import json
from pathlib import Path

from metrics.runner import backend_collector
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


def test_collect_dependency_graph_node_details_fan_in_fan_out_cycle(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    # a.py imports b; b.py imports a → mutual cycle
    (tmp_path / "src" / "a.py").write_text("from src.b import x\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("from src.a import y\n", encoding="utf-8")
    # c.py imports a only; no cycle
    (tmp_path / "src" / "c.py").write_text("from src.a import z\n", encoding="utf-8")

    payload = collect_dependency_graph(tmp_path, ["src"])
    assert payload["status"] == "success"
    assert "node_details" in payload

    details_by_path = {d["path"]: d for d in payload["node_details"]}
    assert set(details_by_path.keys()) == {"src/a.py", "src/b.py", "src/c.py"}

    a = details_by_path["src/a.py"]
    b = details_by_path["src/b.py"]
    c = details_by_path["src/c.py"]

    assert a["fan_out"] == 1  # imports src.b
    assert b["fan_out"] == 1  # imports src.a
    assert c["fan_out"] == 1  # imports src.a

    assert a["fan_in"] == 2  # imported by b and c
    assert b["fan_in"] == 1  # imported by a
    assert c["fan_in"] == 0  # not imported by anyone

    assert a["in_cycle"] is True
    assert b["in_cycle"] is True
    assert c["in_cycle"] is False

    assert a["kind"] == "local"


def test_run_backend_collection_writes_latest_and_history_artifacts(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "api").mkdir(parents=True)
    (tmp_path / "api" / "m.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "test_dummy.py").write_text(
        "from src.m import f\n"
        "from api.m import g\n\n"
        "def test_ok():\n"
        "    assert f() == 1\n"
        "    assert g() == 2\n",
        encoding="utf-8",
    )

    run_backend_collection(
        repo_root=tmp_path,
        run_id="module2-test",
        pytest_target="tests",
        skip_pytest=False,
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
    coverage = metrics_payload["modules"]["backend"]["metrics"]["coverage"]
    assert coverage["status"] == "success"
    assert coverage["coverage_percent"] is not None

    # Chunk 2: Assert complexity and maintainability metrics are present and valid
    complexity = metrics_payload["modules"]["backend"]["metrics"]["complexity"]
    assert complexity["status"] == "success"
    assert complexity["radon_version"] != "not_available"
    cyclomatic = complexity["cyclomatic"]
    assert cyclomatic["mean"] is not None
    assert cyclomatic["max"] is not None
    assert cyclomatic["count"] > 0
    maintain = complexity["maintainability_index"]
    assert maintain["mean"] is not None
    assert maintain["min"] is not None
    assert maintain["count"] > 0

def test_complexity_unavailable_if_radon_missing(monkeypatch, tmp_path: Path) -> None:
    # Simulate radon import failure
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name.startswith("radon"):
            raise ImportError("radon not installed")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    from metrics.runner import backend_collector
    result = backend_collector.collect_complexity_and_maintainability(tmp_path, ["src"])  # src can be empty
    assert result["status"] == "not_available"
    assert "radon unavailable" in result["reason"]


def test_collect_pytest_coverage_prefers_repo_venv_python(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.write_text("", encoding="utf-8")
    output_dir = tmp_path / "metrics" / "output" / "backend" / "venv-check"

    captured: dict[str, object] = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd: list[str], **kwargs: object) -> _Proc:
        captured["cmd"] = cmd
        coverage_json = output_dir / "coverage.json"
        coverage_json.parent.mkdir(parents=True, exist_ok=True)
        coverage_json.write_text('{"totals": {"percent_covered": 50, "covered_lines": 1, "num_statements": 2, "missing_lines": 1}}', encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(backend_collector.subprocess, "run", _run)

    payload = backend_collector.collect_pytest_coverage(tmp_path, "tests/unit", output_dir)

    assert captured["cmd"][0] == str(venv_python)
    assert payload["python_executable"] == str(venv_python)
