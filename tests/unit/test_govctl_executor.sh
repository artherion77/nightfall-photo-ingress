#!/usr/bin/env bash
# tests/unit/test_govctl_executor.sh — Integration-style unit tests for
# dev/lib/govctl-executor.sh.
#
# Tests use a real (minimal) manifest JSON and resolved-targets file, with
# stubbed commands injected via a temp PATH.  No live LXC environment is
# required.
#
# Usage:
#   bash tests/unit/test_govctl_executor.sh
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

EXECUTOR_LIB="$PROJECT_ROOT/dev/lib/govctl-executor.sh"
PREFLIGHTS_LIB="$PROJECT_ROOT/dev/lib/govctl-preflights.sh"

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
    if printf '%s' "$haystack" | grep -qF "$needle"; then
        _pass "$desc"
    else
        _fail "$desc" "does not contain: $(printf '%s' "$needle" | head -c 80)"
    fi
}

assert_file_contains() {
    local desc="$1" needle="$2" file="$3"
    if grep -qF "$needle" "$file" 2>/dev/null; then
        _pass "$desc"
    else
        _fail "$desc" "file '$file' does not contain: $needle"
    fi
}

assert_file_exists() {
    local desc="$1" file="$2"
    if [[ -f "$file" ]]; then
        _pass "$desc"
    else
        _fail "$desc" "file not found: $file"
    fi
}


# ── Workspace setup ───────────────────────────────────────────────────────────

_TMP="$(mktemp -d)"
_cleanup() { rm -rf "$_TMP"; }
trap _cleanup EXIT

# Stub command bin — injected at the front of PATH.
_STUB_BIN="$_TMP/stub-bin"
mkdir -p "$_STUB_BIN"

# lxc stub for preflights (all checks pass by default).
cat > "$_STUB_BIN/lxc" << 'STUB'
#!/usr/bin/env bash
exit "${LXC_STUB_EXIT:-0}"
STUB
chmod +x "$_STUB_BIN/lxc"

export PATH="$_STUB_BIN:$PATH"

# Source the libraries.
GOVCTL_PREFLIGHTS_PROJECT_ROOT="$_TMP/project"
GOVCTL_DEV_CONTAINER="test-container"
source "$PREFLIGHTS_LIB"

GOVCTL_EXEC_PROJECT_ROOT="$_TMP/project"
source "$EXECUTOR_LIB"


# ── Manifest builder ──────────────────────────────────────────────────────────

# Writes a minimal normalised manifest JSON to a temp file and prints its path.
# Arguments: one target definition per call — see usage in tests below.
_write_manifest() {
    # Usage: _write_manifest <json-targets-block>
    local targets_block="$1"
    local out="$_TMP/manifest-$RANDOM.json"
    python3 - "$out" "$targets_block" << 'PY'
import json, sys
out_path = sys.argv[1]
targets_input = sys.argv[2]  # already a JSON object string

manifest = {
    "version": 1,
    "defaults": {"lock": False, "timeout_seconds": 300},
    "targets": json.loads(targets_input),
    "groups": {},
    "groups_expanded": {}
}
open(out_path, "w").write(json.dumps(manifest))
PY
    printf '%s' "$out"
}

# Writes a resolved-targets file (one name per line) and prints its path.
_write_resolved() {
    local out="$_TMP/resolved-$RANDOM.txt"
    printf '%s\n' "$@" > "$out"
    printf '%s' "$out"
}

# Make a fake project root with a stub command that exits with a given code.
_make_stub_cmd() {
    local name="$1"   # e.g. "pass-cmd" or "fail-cmd"
    local exit_code="${2:-0}"
    local output_msg="${3:-}"
    mkdir -p "$_TMP/project"
    local cmd_path="$_STUB_BIN/$name"
    printf '#!/usr/bin/env bash\n%s\nexit %d\n' \
        "${output_msg:+echo \"$output_msg\"}" \
        "$exit_code" \
        > "$cmd_path"
    chmod +x "$cmd_path"
}

# Log dir for a test — unique per test.
_log_dir() {
    local d="$_TMP/logs-$RANDOM"
    mkdir -p "$d"
    printf '%s' "$d"
}

# Find the most recent run dir under a log dir.
_latest_run_dir() {
    ls -1dt "$1"/run-* 2>/dev/null | head -n 1
}


# ── Test: dry-run mode ────────────────────────────────────────────────────────

manifest="$(_write_manifest '{"alpha":{"command":"echo alpha","preflight":[],"lock":false,"timeout_seconds":30}}')"
resolved="$(_write_resolved "alpha")"
log_dir="$(_log_dir)"

output="$(govctl_execute "$manifest" "$resolved" "alpha" "$log_dir" 0 1)"
rc=$?
assert_exit "dry-run: exits 0" 0 "$rc"
assert_contains "dry-run: lists target" "alpha" "$output"
assert_contains "dry-run: shows dry run message" "Dry run" "$output"

# No run directory should have been created in dry-run mode.
run_dir="$(_latest_run_dir "$log_dir")"
if [[ -z "$run_dir" ]]; then
    _pass "dry-run: no run directory created"
else
    _fail "dry-run: no run directory created" "found: $run_dir"
fi


# ── Test: single passing target ───────────────────────────────────────────────

_make_stub_cmd "pass-cmd" 0 "hello from pass-cmd"

manifest="$(_write_manifest '{"t.pass":{"command":"pass-cmd","preflight":[],"lock":false,"timeout_seconds":30}}')"
resolved="$(_write_resolved "t.pass")"
log_dir="$(_log_dir)"

govctl_execute "$manifest" "$resolved" "t.pass" "$log_dir" 0 0
rc=$?
assert_exit "passing target: exits 0" 0 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_exists "passing target: events.jsonl created" "$run_dir/events.jsonl"
assert_file_exists "passing target: summary.json created" "$run_dir/summary.json"

assert_file_contains "passing target: events.jsonl has run_started" "run_started" "$run_dir/events.jsonl"
assert_file_contains "passing target: events.jsonl has target_started" "target_started" "$run_dir/events.jsonl"
assert_file_contains "passing target: events.jsonl has target_passed" "target_passed" "$run_dir/events.jsonl"
assert_file_contains "passing target: events.jsonl has run_finished" "run_finished" "$run_dir/events.jsonl"

# Log file for the target.
assert_file_exists "passing target: per-target log created" "$run_dir/t.pass.log"

# summary.json correctness.
summary="$(cat "$run_dir/summary.json")"
assert_contains "passing target: summary passed count = 1" '"passed": 1' "$summary"
assert_contains "passing target: summary failed count = 0" '"failed": 0' "$summary"
assert_contains "passing target: summary status = passed" '"status": "passed"' "$summary"


# ── Test: single failing target ───────────────────────────────────────────────

_make_stub_cmd "fail-cmd" 1 "something went wrong"

manifest="$(_write_manifest '{"t.fail":{"command":"fail-cmd","preflight":[],"lock":false,"timeout_seconds":30}}')"
resolved="$(_write_resolved "t.fail")"
log_dir="$(_log_dir)"

rc=0
govctl_execute "$manifest" "$resolved" "t.fail" "$log_dir" 0 0 || rc=$?
assert_exit "failing target: exits non-zero" 1 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_contains "failing target: events.jsonl has target_failed" "target_failed" "$run_dir/events.jsonl"

summary="$(cat "$run_dir/summary.json")"
assert_contains "failing target: summary failed count = 1" '"failed": 1' "$summary"
assert_contains "failing target: summary status = failed" '"status": "failed"' "$summary"


# ── Test: multi-target — first fails, second skipped without continue-on-error ─

manifest="$(_write_manifest '{
    "t.first":  {"command":"fail-cmd",  "preflight":[],"lock":false,"timeout_seconds":30},
    "t.second": {"command":"pass-cmd",  "preflight":[],"lock":false,"timeout_seconds":30}
}')"
resolved="$(_write_resolved "t.first" "t.second")"
log_dir="$(_log_dir)"

rc=0
govctl_execute "$manifest" "$resolved" "t.first t.second" "$log_dir" 0 0 || rc=$?
assert_exit "multi-target abort: exits 1" 1 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_contains "multi-target abort: t.second skipped" "target_skipped" "$run_dir/events.jsonl"

summary="$(cat "$run_dir/summary.json")"
assert_contains "multi-target abort: summary skipped = 1" '"skipped": 1' "$summary"


# ── Test: continue-on-error — first fails, second runs ────────────────────────

manifest="$(_write_manifest '{
    "t.c.first":  {"command":"fail-cmd", "preflight":[],"lock":false,"timeout_seconds":30},
    "t.c.second": {"command":"pass-cmd", "preflight":[],"lock":false,"timeout_seconds":30}
}')"
resolved="$(_write_resolved "t.c.first" "t.c.second")"
log_dir="$(_log_dir)"

rc=0
govctl_execute "$manifest" "$resolved" "t.c.first t.c.second" "$log_dir" 1 0 || rc=$?
assert_exit "continue-on-error: exits 1 (some failed)" 1 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_contains "continue-on-error: t.c.second still ran (target_passed)" "target_passed" "$run_dir/events.jsonl"

summary="$(cat "$run_dir/summary.json")"
assert_contains "continue-on-error: passed = 1" '"passed": 1' "$summary"
assert_contains "continue-on-error: failed = 1" '"failed": 1' "$summary"


# ── Test: preflight failure skips target without running command ───────────────

# Stub: lxc returns non-zero for container-running check.
export LXC_STUB_EXIT=1

manifest="$(_write_manifest '{"t.pf":{"command":"pass-cmd","preflight":["container-running:dev-photo-ingress"],"lock":false,"timeout_seconds":30}}')"
resolved="$(_write_resolved "t.pf")"
log_dir="$(_log_dir)"

rc=0
govctl_execute "$manifest" "$resolved" "t.pf" "$log_dir" 0 0 || rc=$?
assert_exit "preflight-fail: exits non-zero" 1 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_contains "preflight-fail: preflight_failed event emitted" "preflight_failed" "$run_dir/events.jsonl"
assert_file_contains "preflight-fail: target_skipped event emitted" "target_skipped" "$run_dir/events.jsonl"

# Command log file for skipped target must NOT exist (command never ran).
if [[ ! -f "$run_dir/t.pf.log" ]]; then
    _pass "preflight-fail: target log not created (command never ran)"
else
    _fail "preflight-fail: target log not created (command never ran)" "file exists: $run_dir/t.pf.log"
fi

# Reset lxc stub.
export LXC_STUB_EXIT=0


# ── Test: lock: true — DEVCTL_GLOBAL_LOCK_HELD propagated ──────────────────────

# Create a command that writes the value of DEVCTL_GLOBAL_LOCK_HELD to a file.
lock_probe_file="$_TMP/lock-probe.txt"
cat > "$_STUB_BIN/probe-lock-cmd" << PROBE
#!/usr/bin/env bash
printf '%s' "\${DEVCTL_GLOBAL_LOCK_HELD:-0}" > "$lock_probe_file"
exit 0
PROBE
chmod +x "$_STUB_BIN/probe-lock-cmd"

manifest="$(_write_manifest '{"t.lock":{"command":"probe-lock-cmd","preflight":[],"lock":true,"timeout_seconds":30}}')"
resolved="$(_write_resolved "t.lock")"
log_dir="$(_log_dir)"

govctl_execute "$manifest" "$resolved" "t.lock" "$log_dir" 0 0
rc=$?
assert_exit "lock: target exits 0" 0 "$rc"

if [[ -f "$lock_probe_file" ]]; then
    lock_val="$(cat "$lock_probe_file")"
    if [[ "$lock_val" == "1" ]]; then
        _pass "lock: DEVCTL_GLOBAL_LOCK_HELD=1 set during command execution"
    else
        _fail "lock: DEVCTL_GLOBAL_LOCK_HELD=1 set during command execution" "got: $lock_val"
    fi
else
    _fail "lock: DEVCTL_GLOBAL_LOCK_HELD=1 set during command execution" "probe file not written"
fi

# After execution, the lock must be released (DEVCTL_GLOBAL_LOCK_HELD should be unset).
lock_after="${DEVCTL_GLOBAL_LOCK_HELD:-}"
if [[ -z "$lock_after" ]]; then
    _pass "lock: DEVCTL_GLOBAL_LOCK_HELD unset after run completes"
else
    _fail "lock: DEVCTL_GLOBAL_LOCK_HELD unset after run completes" "value: $lock_after"
fi


# ── Test: timeout enforcement ─────────────────────────────────────────────────

cat > "$_STUB_BIN/sleep-cmd" << 'STUB'
#!/usr/bin/env bash
sleep 10
STUB
chmod +x "$_STUB_BIN/sleep-cmd"

manifest="$(_write_manifest '{"t.timeout":{"command":"sleep-cmd","preflight":[],"lock":false,"timeout_seconds":1}}')"
resolved="$(_write_resolved "t.timeout")"
log_dir="$(_log_dir)"

rc=0
govctl_execute "$manifest" "$resolved" "t.timeout" "$log_dir" 0 0 || rc=$?
assert_exit "timeout: exits non-zero when command times out" 1 "$rc"

run_dir="$(_latest_run_dir "$log_dir")"
assert_file_contains "timeout: events.jsonl has target_failed" "target_failed" "$run_dir/events.jsonl"
assert_file_contains "timeout: target_failed includes reason=timeout" "timeout" "$run_dir/events.jsonl"


# ── Test: JSONL event ordering ────────────────────────────────────────────────

_make_stub_cmd "order-cmd" 0

manifest="$(_write_manifest '{"t.order":{"command":"order-cmd","preflight":[],"lock":false,"timeout_seconds":30}}')"
resolved="$(_write_resolved "t.order")"
log_dir="$(_log_dir)"

govctl_execute "$manifest" "$resolved" "t.order" "$log_dir" 0 0
run_dir="$(_latest_run_dir "$log_dir")"

# Extract event names in order.
events="$(python3 -c "
import json, sys
for line in open('$run_dir/events.jsonl'):
    try:
        print(json.loads(line)['event'])
    except:
        pass
")"

expected_order="run_started
target_started
target_passed
run_finished"

if [[ "$events" == "$expected_order" ]]; then
    _pass "event ordering: run_started → target_started → target_passed → run_finished"
else
    _fail "event ordering: run_started → target_started → target_passed → run_finished" \
        "got: $(printf '%s' "$events" | tr '\n' ',')"
fi


# ── Test: run_finished totals in events.jsonl ─────────────────────────────────

run_dir="$(_latest_run_dir "$log_dir")"
run_finished_line="$(grep '"run_finished"' "$run_dir/events.jsonl")"
assert_contains 'run_finished: has total_targets field' '"total_targets"' "$run_finished_line"
assert_contains 'run_finished: has passed field' '"passed"' "$run_finished_line"
assert_contains 'run_finished: has failed field' '"failed"' "$run_finished_line"
assert_contains 'run_finished: has skipped field' '"skipped"' "$run_finished_line"
assert_contains 'run_finished: has duration_seconds field' '"duration_seconds"' "$run_finished_line"


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

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
