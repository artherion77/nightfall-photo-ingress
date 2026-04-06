#!/usr/bin/env bash
# tests/unit/test_govctl_cli.sh — Smoke tests for dev/bin/govctl CLI.
#
# Tests are non-interactive; no live LXC environment is required.
# Stubs for `lxc` and test-target commands are injected via PATH.
#
# Usage:
#   bash tests/unit/test_govctl_cli.sh
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GOVCTL="$PROJECT_ROOT/dev/bin/govctl"

# ── Test harness ──────────────────────────────────────────────────────────────

PASS=0
FAIL=0
declare -a ERRORS=()
TEST_N=0

_pass() {
    ((PASS++)) || true
    ((TEST_N++)) || true
    printf 'ok %d - %s\n' "$TEST_N" "$1"
}

_fail() {
    ((FAIL++)) || true
    ((TEST_N++)) || true
    local desc="$1"
    local detail="${2:-}"
    printf 'not ok %d - %s\n' "$TEST_N" "$desc"
    ERRORS+=("FAIL [$TEST_N]: $desc${detail:+ — $detail}")
}

assert_exit() {
    local desc="$1" expected="$2" actual="$3"
    if [[ "$actual" -eq "$expected" ]]; then
        _pass "$desc"
    else
        _fail "$desc" "expected exit $expected, got $actual"
    fi
}

assert_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if printf '%s' "$haystack" | grep -qF -- "$needle"; then
        _pass "$desc"
    else
        _fail "$desc" "output does not contain: $(printf '%s' "$needle" | head -c 80)"
    fi
}

assert_json_valid() {
    local desc="$1" json="$2"
    if python3 -c "import json,sys; json.loads(sys.stdin.read())" <<< "$json" 2>/dev/null; then
        _pass "$desc"
    else
        _fail "$desc" "not valid JSON: $(printf '%s' "$json" | head -c 120)"
    fi
}


# ── Stub setup ────────────────────────────────────────────────────────────────

_TMP="$(mktemp -d)"
_STUB_BIN="$_TMP/stub-bin"
mkdir -p "$_STUB_BIN"

_cleanup() { rm -rf "$_TMP"; }
trap _cleanup EXIT

# lxc stub: all checks pass by default.
# For `lxc list` with LXC_STUB_EXIT=0, emit "RUNNING" so that
# _preflight_container_running (which checks stdout) passes.
cat > "$_STUB_BIN/lxc" << 'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "list" && "${LXC_STUB_EXIT:-0}" == "0" ]]; then
    echo "RUNNING"
fi
exit "${LXC_STUB_EXIT:-0}"
STUB
chmod +x "$_STUB_BIN/lxc"

export PATH="$_STUB_BIN:$PATH"

# Command stub for a target that exits 0.
cat > "$_STUB_BIN/govctl-test-pass" << 'STUB'
#!/usr/bin/env bash
echo "govctl-test-pass: ok"
exit 0
STUB
chmod +x "$_STUB_BIN/govctl-test-pass"

# Command stub for a target that exits 1.
cat > "$_STUB_BIN/govctl-test-fail" << 'STUB'
#!/usr/bin/env bash
echo "govctl-test-fail: error"
exit 1
STUB
chmod +x "$_STUB_BIN/govctl-test-fail"


# ── Test manifest (minimal, exercising every command's output) ────────────────

_MANIFEST_FILE="$_TMP/govctl-test-targets.yaml"
cat > "$_MANIFEST_FILE" << 'YAML'
version: 1
defaults:
  lock: false
  timeout_seconds: 60

targets:
  t.alpha:
    description: "First test target"
    command: "govctl-test-pass"
    preflight: []
    lock: false

  t.beta:
    description: "Second test target (depends on alpha)"
    command: "govctl-test-pass"
    requires: [t.alpha]
    preflight: []
    lock: false

  t.fail:
    description: "A failing target"
    command: "govctl-test-fail"
    preflight: []
    lock: false

  t.pf:
    description: "Target with preflight"
    command: "govctl-test-pass"
    preflight:
      - container-running:dev-photo-ingress
    lock: false

groups:
  grp.all:
    targets: [t.alpha, t.beta]
YAML

LOG_DIR="$_TMP/govctl-logs"
mkdir -p "$LOG_DIR"


# ── Helpers ───────────────────────────────────────────────────────────────────

run_govctl() {
    GOVCTL_MANIFEST="$_MANIFEST_FILE" \
    GOVCTL_DEV_CONTAINER="dev-photo-ingress" \
    bash "$GOVCTL" "$@"
}


# ── Test: help ────────────────────────────────────────────────────────────────

output="$(run_govctl help)"
rc=$?
assert_exit "help: exits 0" 0 "$rc"
assert_contains "help: mentions list command" "list" "$output"
assert_contains "help: mentions check command" "check" "$output"
assert_contains "help: mentions graph command" "graph" "$output"
assert_contains "help: mentions --dry-run" "--dry-run" "$output"


# ── Test: list (human) ────────────────────────────────────────────────────────

output="$(run_govctl list)"
rc=$?
assert_exit "list: exits 0" 0 "$rc"
assert_contains "list: shows t.alpha" "t.alpha" "$output"
assert_contains "list: shows t.beta" "t.beta" "$output"
assert_contains "list: shows groups section" "Groups:" "$output"
assert_contains "list: shows grp.all" "grp.all" "$output"


# ── Test: list --format json ──────────────────────────────────────────────────

output="$(run_govctl list --format json)"
rc=$?
assert_exit "list --format json: exits 0" 0 "$rc"
assert_json_valid "list --format json: emits valid JSON" "$output"
assert_contains "list --format json: includes targets key" '"targets"' "$output"
assert_contains "list --format json: includes groups key" '"groups"' "$output"
assert_contains "list --format json: includes t.alpha name" 't.alpha' "$output"


# ── Test: --dry-run ───────────────────────────────────────────────────────────

output="$(run_govctl t.alpha --dry-run --log-dir "$LOG_DIR")"
rc=$?
assert_exit "dry-run: exits 0" 0 "$rc"
assert_contains "dry-run: shows Dry run" "Dry run" "$output"
assert_contains "dry-run: lists t.alpha in plan" "t.alpha" "$output"

# No run directory should be created.
run_dir="$(ls -1dt "$LOG_DIR"/run-* 2>/dev/null | head -n 1)"
if [[ -z "$run_dir" ]]; then
    _pass "dry-run: no run directory created"
else
    _fail "dry-run: no run directory created" "found: $run_dir"
fi


# ── Test: run passing target ──────────────────────────────────────────────────

output="$(run_govctl t.alpha --log-dir "$LOG_DIR")"
rc=$?
assert_exit "run pass: exits 0" 0 "$rc"
assert_contains "run pass: shows target banner" "t.alpha" "$output"
assert_contains "run pass: shows PASSED" "PASSED" "$output"

run_dir="$(ls -1dt "$LOG_DIR"/run-* 2>/dev/null | head -n 1)"
if [[ -n "$run_dir" ]]; then
    _pass "run pass: run directory created"
    [[ -f "$run_dir/events.jsonl" ]] && _pass "run pass: events.jsonl present" \
        || _fail "run pass: events.jsonl present"
    [[ -f "$run_dir/summary.json" ]] && _pass "run pass: summary.json present" \
        || _fail "run pass: summary.json present"
else
    _fail "run pass: run directory created"
    _fail "run pass: events.jsonl present" "no run dir"
    _fail "run pass: summary.json present" "no run dir"
fi


# ── Test: run failing target ──────────────────────────────────────────────────

rc=0
run_govctl t.fail --log-dir "$LOG_DIR" > /dev/null 2>&1 || rc=$?
assert_exit "run fail: exits non-zero" 1 "$rc"


# ── Test: run group (resolves dependencies) ───────────────────────────────────

output="$(run_govctl grp.all --log-dir "$LOG_DIR")"
rc=$?
assert_exit "run group: exits 0" 0 "$rc"
# t.alpha must appear before t.beta (dependency resolution).
# Exclude the "Targets resolved" header line (which lists both names together)
# and look at the per-target execution banners only.
order_check="$(printf '%s\n' "$output" | grep -v 'Targets resolved')"
alpha_pos="$(printf '%s\n' "$order_check" | grep -n 't.alpha' | head -n1 | cut -d: -f1)"
beta_pos="$(printf '%s\n' "$order_check" | grep -n 't.beta' | head -n1 | cut -d: -f1)"
if [[ -n "$alpha_pos" && -n "$beta_pos" && "$alpha_pos" -lt "$beta_pos" ]]; then
    _pass "run group: t.alpha executes before t.beta"
else
    _fail "run group: t.alpha executes before t.beta" "alpha=$alpha_pos beta=$beta_pos"
fi


# ── Test: graph (human format) ────────────────────────────────────────────────

output="$(run_govctl graph t.beta)"
rc=$?
assert_exit "graph human: exits 0" 0 "$rc"
assert_contains "graph human: shows t.beta" "t.beta" "$output"
assert_contains "graph human: shows t.alpha dependency" "t.alpha" "$output"


# ── Test: graph --format dot ─────────────────────────────────────────────────

output="$(run_govctl graph t.beta --format dot)"
rc=$?
assert_exit "graph dot: exits 0" 0 "$rc"
assert_contains "graph dot: starts with digraph" "digraph" "$output"
assert_contains "graph dot: contains t.beta node" "t.beta" "$output"
assert_contains "graph dot: contains t.alpha -> t.beta edge" "t.alpha" "$output"
assert_contains "graph dot: contains closing brace" "}" "$output"


# ── Test: check (human format, all passing) ───────────────────────────────────

export LXC_STUB_EXIT=0
output="$(run_govctl check t.pf)"
rc=$?
assert_exit "check pass: exits 0 when preflight passes" 0 "$rc"
assert_contains "check pass: shows PASS" "PASS" "$output"
assert_contains "check pass: shows container-running check" "container-running" "$output"


# ── Test: check --format json ─────────────────────────────────────────────────

output="$(run_govctl check t.pf --format json)"
rc=$?
assert_exit "check --format json: exits 0 when passing" 0 "$rc"
assert_json_valid "check --format json: emits valid JSON" "$output"
assert_contains "check --format json: contains status field" '"status"' "$output"
assert_contains "check --format json: contains PASS status" '"PASS"' "$output"


# ── Test: check with failing preflight ───────────────────────────────────────

export LXC_STUB_EXIT=1
rc=0
output="$(run_govctl check t.pf)" || rc=$?
assert_exit "check fail: exits non-zero when preflight fails" 1 "$rc"
assert_contains "check fail: shows FAIL" "FAIL" "$output"


# ── Test: check --format json with failure ────────────────────────────────────

output="$(run_govctl check t.pf --format json)" || true
assert_json_valid "check fail json: emits valid JSON even on failure" "$output"
assert_contains "check fail json: contains FAIL status" '"FAIL"' "$output"
assert_contains "check fail json: contains reason field" '"reason"' "$output"

export LXC_STUB_EXIT=0


# ── Test: check with no-preflight target ─────────────────────────────────────

output="$(run_govctl check t.alpha)"
rc=$?
assert_exit "check no-preflight: exits 0" 0 "$rc"
assert_contains "check no-preflight: shows no preflights message" "no preflights" "$output"


# ── Test: unknown target exits non-zero ──────────────────────────────────────

rc=0
run_govctl no-such-target --log-dir "$LOG_DIR" > /dev/null 2>&1 || rc=$?
assert_exit "unknown target: exits non-zero" 1 "$rc"


# ── Test: no args shows help ──────────────────────────────────────────────────

output="$(run_govctl)"
rc=$?
assert_exit "no args: exits 0 (shows help)" 0 "$rc"
assert_contains "no args: help output included" "govctl" "$output"


# ── Summary ───────────────────────────────────────────────────────────────────

printf '1..%d\n' "$TEST_N"
echo ""
printf '# Results: %d passed, %d failed\n' "$PASS" "$FAIL"

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "# Failed tests:"
    for e in "${ERRORS[@]}"; do
        printf '#   %s\n' "$e"
    done
fi

[[ "$FAIL" -gt 0 ]] && exit 1
exit 0
