"""Unit tests for frontend metrics module (module 3): Sonar Cognitive Complexity."""

import json
from pathlib import Path

import pytest

from metrics.runner.frontend_collector import (
    collect_cognitive_complexity,
    collect_dependency_graph,
    collect_loc,
    SonarCognitiveComplexityCollector,
    run_frontend_collection,
)


class TestCognitiveComplexityCollector:
    """Test Sonar Cognitive Complexity scoring algorithm."""

    def test_flat_function_scores_zero(self, tmp_path: Path) -> None:
        """Flat function with no control flow should score 0."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function flat(x, y) {
    const result = x + y;
    return result;
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        assert file_result["function_count"] == 1
        assert file_result["functions"][0]["cognitive_complexity"] == 0

    def test_single_if_scores_one(self, tmp_path: Path) -> None:
        """Single if statement should score +1."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function withIf(x) {
    if (x > 0) {
        return x;
    }
    return 0;
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        assert file_result["function_count"] == 1
        assert file_result["functions"][0]["cognitive_complexity"] == 1

    def test_nested_conditionals(self, tmp_path: Path) -> None:
        """Nested if should apply nesting penalty."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function nested(x, y) {
    if (x > 0) {
        if (y > 0) {
            return x + y;
        }
    }
    return 0;
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        # Outer if: +1, inner if: +(1+1) = +2, total = 3
        assert file_result["functions"][0]["cognitive_complexity"] == 3

    def test_loop_scores_one(self, tmp_path: Path) -> None:
        """for/while loops should score +1."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function withLoop(arr) {
    for (let i = 0; i < arr.length; i++) {
        console.log(arr[i]);
    }
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        assert file_result["functions"][0]["cognitive_complexity"] == 1

    def test_switch_statement(self, tmp_path: Path) -> None:
        """Switch statement: +1 for switch, +1 for each case."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function switchTest(x) {
    switch (x) {
        case 1:
            return 'one';
        case 2:
            return 'two';
        default:
            return 'other';
    }
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        # switch: +1, case 1: +1, case 2: +1 = 3
        assert file_result["functions"][0]["cognitive_complexity"] == 3

    def test_try_catch(self, tmp_path: Path) -> None:
        """Try-catch: +1 for catch clause."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function tryCatch(x) {
    try {
        return riskyOp(x);
    } catch (e) {
        return null;
    }
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        assert file_result["functions"][0]["cognitive_complexity"] == 1

    def test_boolean_operators(self, tmp_path: Path) -> None:
        """Boolean operators: each && or || adds +1."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function boolOps(a, b, c) {
    if (a > 0 && b > 0 && c > 0) {
        return 'all positive';
    }
    return 'not all';
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        # if: +1, && count: 2 = 3 total
        assert file_result["functions"][0]["cognitive_complexity"] == 3

    def test_multiple_functions(self, tmp_path: Path) -> None:
        """File with multiple functions."""
        fixture = tmp_path / "test.js"
        fixture.write_text("""
function func1(x) {
    return x;
}

function func2(x) {
    if (x > 0) {
        return x;
    }
    return 0;
}
        """, encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        assert len(failures) == 0
        assert file_result["function_count"] == 2
        # func1: 0, func2: 1
        scores = [f["cognitive_complexity"] for f in file_result["functions"]]
        assert scores == [0, 1]
        assert file_result["file_total"] == 1
        assert file_result["file_mean"] == pytest.approx(0.5, abs=0.01)

    def test_parse_error_handling(self, tmp_path: Path) -> None:
        """Parse errors are reported as failures."""
        fixture = tmp_path / "test.js"
        fixture.write_text("function broken(x { return x; }", encoding="utf-8")
        
        collector = SonarCognitiveComplexityCollector()
        file_result, failures = collector.score_file(fixture)
        
        # Parse error should be captured
        assert len(failures) > 0
        assert failures[0]["reason"] == "parse_error"


class TestCollectCognitiveComplexity:
    """Test the high-level collect_cognitive_complexity function."""

    def test_no_files_returns_not_available(self, tmp_path: Path) -> None:
        """No eligible files should return not_available."""
        result = collect_cognitive_complexity(tmp_path, ["webui/nonexistent"])
        assert result["status"] == "not_available"
        assert result["source"] == "sonar_cognitive"
        assert result["file_count"] == 0

    def test_valid_project_scoring(self, tmp_path: Path) -> None:
        """Valid project should produce scores."""
        src_dir = tmp_path / "webui" / "src"
        src_dir.mkdir(parents=True)
        
        (src_dir / "simple.js").write_text("function f(x) { return x; }", encoding="utf-8")
        (src_dir / "complex.js").write_text("""
function c(x) {
    if (x > 0) {
        if (x > 10) {
            return 'large';
        }
        return 'small';
    }
    return 'zero';
}
        """, encoding="utf-8")
        
        result = collect_cognitive_complexity(tmp_path, ["webui/src"])
        
        assert result["status"] == "available"
        assert result["source"] == "sonar_cognitive"
        assert result["file_count"] == 2
        assert result["failed_file_count"] == 0
        assert result["mean"] is not None
        assert len(result["files"]) == 2

    def test_parser_info_included(self, tmp_path: Path) -> None:
        """Parser version info must be included."""
        src_dir = tmp_path / "webui" / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "test.js").write_text("function f(x) { return x; }", encoding="utf-8")
        
        result = collect_cognitive_complexity(tmp_path, ["webui/src"])
        
        assert "parser_info" in result
        assert result["parser_info"]["library"] == "tree-sitter"
        assert "library_version" in result["parser_info"]


class TestFrontendLOC:
    """Test LOC collection (should remain unchanged)."""

    def test_collect_loc_counts_files(self, tmp_path: Path) -> None:
        """LOC collection should count JavaScript/TypeScript/Svelte files."""
        src = tmp_path / "webui" / "src"
        src.mkdir(parents=True)
        
        (src / "a.ts").write_text("const x = 1;\n", encoding="utf-8")
        (src / "b.svelte").write_text("<script>let x=1;</script>\n", encoding="utf-8")
        (src / "c.js").write_text("console.log('x')\n", encoding="utf-8")
        
        payload = collect_loc(tmp_path, ["webui/src"])
        
        assert payload["status"] == "success"
        assert payload["files"] == 3
        assert payload["js_ts_files"] == 2
        assert payload["svelte_files"] == 1


class TestFrontendCollectionIntegration:
    """Integration tests for full frontend collection."""

    def test_run_frontend_collection_writes_artifacts(self, tmp_path: Path) -> None:
        """Full frontend collection should write metric artifacts."""
        src = tmp_path / "webui" / "src"
        src.mkdir(parents=True)
        
        (src / "main.ts").write_text("""
function main(x) {
    if (x > 0) {
        return x * 2;
    }
    return 0;
}
        """, encoding="utf-8")
        
        result = run_frontend_collection(
            repo_root=tmp_path.resolve(),
            run_id="test-run",
        )
        
        # Check result structure
        assert "manifest" in result
        assert "metrics" in result
        
        metrics = result["metrics"]
        assert "modules" in metrics
        assert "frontend" in metrics["modules"]
        
        frontend = metrics["modules"]["frontend"]
        assert "metrics" in frontend
        assert "cognitive_complexity" in frontend["metrics"]
        
        cc = frontend["metrics"]["cognitive_complexity"]
        assert cc["source"] == "sonar_cognitive"
        assert cc["status"] in ("available", "partial", "not_available")
        assert cc.get("version") == "1.0"
