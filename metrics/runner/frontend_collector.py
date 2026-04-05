
from __future__ import annotations

import argparse
import getpass
import importlib.metadata
import json
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metrics.runner.module1_init import _git_branch, _git_head_sha, _git_version
from metrics.runner.schema_contract import validate_manifest_payload, validate_metrics_payload


IMPORT_RE = re.compile(
    r"(?:import\s+(?:.+?)\s+from\s+|import\(\s*|require\(\s*)(['\"])(?P<module>[^'\"]+)\1"
)
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tool_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _iter_frontend_files(repo_root: Path, roots: list[str]) -> list[Path]:
    files: list[Path] = []
    suffixes = {".js", ".ts", ".svelte", ".jsx", ".tsx"}
    exclude_dirs = {"node_modules", "dist", ".svelte-kit", "build", "coverage"}
    
    for root in roots:
        start = repo_root / root
        if not start.exists():
            continue
        for file_path in start.rglob("*"):
            # Skip excluded directories
            if any(part in exclude_dirs for part in file_path.parts):
                continue
            # Skip .d.ts files
            if file_path.name.endswith(".d.ts"):
                continue
            if file_path.is_file() and file_path.suffix in suffixes:
                files.append(file_path)
    return sorted(files)


def collect_loc(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    files = _iter_frontend_files(repo_root, roots)
    totals = {
        "files": 0,
        "total_lines": 0,
        "total_code_lines": 0,
        "js_ts_files": 0,
        "svelte_files": 0,
    }
    per_file: dict[str, dict[str, int | str]] = {}

    for file_path in files:
        rel = str(file_path.relative_to(repo_root))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("//"))

        file_type = "svelte" if file_path.suffix == ".svelte" else "js_ts"
        if file_type == "svelte":
            totals["svelte_files"] += 1
        else:
            totals["js_ts_files"] += 1

        totals["files"] += 1
        totals["total_lines"] += total_lines
        totals["total_code_lines"] += code_lines
        per_file[rel] = {
            "type": file_type,
            "lines": total_lines,
            "code_lines": code_lines,
        }

    return {
        "status": "success",
        "roots": roots,
        **totals,
        "per_file": per_file,
    }


# ============================================================================
# SONAR COGNITIVE COMPLEXITY COLLECTOR (tree-sitter based)
# ============================================================================

class SonarCognitiveComplexityCollector:
    """AST-based Sonar Cognitive Complexity scorer for JS/TS/Svelte."""

    def __init__(self):
        try:
            from tree_sitter import Language, Parser
            from tree_sitter_javascript import language as js_language
            from tree_sitter_typescript import language_typescript as ts_language
        except ImportError as e:
            raise RuntimeError(f"tree-sitter not available: {e}") from e

        self.parser = Parser()
        self.languages = {
            ".js": Language(js_language()),
            ".jsx": Language(js_language()),
            ".ts": Language(ts_language()),
            ".tsx": Language(ts_language()),
            ".svelte": Language(js_language()),  # Svelte uses JS grammar
        }

    def _parser_info(self) -> dict[str, str]:
        """Return parser library versions."""
        def get_version(module_name: str) -> str:
            """Try to get version from importlib.metadata."""
            try:
                return importlib.metadata.version(module_name)
            except Exception:
                return "unknown"

        js_ver = get_version("tree-sitter-javascript")
        return {
            "library": "tree-sitter",
            "library_version": get_version("tree-sitter"),
            "grammar_js": js_ver,
            "grammar_ts": get_version("tree-sitter-typescript"),
            "grammar_svelte": js_ver,  # Svelte parsed with JS grammar (no tree-sitter-svelte installed)
        }

    def calculate_javascript_complexity(self, code: str) -> int:
        """Calculate complexity for a JavaScript code string.
        
        Parses the code and finds the first function declaration,
        then returns its cognitive complexity score.
        """
        try:
            # Parse the code
            code_bytes = code.encode("utf-8")
            lang = self.languages.get(".js")
            if not lang:
                return 0
            self.parser.language = lang
            tree = self.parser.parse(code_bytes)
            
            # Find the first function
            def find_function(node: Any) -> Any | None:
                if self._is_function_like(node):
                    return node
                for child in node.children:
                    result = find_function(child)
                    if result:
                        return result
                return None
            
            func_node = find_function(tree.root_node)
            if not func_node:
                return 0
            
            return self._score_function(func_node)
        except Exception:
            return 0

    def _parse_file(self, file_path: Path) -> Any | None:
        """Parse file and return AST root or None on parse error."""
        try:
            text = file_path.read_bytes()
            lang = self.languages.get(file_path.suffix)
            if not lang:
                return None
            self.parser.language = lang
            tree = self.parser.parse(text)
            if tree.root_node.has_error:
                return None
            return tree.root_node
        except Exception:
            return None

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file suffix."""
        if file_path.suffix == ".svelte":
            return "svelte"
        elif file_path.suffix in {".ts", ".tsx"}:
            return "typescript"
        else:
            return "javascript"

    def _is_function_like(self, node: Any) -> bool:
        """Check if node is a function-like declaration."""
        types = {
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
            "generator_function_declaration",
            "generator_function_expression",
        }
        return node.type in types

    def _extract_function_name(self, node: Any) -> str:
        """Extract display name from form function node."""
        # Try to find name child
        for child in node.children:
            if child.type == "identifier":
                try:
                    return child.text.decode("utf-8", errors="replace")
                except Exception:
                    pass
        
        # Try property name for methods
        if node.type == "method_definition":
            for child in node.children:
                if child.type in ("property_identifier", "identifier"):
                    try:
                        return child.text.decode("utf-8", errors="replace")
                    except Exception:
                        pass
        
        return f"<{node.type}>"

    def _count_boolean_operators(self, node: Any) -> int:
        """Count boolean operators in a condition."""
        count = 0
        # DFS to find operators in condition
        def traverse(n: Any) -> None:
            nonlocal count
            if n.type in ("&&", "||"):
                count += 1
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return count

    def _score_function(self, func_node: Any) -> int:
        """Compute Sonar cognitive complexity score for a function."""
        score = 0
        
        def traverse(node: Any, nesting_level: int) -> None:
            nonlocal score
            
            next_nesting = nesting_level
            
            # Handle else_clause without nesting penalty
            if node.type == "else_clause":
                score += 1  # +1 for else
                # Special case: else if should not increase nesting
                # Check if this else contains only an if statement (else if pattern)
                has_only_if = False
                for child in node.children:
                    if child.type == "if_statement":
                        has_only_if = True
                    elif child.type not in ("else", "if_statement"):
                        # Has other statements beside the if
                        has_only_if = False
                        break
                
                # If this is "else if", pass reduced nesting to avoid double-counting
                if has_only_if:
                    # Pass nesting_level - 2 so the if inside gets no nesting penalty
                    next_nesting = max(0, nesting_level - 2)
                else:
                    next_nesting = nesting_level + 1
            # Handle switch cases without nesting penalty
            elif node.type == "switch_case":
                score += 1  # +1 for case, no nesting penalty
                next_nesting = nesting_level + 1
            # Handle other flow control structures with nesting penalty
            elif node.type in ("if_statement", "for_statement", "for_in_statement", 
                              "while_statement", "do_statement", "switch_statement",
                              "catch_clause", "ternary_expression"):
                score += 1 + nesting_level
                
                # Count boolean operators in condition (if present)
                for child in node.children:
                    if child.type in ("parenthesized_expression", "conditions"):
                        bool_count = self._count_boolean_operators(child)
                        score += bool_count
                
                next_nesting = nesting_level + 1
            # Handle jump statements (break, continue, throw)
            elif node.type in {"break_statement", "continue_statement", "throw_statement"}:
                score += 1
                next_nesting = nesting_level
            
            # Check for recursion (function calling itself)
            if node.type == "call_expression":
                # Try to find callee name
                for child in node.children:
                    if child.type == "identifier":
                        try:
                            callee_name = child.text.decode("utf-8", errors="replace")
                            func_name = self._extract_function_name(func_node)
                            if func_name == callee_name:
                                score += 1
                        except Exception:
                            pass
            
            # Recurse to children
            for child in node.children:
                traverse(child, next_nesting)
        
        # Find body (varies by function type)
        body = None
        for child in func_node.children:
            if child.type in ("block", "statement_block"):
                body = child
                break
        
        if body:
            traverse(body, 0)
        
        return score

    def score_file(self, file_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Score all functions in a file. Returns (file_result, failures)."""
        failures: list[dict[str, Any]] = []
        
        root_node = self._parse_file(file_path)
        if not root_node:
            return (
                {
                    "path": str(file_path),
                    "language": self._detect_language(file_path),
                    "function_count": 0,
                    "functions": [],
                    "file_total": 0,
                    "file_mean": None,
                },
                [
                    {
                        "path": str(file_path),
                        "reason": "parse_error",
                        "detail": "Failed to parse file",
                        "remediation": "Fix syntax error or exclude file from analysis",
                    }
                ],
            )
        
        functions = []
        
        def extract_functions(node: Any) -> None:
            """Recursively extract function-like nodes."""
            if self._is_function_like(node):
                score = self._score_function(node)
                functions.append({
                    "name": self._extract_function_name(node),
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "cognitive_complexity": score,
                })
            
            for child in node.children:
                extract_functions(child)
        
        extract_functions(root_node)
        
        file_total = sum(f["cognitive_complexity"] for f in functions)
        file_mean = (file_total / len(functions)) if functions else None
        
        return (
            {
                "path": str(file_path),
                "language": self._detect_language(file_path),
                "function_count": len(functions),
                "functions": functions,
                "file_total": file_total,
                "file_mean": file_mean,
            },
            failures,
        )

    def score_project(self, files: list[Path]) -> dict[str, Any]:
        """Score all files in project."""
        analyzed_files = []
        all_failures = []
        
        for file_path in files:
            file_result, failures = self.score_file(file_path)
            analyzed_files.append(file_result)
            all_failures.extend(failures)
        
        # Compute project mean
        file_means = [f["file_mean"] for f in analyzed_files if f["file_mean"] is not None]
        project_mean = (sum(file_means) / len(file_means)) if file_means else None
        
        # Determine status
        if all_failures:
            if all_failures and len(analyzed_files) > len(all_failures):
                status = "partial"
            elif len(all_failures) == len(analyzed_files):
                status = "error"
            else:
                status = "partial"
        elif not analyzed_files:
            status = "not_available"
        else:
            status = "available"
        
        # Compute max across all file means
        project_max = max(file_means) if file_means else None

        return {
            "source": "sonar_cognitive",
            "status": status,
            "version": "1.0",
            "parser_info": self._parser_info(),
            "mean": project_mean,
            "max": project_max,
            "file_count": len(analyzed_files),
            "failed_file_count": len(all_failures),
            "files": analyzed_files,
            "failures": all_failures,
        }


def collect_cognitive_complexity(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    """Collect frontend cognitive complexity using Sonar Cognitive Complexity."""
    files = _iter_frontend_files(repo_root, roots)
    
    try:
        collector = SonarCognitiveComplexityCollector()
    except RuntimeError as e:
        return {
            "status": "error",
            "source": "sonar_cognitive",
            "reason": str(e),
            "detail": "tree-sitter not available",
            "remediation": "Install tree-sitter: pip install tree-sitter tree-sitter-javascript tree-sitter-typescript",
        }
    
    if not files:
        return {
            "status": "not_available",
            "source": "sonar_cognitive",
            "reason": "no eligible files found",
            "file_count": 0,
            "failed_file_count": 0,
            "files": [],
            "failures": [],
        }
    
    result = collector.score_project(files)

    # Build per_file dict (path → file_mean) for dashboard breakdown
    per_file: dict[str, float] = {}
    for f in result.get("files", []):
        if f.get("file_mean") is not None:
            raw_path = f["path"]
            try:
                rel = str(Path(raw_path).relative_to(repo_root))
            except ValueError:
                rel = raw_path
            per_file[rel] = round(f["file_mean"], 2)
    result["per_file"] = per_file

    # Add collection time
    result["collection_time_ms"] = 0  # Will be set by orchestrator
    
    return result


_FRONTEND_EXTS = (".ts", ".tsx", ".js", ".jsx", ".svelte")


def _resolve_local_import(from_path: str, to_module: str, node_set: set[str], repo_root: Path) -> str | None:
    """Resolve a relative JS/TS import specifier to its project node path, or None if unresolvable."""
    if not to_module.startswith("."):
        return None
    src_dir = (repo_root / from_path).parent
    resolved_base = (src_dir / to_module).resolve()
    for ext in _FRONTEND_EXTS:
        try:
            candidate = str(resolved_base.with_suffix(ext).relative_to(repo_root))
            if candidate in node_set:
                return candidate
        except ValueError:
            continue
    if resolved_base.suffix in set(_FRONTEND_EXTS):
        try:
            candidate = str(resolved_base.relative_to(repo_root))
            if candidate in node_set:
                return candidate
        except ValueError:
            pass
    return None


def _detect_cycles(adj: dict[str, list[str]]) -> set[str]:
    """Return the set of node keys that participate in any cycle (DFS with gray-set tracking)."""
    in_cycle: set[str] = set()
    visited: set[str] = set()
    gray: set[str] = set()

    def _dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        gray.add(node)
        path.append(node)
        for neighbor in adj.get(node, []):
            if neighbor not in adj:
                continue
            if neighbor in gray:
                idx = path.index(neighbor)
                for cycle_node in path[idx:]:
                    in_cycle.add(cycle_node)
            elif neighbor not in visited:
                _dfs(neighbor, path)
        path.pop()
        gray.discard(node)

    for start_node in list(adj.keys()):
        if start_node not in visited:
            _dfs(start_node, [])
    return in_cycle


def collect_dependency_graph(repo_root: Path, roots: list[str]) -> dict[str, Any]:
    all_files = _iter_frontend_files(repo_root, roots)
    nodes: list[str] = [str(f.relative_to(repo_root)) for f in all_files]
    node_set = set(nodes)

    edges: list[dict[str, str]] = []
    for file_path in all_files:
        rel = str(file_path.relative_to(repo_root))
        text = file_path.read_text(encoding="utf-8", errors="replace")
        modules = {match.group("module") for match in IMPORT_RE.finditer(text)}
        for module in sorted(modules):
            edges.append({"from": rel, "to": module})

    fan_out: dict[str, int] = {n: 0 for n in nodes}
    fan_in: dict[str, int] = {n: 0 for n in nodes}
    local_adj: dict[str, list[str]] = {n: [] for n in nodes}
    for edge in edges:
        fan_out[edge["from"]] = fan_out.get(edge["from"], 0) + 1
        resolved = _resolve_local_import(edge["from"], edge["to"], node_set, repo_root)
        if resolved:
            fan_in[resolved] = fan_in.get(resolved, 0) + 1
            local_adj[edge["from"]].append(resolved)

    in_cycle = _detect_cycles(local_adj)

    node_details = sorted(
        [
            {
                "path": path,
                "fan_in": fan_in.get(path, 0),
                "fan_out": fan_out.get(path, 0),
                "kind": "local",
                "in_cycle": path in in_cycle,
            }
            for path in nodes
        ],
        key=lambda d: d["path"],
    )

    return {
        "status": "success",
        "nodes": sorted(nodes),
        "edges": edges,
        "node_details": node_details,
    }


def frontend_test_coverage_status(reason: str = "deferred_until_vitest_playwright_maturity") -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": reason,
    }


def _determine_collection_status(frontend: dict[str, Any]) -> str:
    statuses = {
        frontend.get("loc", {}).get("status"),
        frontend.get("cognitive_complexity", {}).get("status"),
        frontend.get("dependency_graph", {}).get("status"),
        frontend.get("test_coverage", {}).get("status"),
    }
    if "failed" in statuses:
        return "failed"
    if "not_available" in statuses:
        return "partial"
    return "success"


def _build_manifest(
    repo_root: Path,
    run_id: str,
    branch: str,
    commit_sha: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    frontend_status: str,
    warnings: list[str],
    failures: list[str],
) -> dict[str, Any]:
    history_base = f"artifacts/metrics/history/{run_id}"
    exit_state = "success" if frontend_status in {"success", "partial", "not_available"} else "failed"
    return {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "repository_path": str(repo_root),
            "branch": branch,
            "commit_sha": commit_sha,
        },
        "trigger": {
            "mode": "bootstrap",
            "polled_at": started_at,
        },
        "execution": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": round(duration_seconds, 4),
            "hostname": socket.gethostname(),
            "executor_identity": getpass.getuser(),
            "exit_state": exit_state,
        },
        "tools": {
            "python": sys.version.split()[0],
            "git": _git_version(repo_root),
            "eslint": _tool_version("eslint") or "not_available",
        },
        "steps": [
            {
                "name": "module3_frontend_collect",
                "status": "success" if exit_state == "success" else "failed",
                "exit_code": 0 if exit_state == "success" else 1,
                "duration_seconds": round(duration_seconds, 4),
            }
        ],
        "artifacts": {
            "latest_manifest": "artifacts/metrics/latest/manifest.json",
            "latest_metrics": "artifacts/metrics/latest/metrics.json",
            "history_manifest": f"{history_base}/manifest.json",
            "history_metrics": f"{history_base}/metrics.json",
        },
        "publication": {
            "status": "not_published",
            "metrics_branch": "metrics",
            "dashboard_relative_path": "/dashboard/",
            "published_at": None,
        },
        "warnings": warnings,
        "failures": failures,
    }


def run_frontend_collection(repo_root: Path, run_id: str) -> dict[str, Any]:
    started = time.time()
    started_at = utc_now_iso()
    branch = _git_branch(repo_root)
    commit_sha = _git_head_sha(repo_root)

    roots = ["webui/src", "webui/tests"]
    frontend_output_dir = repo_root / "metrics" / "output" / "frontend" / run_id
    frontend_output_dir.mkdir(parents=True, exist_ok=True)

    frontend_metrics = {
        "loc": collect_loc(repo_root, roots),
        "cognitive_complexity": collect_cognitive_complexity(repo_root, roots),
        "dependency_graph": collect_dependency_graph(repo_root, roots),
        "test_coverage": frontend_test_coverage_status(),
    }
    frontend_status = _determine_collection_status(frontend_metrics)

    warnings: list[str] = []
    failures: list[str] = []
    for key in ("cognitive_complexity", "dependency_graph", "test_coverage"):
        status = frontend_metrics.get(key, {}).get("status")
        if status == "not_available":
            warnings.append(f"frontend.{key} not available")
        elif status == "failed":
            failures.append(f"frontend.{key} failed")

    latest_metrics_path = repo_root / "artifacts" / "metrics" / "latest" / "metrics.json"
    backend = {
        "status": "not_available",
        "metrics": {},
    }
    if latest_metrics_path.exists():
        try:
            existing = json.loads(latest_metrics_path.read_text(encoding="utf-8"))
            backend = existing.get("modules", {}).get("backend", backend)
        except Exception:
            backend = {
                "status": "not_available",
                "metrics": {},
            }

    module_statuses = {backend.get("status"), frontend_status}
    if "failed" in module_statuses:
        collection_status = "failed"
    elif "partial" in module_statuses or "not_available" in module_statuses:
        collection_status = "partial"
    else:
        collection_status = "success"

    metrics_payload = {
        "schema_version": 1,
        "run_id": run_id,
        "source": {
            "commit_sha": commit_sha,
            "branch": branch,
        },
        "collection_status": collection_status,
        "modules": {
            "backend": backend,
            "frontend": {
                "status": frontend_status,
                "metrics": frontend_metrics,
            },
        },
        "delta": {},
    }

    finished_at = utc_now_iso()
    duration = time.time() - started
    manifest_payload = _build_manifest(
        repo_root=repo_root,
        run_id=run_id,
        branch=branch,
        commit_sha=commit_sha,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        frontend_status=frontend_status,
        warnings=warnings,
        failures=failures,
    )

    validate_metrics_payload(metrics_payload)
    validate_manifest_payload(manifest_payload)

    history_dir = repo_root / "artifacts" / "metrics" / "history" / run_id
    history_dir.mkdir(parents=True, exist_ok=True)

    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "metrics.json", metrics_payload)
    _write_json(repo_root / "artifacts" / "metrics" / "latest" / "manifest.json", manifest_payload)
    _write_json(history_dir / "metrics.json", metrics_payload)
    _write_json(history_dir / "manifest.json", manifest_payload)
    _write_json(frontend_output_dir / "frontend_metrics.json", frontend_metrics)

    return {
        "manifest": manifest_payload,
        "metrics": metrics_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect frontend metrics (LOC/complexity/dependency graph)")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--run-id", default="module3-bootstrap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_frontend_collection(
        repo_root=Path(args.repo_root).resolve(),
        run_id=args.run_id,
    )


if __name__ == "__main__":
    main()
