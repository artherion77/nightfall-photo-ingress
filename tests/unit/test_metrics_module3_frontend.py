from pathlib import Path
def test_collect_cognitive_complexity_heuristic_and_not_available(tmp_path: Path, monkeypatch) -> None:
    # No ESLint: fallback to heuristic
    from metrics.runner import frontend_collector
    (tmp_path / "webui" / "src").mkdir(parents=True)
    (tmp_path / "webui" / "src" / "a.ts").write_text("if (x) { y(); }", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = frontend_collector.collect_cognitive_complexity(tmp_path, ["webui/src"])
    assert result["status"] == "success"
    assert result["source"] == "heuristic_fallback"
    assert result["count"] == 1
    assert "a.ts" in next(iter(result["per_file"]))

    # No files: not_available
    result2 = frontend_collector.collect_cognitive_complexity(tmp_path, ["webui/empty"])
    assert result2["status"] == "not_available"
    assert result2["source"] == "heuristic_fallback"

def test_collect_cognitive_complexity_eslint_not_available(monkeypatch, tmp_path: Path) -> None:
    # Simulate ESLint present but fails
    from metrics.runner import frontend_collector
    (tmp_path / "webui" / "src").mkdir(parents=True)
    (tmp_path / "webui" / "src" / "b.ts").write_text("if (y) { z(); }", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/eslint")
    class DummyProc:
        returncode = 2
        stdout = ""
        stderr = "ESLint error"
    monkeypatch.setattr(frontend_collector.subprocess, "run", lambda *a, **k: DummyProc())
    result = frontend_collector.collect_cognitive_complexity(tmp_path, ["webui/src"])
    assert result["status"] == "not_available"
    assert result["source"] == "eslint_rules"

import json
from pathlib import Path

from metrics.runner.frontend_collector import collect_dependency_graph, collect_loc, run_frontend_collection


def test_collect_frontend_loc_counts_js_ts_svelte(tmp_path: Path) -> None:
    (tmp_path / "webui" / "src").mkdir(parents=True)
    (tmp_path / "webui" / "src" / "a.ts").write_text("const x = 1;\n", encoding="utf-8")
    (tmp_path / "webui" / "src" / "b.svelte").write_text("<script>let x=1;</script>\n", encoding="utf-8")
    (tmp_path / "webui" / "tests").mkdir(parents=True)
    (tmp_path / "webui" / "tests" / "c.js").write_text("console.log('x')\n", encoding="utf-8")

    payload = collect_loc(tmp_path, ["webui/src", "webui/tests"])
    assert payload["status"] == "success"
    assert payload["files"] == 3
    assert payload["js_ts_files"] == 2
    assert payload["svelte_files"] == 1


def test_collect_frontend_dependency_graph_extracts_imports(tmp_path: Path) -> None:
    (tmp_path / "webui" / "src").mkdir(parents=True)
    (tmp_path / "webui" / "src" / "imports.ts").write_text(
        "import x from 'foo';\nconst y = require('bar');\n",
        encoding="utf-8",
    )
    payload = collect_dependency_graph(tmp_path, ["webui/src"])
    assert payload["status"] == "success"
    assert {edge["to"] for edge in payload["edges"]} == {"foo", "bar"}


def test_run_frontend_collection_writes_latest_and_history_artifacts(tmp_path: Path) -> None:
    (tmp_path / "webui" / "src").mkdir(parents=True)
    (tmp_path / "webui" / "src" / "x.ts").write_text("if (true) { console.log('x'); }\n", encoding="utf-8")
    (tmp_path / "webui" / "tests").mkdir(parents=True)
    (tmp_path / "webui" / "tests" / "x.test.ts").write_text("export {};\n", encoding="utf-8")

    # Seed a backend slot to verify frontend collector preserves it.
    (tmp_path / "artifacts" / "metrics" / "latest").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "seed",
                "source": {"commit_sha": "0" * 40, "branch": "main"},
                "collection_status": "partial",
                "modules": {
                    "backend": {"status": "success", "metrics": {"loc": {"status": "success"}}},
                    "frontend": {"status": "not_available", "metrics": {}},
                },
                "delta": {},
            }
        ),
        encoding="utf-8",
    )

    run_frontend_collection(repo_root=tmp_path, run_id="module3-test")

    latest_manifest = tmp_path / "artifacts" / "metrics" / "latest" / "manifest.json"
    latest_metrics = tmp_path / "artifacts" / "metrics" / "latest" / "metrics.json"
    history_manifest = tmp_path / "artifacts" / "metrics" / "history" / "module3-test" / "manifest.json"
    history_metrics = tmp_path / "artifacts" / "metrics" / "history" / "module3-test" / "metrics.json"
    frontend_output = tmp_path / "metrics" / "output" / "frontend" / "module3-test" / "frontend_metrics.json"

    assert latest_manifest.exists()
    assert latest_metrics.exists()
    assert history_manifest.exists()
    assert history_metrics.exists()
    assert frontend_output.exists()

    metrics_payload = json.loads(latest_metrics.read_text(encoding="utf-8"))
    assert metrics_payload["schema_version"] == 1
    assert metrics_payload["run_id"] == "module3-test"
    assert metrics_payload["modules"]["backend"]["status"] == "success"
    assert metrics_payload["modules"]["frontend"]["status"] in {"success", "partial"}
    assert metrics_payload["modules"]["frontend"]["metrics"]["test_coverage"]["status"] == "not_available"
