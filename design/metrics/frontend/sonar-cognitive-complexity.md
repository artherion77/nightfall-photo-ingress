# Sonar Cognitive Complexity: Algorithm and Methodology

Status: Design
Date: 2026-04-05
Owner: Systems Engineering
Purpose: Define deterministic, AST-based cognitive complexity scoring for frontend code

## 1. Methodology Reference

### 1.1 Sonar Cognitive Complexity overview

This design adopts Sonar Cognitive Complexity (G. Ann Campbell, SonarSource, 2017) as the basis for measuring frontend code understandability.

Core principles:

- Score increases for control-flow structures that break linear code reading.
- Nesting depth is directly represented as an additional penalty, since nested logic increases cognitive load.
- Readable shorthand forms are not over-penalized when they reduce overall mental effort.
- Function-level scoring reflects maintainability and understandability, not path-count mathematics.

### 1.2 Why this measures understandability, not size

- The metric does not increase for lines of code alone.
- Focus is on breaks in linear reading flow: branches, loops, exception handlers, conditionals, jumps.
- Nesting depth directly correlates with mental effort required to follow frontend logic.
- Two files with identical line counts can have very different cognitive complexity depending on nesting and control-flow density.

### 1.3 Why prefer this over cyclomatic complexity for frontend

- Cyclomatic complexity measures path count; useful for some contexts, but does not align well with human comprehension burden.
- Frontend code frequently contains nested rendering conditions, event handlers, and UI-state transitions where readability cost matters more than mathematical path count.
- Cognitive complexity better captures perceived maintainability when reading modern JS/TS/Svelte patterns.
- Sonar methodology is documented, recognized across industry, and designed for cross-project comparison.

## 2. Scope Definition

### 2.1 In scope

**Languages:** JavaScript, TypeScript, Svelte.

**Collection root:** `webui/` directory.

**Score units:**
- Per-function cognitive complexity score
- Per-file aggregate (mean and total)
- Run-level aggregate mean across all analyzed files

**Provenance:** Output includes explicit source tagging (`source: "sonar_cognitive"`) for audit and comparison.

### 2.2 File eligibility

**Default include set under `webui/`:**
- `**/*.js`
- `**/*.jsx`
- `**/*.ts`
- `**/*.tsx`
- `**/*.svelte`

**Default exclude set:**
- `**/node_modules/**`
- `**/dist/**`
- `**/.svelte-kit/**`
- `**/build/**`
- `**/coverage/**`
- `**/*.d.ts`
- Generated artifacts and vendored code

### 2.3 Explicit non-goals

- No linting rule integration or ESLint plugin dependence.
- No attempt to perfectly emulate every edge case in Sonar's language-specific implementations; this design uses a stable, documented subset of Sonar semantics suitable for JS/TS/Svelte ASTs.
- No measurement of template or markup complexity outside of executable script logic.

## 3. Algorithm Specification

### 3.1 Determinism contract

The collector must produce deterministic scores for identical inputs:

- Same parser version and same source bytes must always produce identical scores.
- AST traversal order must be stable (pre-order by AST child list order).
- Parse failures must produce explicit failure metadata; no silent fallback.
- Aggregation formulas are fixed and documented; no dynamic weighting.

### 3.2 Scoring rules

#### Base increments

Add +1 for each control-flow structure that breaks sequential flow:

- `if`, `else if`
- Loop constructs: `for`, `for..of`, `for..in`, `while`, `do..while`
- `catch` clauses
- Conditional (ternary) expressions `? :`
- `switch` statements with branching cases (see switch rule below)

#### Nesting penalty

For each flow-breaking structure, add its current nesting level to the score increment:

- Increment contribution = `1 + nesting_level`
- Top-level structure within a function has `nesting_level = 0`
- Structure nested inside another has `nesting_level = 1`; one level deeper has `nesting_level = 2`, etc.

#### Flow-breaking jumps

Add +1 for control-flow jumps within a function body:

- `break` (excluding trivial switch case fall-through where no effective branch jump is represented)
- `continue`
- `throw`
- Early `return` in guarded branches (return at the final linear tail of a function is not additionally penalized)

#### Boolean operator handling

Within decision conditions (`if`, loop guards, ternary guards):

- Count logical operator chains that increase reasoning complexity.
- For each additional logical operator in a contiguous chain (`&&` or `||`), add +1.
- Example: `a && b || c && d` counts as: condition base (+1) plus operators (+3 for `&&`, `||`, `&&`) = +4 total.
- AST parentheses are honored; operator grouping follows AST structure.

#### Switch handling

- `switch` statement contributes complexity for its branching context.
- Each non-`default` case contributes +1 (plus applicable nesting penalty).
- `default` case contributes 0 unless it contains nested control-flow structures (scored normally).

#### Recursion handling

- If a function directly calls itself by name, add +1 once per function.
- Mutual recursion (A calls B calls A) is out of scope for initial implementation.

### 3.3 Function boundaries

Scores are computed per function-like scope:

**In scope:**
- Function declarations
- Function expressions
- Arrow functions
- Class methods (instance and static)
- Svelte script-level functions and method-like constructs

**Nesting of functions:**
- Parent function score does not include child function complexity.
- Child function is scored independently and included in file-level aggregates.

### 3.4 Svelte-specific handling

- Parse `.svelte` files into AST segments covering script content.
- Complexity is computed from executable script logic only.
- Template markup alone contributes 0 complexity unless mapped to generated control-flow in the AST.

### 3.5 Pseudocode

```text
function score_project(files):
    analyzed_files = []
    failures = []

    for file in stable_sorted(files):
        parse_result = parse_file_to_ast(file)
        if parse_result.error:
            failures.append({
              "path": file,
              "reason": parse_result.error.code,
              "detail": parse_result.error.message
            })
            continue

        function_nodes = extract_function_like_nodes(parse_result.ast)
        file_function_scores = []

        for fn in function_nodes:
            score = score_function(fn)
            file_function_scores.append({
                "name": function_display_name(fn),
                "start_line": fn.start_line,
                "end_line": fn.end_line,
                "cognitive_complexity": score,
            })

        file_total = sum(s.cognitive_complexity for s in file_function_scores)
        file_mean = arithmetic_mean(file_function_scores) or null

        analyzed_files.append({
            "path": normalize_path(file),
            "language": detect_language(file),
            "function_count": len(file_function_scores),
            "function_scores": file_function_scores,
            "file_total": file_total,
            "file_mean": file_mean,
        })

    project_mean = arithmetic_mean(
        [f.file_mean for f in analyzed_files if f.function_count > 0]
    ) or null

    return {
        "source": "sonar_cognitive",
        "status": infer_status(analyzed_files, failures),
        "files": analyzed_files,
        "summary": {
            "file_count": len(analyzed_files),
            "failed_file_count": len(failures),
            "mean": project_mean,
        },
        "failures": failures,
    }


function score_function(fn_node):
    return traverse(fn_node.body, nesting_level = 0)


function traverse(node, nesting_level):
    score = 0

    if is_flow_breaking_structure(node):
        score += 1 + nesting_level
        score += count_boolean_operators_in_condition(node)
        next_nesting = nesting_level + 1
    else:
        next_nesting = nesting_level

    if is_flow_breaking_jump(node):
        score += flow_jump_score(node)

    if is_direct_recursion_call(node):
        score += 1

    for child in ordered_children(node):
        score += traverse(child, next_nesting_for_child(node, child))

    return score
```

### 3.6 Aggregation rules

- **Per-file mean:** Arithmetic mean of per-function scores in that file (null if file has no functions).
- **Project mean:** Arithmetic mean of file means for files with at least one function.
- **Empty files:** Reported in output but excluded from project mean denominator.

## 4. Technology Choice

### 4.1 Evaluated approaches

#### Option A: tree-sitter in Python

**Strengths:**
- Direct integration with existing Python metrics pipeline.
- Deterministic parser versions pinned in Python environment.
- No runtime dependency on project-local Node.js plugins.
- Access to mature JS/TS grammar packages.
- Single-language runtime improves testability.

**Risks:**
- Svelte parsing strategy requires validation.
- AST normalization layer required across JS/TS/Svelte.

#### Option B: Node.js subprocess with parser

**Strengths:**
- Access to JS ecosystem parsers and Svelte compiler tooling.

**Risks:**
- Adds subprocess orchestration complexity.
- Higher brittleness from Node dependency version drift.
- More failure surfaces in event loop/IPC.

### 4.2 Selected approach: tree-sitter in Python

**Rationale:**
- Best fit for existing collector architecture and Python test harness.
- Deterministic version pinning via environment management.
- Reduces dependency churn compared to Node subprocess model.
- Consolidates scoring logic in one language/runtime with backend collectors.

## 5. Parser Version Reporting

### 5.1 Version contract

Every collection run must include explicit parser version metadata:

```json
{
  "modules": {
    "frontend": {
      "metrics": {
        "cognitive_complexity": {
          "source": "sonar_cognitive",
          "parser_info": {
            "library": "tree-sitter",
            "library_version": "0.20.8",
            "grammar_js": "0.21.0",
            "grammar_ts": "0.20.2",
            "grammar_svelte": "0.13.10"
          }
        }
      }
    }
  }
}
```

### 5.2 historical comparability

When parser versions change:

- Scores are comparable across runs only when parser versions are identical.
- Dashboard must include parser version info for historical context.
- Breaking changes in a grammar version should trigger a baseline reset (clear historical comparisons).
- Minor patches (e.g., 0.20.7 → 0.20.8) are treated as compatible; run-to-run consistency is expected.

## 6. Test Fixture Strategy

### 6.1 Regression locking

Test suite includes fixtures locked to known outputs via snapshot testing:

- Representative JS/TS/Svelte code samples covering all scoring rules.
- Each fixture has a locked baseline score that fails if algorithm changes.
- Fixtures cover edge cases: empty functions, deeply nested control, boolean chains, recursion, Svelte templates.

### 6.2 Fixture organization

```
tests/unit/fixtures/cognitive_complexity/
  ├── flat_function.js
  ├── nested_conditionals.ts
  ├── loop_with_catches.js
  ├── boolean_chains.ts
  ├── svelte_script_logic.svelte
  ├── deeply_nested.js
  └── recursion_example.ts

tests/unit/snapshots/
  └── cognitive_complexity_scores.snap
```

### 6.3 Determinism validation

- Build-time: Verify all fixture inputs hash reproducibly.
- Test-time: Run fixtures through scorer twice; assert identical output.
- CI: Lock snapshot hashes to prevent score drift without review.

## 7. Performance Expectations

### 7.1 Soft targets

- AST parsing: < 100ms per file for typical ~500 LOC file.
- Traversal: < 10ms per file.
- Full project (42 files): < 10 seconds wall-clock.

### 7.2 Optimization strategy

- Parse files in parallel where feasible.
- Cache AST if traversal must run multiple times in same run.
- Avoid regex escapes in favor of AST node traversal.

### 7.3 Monitoring

- Collector emits wall-clock duration in metadata.
- Dashboard includes parser/collection time for transparency.
- If collection exceeds 30 seconds, emit warning to logs (possible timeout risk).

## 8. Determinism Contract Summary

**Invariant:** For a given source tree at a given commit with given parser versions:

$$\text{CollectorInvocation}_1 = \text{CollectorInvocation}_2 = \ldots = \text{CollectorInvocation}_n$$

This invariant ensures historical scores remain valid and comparable across runs.
