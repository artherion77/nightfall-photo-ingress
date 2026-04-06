#!/usr/bin/env bash
# tests/unit/test_govctl_preflights.sh — Unit tests for dev/lib/govctl-preflights.sh
#
# Runs without a live LXC environment by injecting a configurable `lxc` stub
# via PATH manipulation.  All `lxc` calls honour env vars set by each test.
#
# Usage:
#   bash tests/unit/test_govctl_preflights.sh
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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

# assert_exit <desc> <expected_exit> <actual_exit>
assert_exit() {
    local desc="$1" expected="$2" actual="$3"
    if [[ "$actual" -eq "$expected" ]]; then
        _pass "$desc"
    else
        _fail "$desc" "expected exit $expected, got $actual"
    fi
}

# assert_contains <desc> <needle> <haystack>
assert_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if printf '%s' "$haystack" | grep -qF "$needle"; then
        _pass "$desc"
    else
        _fail "$desc" "output '$(printf '%s' "$haystack" | head -c 200)' does not contain '$needle'"
    fi
}

# run_check <check-string> — sets rc and output; never exits even on failure.
run_check() {
    local check_string="$1"
    rc=0
    output="$(govctl_run_preflight "$check_string")" || rc=$?
}

# ── Stub setup ────────────────────────────────────────────────────────────────

_STUB_BIN="$(mktemp -d)"
_ORIGINAL_PATH="$PATH"

_cleanup() {
    PATH="$_ORIGINAL_PATH"
    rm -rf "$_STUB_BIN"
}
trap _cleanup EXIT

# Write the configurable lxc stub.  Each subcommand honours env vars:
#
#   lxc info <name>          → LXC_INFO_EXIT (0|1), LXC_INFO_OUTPUT
#   lxc info <c>/<snap>      → LXC_INFO_SNAPSHOT_EXIT (0|1)
#   lxc list <name> …        → LXC_LIST_OUTPUT  (first line = status csv)
#   lxc config device list … → LXC_DEVICE_LIST_OUTPUT, LXC_DEVICE_LIST_EXIT
#   lxc config device show … → LXC_DEVICE_SHOW_OUTPUT, LXC_DEVICE_SHOW_EXIT
#   lxc exec … -- node …     → LXC_EXEC_NODE_OUTPUT, LXC_EXEC_NODE_EXIT
#   lxc exec … -- bash …     → LXC_EXEC_BASH_OUTPUT, LXC_EXEC_BASH_EXIT
#   lxc exec … -- test …     → LXC_EXEC_TEST_EXIT
cat > "$_STUB_BIN/lxc" << 'STUB'
#!/usr/bin/env bash
_sub="$1"; shift
case "$_sub" in
    info)
        if [[ "$1" == */* ]]; then
            exit "${LXC_INFO_SNAPSHOT_EXIT:-0}"
        fi
        [[ "${LXC_INFO_EXIT:-0}" != "0" ]] && exit 1
        printf '%s\n' "${LXC_INFO_OUTPUT:-}"
        exit 0
        ;;
    list)
        printf '%s\n' "${LXC_LIST_OUTPUT:-}"
        exit 0
        ;;
    config)
        _op="$1"; shift
        case "$_op" in
            device)
                _dev_op="$1"; shift
                case "$_dev_op" in
                    list)
                        printf '%s\n' "${LXC_DEVICE_LIST_OUTPUT:-}"
                        exit "${LXC_DEVICE_LIST_EXIT:-0}"
                        ;;
                    show)
                        [[ "${LXC_DEVICE_SHOW_EXIT:-0}" != "0" ]] && exit 1
                        printf '%s\n' "${LXC_DEVICE_SHOW_OUTPUT:-}"
                        exit 0
                        ;;
                esac
                ;;
        esac
        exit 0
        ;;
    exec)
        shift  # container name
        shift  # --
        _cmd="$1"
        case "$_cmd" in
            node)
                printf '%s\n' "${LXC_EXEC_NODE_OUTPUT:-v20.0.0}"
                exit "${LXC_EXEC_NODE_EXIT:-0}"
                ;;
            bash)
                printf '%s\n' "${LXC_EXEC_BASH_OUTPUT:-}"
                exit "${LXC_EXEC_BASH_EXIT:-0}"
                ;;
            test)
                exit "${LXC_EXEC_TEST_EXIT:-0}"
                ;;
            *)
                exit "${LXC_EXEC_EXIT:-0}"
                ;;
        esac
        ;;
esac
exit 0
STUB
chmod +x "$_STUB_BIN/lxc"

export PATH="$_STUB_BIN:$_ORIGINAL_PATH"

# ── Source the library under test ─────────────────────────────────────────────

# shellcheck source=../../dev/lib/govctl-preflights.sh
source "$PREFLIGHTS_LIB"

# Use a temp directory as the fake project root for file-based checks.
_FAKE_PROJECT_ROOT="$(mktemp -d)"

_cleanup_fake_root() {
    rm -rf "$_FAKE_PROJECT_ROOT"
}
trap '_cleanup; _cleanup_fake_root' EXIT

# Point the library at our fake project root (functions read this at call time).
GOVCTL_PREFLIGHTS_PROJECT_ROOT="$_FAKE_PROJECT_ROOT"
GOVCTL_DEV_CONTAINER="test-container"

# ── Reset stub env vars between tests ─────────────────────────────────────────

_reset_stub_env() {
    unset LXC_INFO_EXIT LXC_INFO_OUTPUT LXC_INFO_SNAPSHOT_EXIT
    unset LXC_LIST_OUTPUT
    unset LXC_DEVICE_LIST_OUTPUT LXC_DEVICE_LIST_EXIT
    unset LXC_DEVICE_SHOW_OUTPUT LXC_DEVICE_SHOW_EXIT
    unset LXC_EXEC_NODE_OUTPUT LXC_EXEC_NODE_EXIT
    unset LXC_EXEC_BASH_OUTPUT LXC_EXEC_BASH_EXIT
    unset LXC_EXEC_TEST_EXIT LXC_EXEC_EXIT
}

rc=0; output=""

# ── Tests: container-exists ───────────────────────────────────────────────────

_reset_stub_env
export LXC_INFO_EXIT=0
run_check "container-exists:my-container"
assert_exit "container-exists PASS: exit 0 when lxc info succeeds" 0 "$rc"

_reset_stub_env
export LXC_INFO_EXIT=1
run_check "container-exists:missing-container"
assert_exit "container-exists FAIL: exit 1 when lxc info fails" 1 "$rc"
assert_contains "container-exists FAIL: reason mentions container name" "missing-container" "$output"

# ── Tests: container-running ──────────────────────────────────────────────────

_reset_stub_env
export LXC_LIST_OUTPUT="RUNNING"
run_check "container-running:my-container"
assert_exit "container-running PASS: exit 0 when status is RUNNING" 0 "$rc"

_reset_stub_env
export LXC_LIST_OUTPUT="STOPPED"
run_check "container-running:my-container"
assert_exit "container-running FAIL: exit 1 when status is STOPPED" 1 "$rc"
assert_contains "container-running FAIL: reason mentions container name" "my-container" "$output"
assert_contains "container-running FAIL: reason mentions stopped state" "stopped" "$output"

# ── Tests: snapshot-exists ────────────────────────────────────────────────────

_reset_stub_env
export LXC_INFO_SNAPSHOT_EXIT=0
run_check "snapshot-exists:my-container/base"
assert_exit "snapshot-exists PASS: exit 0 when snapshot reference resolves" 0 "$rc"

_reset_stub_env
export LXC_INFO_SNAPSHOT_EXIT=1
run_check "snapshot-exists:my-container/missing-snap"
assert_exit "snapshot-exists FAIL: exit 1 when snapshot not found" 1 "$rc"
assert_contains "snapshot-exists FAIL: reason mentions snapshot name" "missing-snap" "$output"
assert_contains "snapshot-exists FAIL: reason mentions container name" "my-container" "$output"

# ── Tests: cache-mounts-active ────────────────────────────────────────────────

_reset_stub_env
export LXC_DEVICE_LIST_OUTPUT="cache-root-npm-home
cache-root-cache-npm
cache-root-cache-pip
cache-root-cache-playwright"
run_check "cache-mounts-active"
assert_exit "cache-mounts-active PASS: exit 0 when all 4 devices present" 0 "$rc"

_reset_stub_env
export LXC_DEVICE_LIST_OUTPUT="cache-root-npm-home
cache-root-cache-npm
cache-root-cache-pip"
run_check "cache-mounts-active"
assert_exit "cache-mounts-active FAIL: exit 1 when a device is missing" 1 "$rc"
assert_contains "cache-mounts-active FAIL: reason mentions missing device" "cache-root-cache-playwright" "$output"

_reset_stub_env
export LXC_DEVICE_LIST_EXIT=1
run_check "cache-mounts-active"
assert_exit "cache-mounts-active FAIL: exit 1 when lxc config device list fails" 1 "$rc"

# ── Tests: stack-drift-free ───────────────────────────────────────────────────

# PASS: create real host manifest files; stub returns matching hash.
_reset_stub_env
mkdir -p "$_FAKE_PROJECT_ROOT/webui"
printf '{"name":"webui"}' > "$_FAKE_PROJECT_ROOT/webui/package.json"
printf '{"lockfileVersion":3}' > "$_FAKE_PROJECT_ROOT/webui/package-lock.json"
_expected_hash="$(cat \
    "$_FAKE_PROJECT_ROOT/webui/package.json" \
    "$_FAKE_PROJECT_ROOT/webui/package-lock.json" \
    | sha256sum | awk '{print $1}')"
export LXC_EXEC_BASH_OUTPUT="$_expected_hash"
run_check "stack-drift-free:webui"
assert_exit "stack-drift-free PASS: exit 0 when host and container hashes match" 0 "$rc"

# FAIL: stub returns a different hash.
_reset_stub_env
export LXC_EXEC_BASH_OUTPUT="0000000000000000000000000000000000000000000000000000000000000000"
run_check "stack-drift-free:webui"
assert_exit "stack-drift-free FAIL: exit 1 when hashes differ" 1 "$rc"
assert_contains "stack-drift-free FAIL: reason mentions drift" "drift" "$output"
assert_contains "stack-drift-free FAIL: reason mentions stack name" "webui" "$output"

# FAIL: missing manifest files.
_reset_stub_env
rm -f "$_FAKE_PROJECT_ROOT/webui/package-lock.json"
run_check "stack-drift-free:webui"
assert_exit "stack-drift-free FAIL: exit 1 when host manifest files missing" 1 "$rc"
assert_contains "stack-drift-free FAIL: reason mentions missing files" "missing" "$output"
# Restore for later tests
printf '{"lockfileVersion":3}' > "$_FAKE_PROJECT_ROOT/webui/package-lock.json"

# FAIL: unknown stack name.
_reset_stub_env
run_check "stack-drift-free:unknown-stack"
assert_exit "stack-drift-free FAIL: exit 1 for unknown stack" 1 "$rc"
assert_contains "stack-drift-free FAIL: reason mentions unknown stack" "unknown-stack" "$output"

# ── Tests: node-version-match ─────────────────────────────────────────────────

# PASS: container version matches pinned version.
_reset_stub_env
printf '20.15.0\n' > "$_FAKE_PROJECT_ROOT/.node-version"
export LXC_EXEC_NODE_OUTPUT="v20.15.0"
run_check "node-version-match"
assert_exit "node-version-match PASS: exit 0 when versions match" 0 "$rc"

# FAIL: version mismatch.
_reset_stub_env
export LXC_EXEC_NODE_OUTPUT="v18.19.0"
run_check "node-version-match"
assert_exit "node-version-match FAIL: exit 1 when container version differs" 1 "$rc"
assert_contains "node-version-match FAIL: reason mentions container version" "18.19.0" "$output"
assert_contains "node-version-match FAIL: reason mentions pinned version" "20.15.0" "$output"

# FAIL: no version file.
_reset_stub_env
rm -f "$_FAKE_PROJECT_ROOT/.node-version"
run_check "node-version-match"
assert_exit "node-version-match FAIL: exit 1 when no .node-version file" 1 "$rc"
assert_contains "node-version-match FAIL: reason mentions missing file" ".node-version" "$output"
# Restore version file for subsequent tests that touch the same root.
printf '20.15.0\n' > "$_FAKE_PROJECT_ROOT/.node-version"

# ── Tests: venv-exists ────────────────────────────────────────────────────────

_reset_stub_env
export LXC_EXEC_TEST_EXIT=0
run_check "venv-exists:/opt/ingress"
assert_exit "venv-exists PASS: exit 0 when container test -d succeeds" 0 "$rc"

_reset_stub_env
export LXC_EXEC_TEST_EXIT=1
run_check "venv-exists:/opt/ingress"
assert_exit "venv-exists FAIL: exit 1 when directory absent" 1 "$rc"
assert_contains "venv-exists FAIL: reason mentions path" "/opt/ingress" "$output"

# ── Tests: wheel-exists ───────────────────────────────────────────────────────

_reset_stub_env
mkdir -p "$_FAKE_PROJECT_ROOT/dist"
touch "$_FAKE_PROJECT_ROOT/dist/nightfall_photo_ingress-1.0.0-py3-none-any.whl"
run_check "wheel-exists"
assert_exit "wheel-exists PASS: exit 0 when .whl present in dist/" 0 "$rc"

_reset_stub_env
rm -f "$_FAKE_PROJECT_ROOT/dist/"*.whl
run_check "wheel-exists"
assert_exit "wheel-exists FAIL: exit 1 when dist/ has no .whl files" 1 "$rc"
assert_contains "wheel-exists FAIL: reason mentions dist/" "dist/" "$output"

# ── Tests: bridge-network ─────────────────────────────────────────────────────

_reset_stub_env
export LXC_DEVICE_SHOW_OUTPUT="eth0:
  name: eth0
  network: br-staging
  type: nic"
run_check "bridge-network:br-staging"
assert_exit "bridge-network PASS: exit 0 when bridge present in device config" 0 "$rc"

_reset_stub_env
export LXC_DEVICE_SHOW_OUTPUT="eth0:
  name: eth0
  network: lxdbr0
  type: nic"
run_check "bridge-network:br-staging"
assert_exit "bridge-network FAIL: exit 1 when bridge absent from device config" 1 "$rc"
assert_contains "bridge-network FAIL: reason mentions bridge name" "br-staging" "$output"

_reset_stub_env
export LXC_DEVICE_SHOW_EXIT=1
run_check "bridge-network:br-staging"
assert_exit "bridge-network FAIL: exit 1 when lxc config device show fails" 1 "$rc"

# ── Tests: dispatch ───────────────────────────────────────────────────────────

_reset_stub_env
run_check "unknown-check-name"
assert_exit "dispatch FAIL: exit 1 for unrecognised check name" 1 "$rc"
assert_contains "dispatch FAIL: reason mentions unknown check name" "unknown-check-name" "$output"

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
