#!/usr/bin/env bash
# govctl-executor.sh — Core execution engine for govctl.
#
# SOURCE this file; do not execute it directly.
#
# Public entry point:
#   govctl_execute <manifest_json_file> <resolved_targets_file> \
#                  <requested_targets_string> <log_dir> \
#                  [continue_on_error=0] [dry_run=0]
#
#   <manifest_json_file>      Path to the normalised JSON produced by govctl_manifest.py.
#   <resolved_targets_file>   Path to a file with one target name per line,
#                             in execution order (produced by govctl_resolve.py).
#   <requested_targets_string> Space-separated list of originally-requested targets/groups (for events).
#   <log_dir>                 Root directory for run artifacts (default: artifacts/govctl).
#   continue_on_error         Set to 1 to keep running after a target failure.
#   dry_run                   Set to 1 to resolve and print the plan without executing.
#
# Artifacts produced:
#   <log_dir>/run-<timestamp>/events.jsonl
#   <log_dir>/run-<timestamp>/<target-name>.log
#   <log_dir>/run-<timestamp>/summary.json
#
# The function exits with 0 if all executed targets passed, 1 otherwise.

# Resolve paths relative to this file's location at source time.
_GOVCTL_EXEC_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOVCTL_EXEC_PROJECT_ROOT="$(cd "$_GOVCTL_EXEC_SCRIPT_DIR/../.." && pwd)"
_GOVCTL_ARTIFACT_HASH_PY="$_GOVCTL_EXEC_SCRIPT_DIR/artifact_hash.py"

# Global repo lock — matches devctl's lock configuration exactly.
_GOVCTL_REPO_LOCK_FILE="/tmp/nightfall-repo.lock"
_GOVCTL_REPO_LOCK_FD=201          # Different FD from devctl's 200 to avoid conflicts.
_GOVCTL_REPO_LOCK_TIMEOUT_SEC="${REPO_LOCK_TIMEOUT_SEC:-300}"


# ── Helpers ───────────────────────────────────────────────────────────────────

# Emit a single ISO-8601 UTC timestamp string.
_govctl_timestamp() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Emit one JSONL line to the events file.
# Usage: _govctl_emit_event <events_file> <json_object>
_govctl_emit_event() {
    local events_file="$1"
    local json_obj="$2"
    printf '%s\n' "$json_obj" >> "$events_file"
}

# Build a minimal JSON string (no external deps — pure Bash string assembly).
# Scalars only; values are single-quoted internally so double-quotes in values
# are escaped.
_govctl_json_str() {
    local value="$1"
    # Escape backslash, double-quote, and control chars that matter in JSON.
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

# Acquire the global repo lock (flock).
# Sets _GOVCTL_LOCK_HELD=1 if acquisition succeeds.
_govctl_acquire_lock() {
    if [[ "${DEVCTL_GLOBAL_LOCK_HELD:-}" == "1" ]]; then
        # Caller already holds the lock; skip to avoid deadlock.
        return 0
    fi
    exec {_GOVCTL_REPO_LOCK_FD}>"$_GOVCTL_REPO_LOCK_FILE"
    if ! flock -w "$_GOVCTL_REPO_LOCK_TIMEOUT_SEC" "$_GOVCTL_REPO_LOCK_FD"; then
        echo "[govctl] Timed out waiting for global repo lock ($_GOVCTL_REPO_LOCK_FILE)" >&2
        exec {_GOVCTL_REPO_LOCK_FD}>&-
        return 1
    fi
    export DEVCTL_GLOBAL_LOCK_HELD=1
    _GOVCTL_LOCK_HELD_BY_US=1
}

# Release the global repo lock if we acquired it.
_govctl_release_lock() {
    if [[ "${_GOVCTL_LOCK_HELD_BY_US:-}" == "1" ]]; then
        flock -u "$_GOVCTL_REPO_LOCK_FD"
        exec {_GOVCTL_REPO_LOCK_FD}>&-
        unset DEVCTL_GLOBAL_LOCK_HELD
        _GOVCTL_LOCK_HELD_BY_US=0
    fi
}

# Read a field from a target's JSON block using python3 (available in venv).
# Usage: _govctl_target_field <manifest_json_file> <target_name> <field>
_govctl_target_field() {
    local manifest_json="$1"
    local target_name="$2"
    local field="$3"
    python3 - "$manifest_json" "$target_name" "$field" <<'PY'
import json, sys
manifest = json.loads(open(sys.argv[1]).read())
target = manifest["targets"][sys.argv[2]]
val = target.get(sys.argv[3], "")
if isinstance(val, list):
    print("\n".join(val))
elif isinstance(val, bool):
    print("1" if val else "0")
else:
    print(val)
PY
}

# Build the JSON array literal for a list of strings.
_govctl_json_array() {
    python3 - "$@" <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
}

# Print a separator banner to the terminal.
_govctl_banner() {
    local width=72
    local text="$1"
    printf '\033[0;36m%s %s %s\033[0m\n' \
        "$(printf '─%.0s' $(seq 1 4))" \
        "$text" \
        "$(printf '─%.0s' $(seq 1 $((width - ${#text} - 6))))"
}


# Compute and emit build_fingerprint event for known artifact-producing targets.
_govctl_emit_build_fingerprint_if_applicable() {
    local events_file="$1"
    local target="$2"

    local artifact_path=""
    case "$target" in
        web.build) artifact_path="webui/build/" ;;
        backend.build.wheel) artifact_path="dist/*.whl" ;;
        *) return 0 ;;
    esac

    local sha
    sha="$(python3 "$_GOVCTL_ARTIFACT_HASH_PY" compute "$artifact_path" --cwd "$GOVCTL_EXEC_PROJECT_ROOT" 2>/dev/null)" || return 1

    _govctl_emit_event "$events_file" \
        "{\"event\":\"build_fingerprint\",\"target\":\"$target\",\"sha256\":$(_govctl_json_str "$sha"),\"artifact_path\":$(_govctl_json_str "$artifact_path"),\"timestamp\":\"$(_govctl_timestamp)\"}"
    return 0
}


# ── govctl_execute ────────────────────────────────────────────────────────────

govctl_execute() {
    local manifest_json_file="$1"
    local resolved_targets_file="$2"
    local requested_targets_str="$3"
    local log_dir="${4:-$GOVCTL_EXEC_PROJECT_ROOT/artifacts/govctl}"
    local continue_on_error="${5:-0}"
    local dry_run="${6:-0}"

    # ── Build run directory ────────────────────────────────────────────────

    local run_ts run_id run_dir events_file
    run_ts="$(date -u +"%Y%m%dT%H%M%S")"
    # Short suffix for uniqueness within the same second.
    local run_suffix
    run_suffix="$(cat /dev/urandom 2>/dev/null | tr -dc 'a-z0-9' | head -c 6 2>/dev/null || echo "xxxxxx")"
    run_id="${run_ts}-${run_suffix}"
    run_dir="${log_dir}/run-${run_id}"
    events_file="${run_dir}/events.jsonl"

    # Read resolved targets into an array.
    local -a resolved=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && resolved+=("$line")
    done < "$resolved_targets_file"

    if [[ ${#resolved[@]} -eq 0 ]]; then
        echo "[govctl] No targets to execute." >&2
        return 1
    fi

    # ── Dry-run mode ───────────────────────────────────────────────────────

    if [[ "$dry_run" == "1" ]]; then
        echo "[govctl] Dry run — execution plan:"
        local idx=1
        for t in "${resolved[@]}"; do
            local cmd
            cmd="$(_govctl_target_field "$manifest_json_file" "$t" "command")"
            printf '  %2d. %s\n      %s\n' "$idx" "$t" "$(printf '%s' "$cmd" | head -n 1)"
            ((idx++)) || true
        done
        echo "[govctl] ${#resolved[@]} target(s) would run."
        return 0
    fi

    # ── Create run directory ───────────────────────────────────────────────

    mkdir -p "$run_dir"

    # ── Emit run_started ───────────────────────────────────────────────────

    # Build JSON arrays for targets and resolved fields.
    IFS=' ' read -ra requested_arr <<< "$requested_targets_str"
    local targets_json resolved_json
    targets_json="$(_govctl_json_array "${requested_arr[@]}")"
    resolved_json="$(_govctl_json_array "${resolved[@]}")"

    _govctl_emit_event "$events_file" \
        "{\"event\":\"run_started\",\"timestamp\":\"$(_govctl_timestamp)\",\"run_id\":\"$run_id\",\"targets\":$targets_json,\"resolved\":$resolved_json}"

    export GOVCTL_EVENTS_FILE="$events_file"

    _govctl_banner "govctl run $run_id"
    echo "  Targets requested : $requested_targets_str"
    echo "  Targets resolved  : ${resolved[*]}"
    echo "  Log directory     : $run_dir"
    echo ""

    # ── Per-target counters ────────────────────────────────────────────────

    local total_passed=0 total_failed=0 total_skipped=0
    local run_start_epoch
    run_start_epoch="$(date +%s)"

    # Track which targets failed so dependents can be skipped.
    # We operate on an already-resolved list (executor does not re-resolve);
    # any skipping is driven only by failure propagation, not by re-reading deps.
    declare -A _target_failed=()

    # ── Target loop ────────────────────────────────────────────────────────

    for target in "${resolved[@]}"; do
        export GOVCTL_CURRENT_TARGET="$target"

        # ── Read target metadata ───────────────────────────────────────────

        local command timeout_sec lock_required preflight_str
        command="$(_govctl_target_field   "$manifest_json_file" "$target" "command")"
        timeout_sec="$(_govctl_target_field "$manifest_json_file" "$target" "timeout_seconds")"
        lock_required="$(_govctl_target_field "$manifest_json_file" "$target" "lock")"
        preflight_str="$(_govctl_target_field "$manifest_json_file" "$target" "preflight")"

        # timeout_sec default.
        [[ -z "$timeout_sec" || "$timeout_sec" == "0" ]] && timeout_sec=300

        # Build preflight array from newline-delimited output.
        local -a preflights=()
        while IFS= read -r pf_line; do
            [[ -n "$pf_line" ]] && preflights+=("$pf_line")
        done <<< "$preflight_str"

        # ── Preflight checks ───────────────────────────────────────────────

        local preflight_ok=1   # assume pass

        for check in "${preflights[@]}"; do
            local pf_reason pf_exit
            unset GOVCTL_ARTIFACT_EVENT_ARTIFACT
            unset GOVCTL_ARTIFACT_EVENT_EXPECTED
            unset GOVCTL_ARTIFACT_EVENT_ACTUAL

            local pf_out
            pf_out="$(mktemp)"
            if govctl_run_preflight "$check" > "$pf_out"; then
                pf_exit=0
            else
                pf_exit=$?
            fi
            pf_reason="$(cat "$pf_out")"
            rm -f "$pf_out"

            if [[ "$pf_exit" -eq 0 ]]; then
                _govctl_emit_event "$events_file" \
                    "{\"event\":\"preflight_passed\",\"target\":\"$target\",\"check\":$(_govctl_json_str "$check"),\"timestamp\":\"$(_govctl_timestamp)\"}"
            else
                _govctl_emit_event "$events_file" \
                    "{\"event\":\"preflight_failed\",\"target\":\"$target\",\"check\":$(_govctl_json_str "$check"),\"reason\":$(_govctl_json_str "$pf_reason"),\"timestamp\":\"$(_govctl_timestamp)\"}"
                preflight_ok=0
            fi

            if [[ "$check" == artifact-hash-verified:* ]]; then
                local artifact_ref expected_sha actual_sha
                artifact_ref="${GOVCTL_ARTIFACT_EVENT_ARTIFACT:-}"
                expected_sha="${GOVCTL_ARTIFACT_EVENT_EXPECTED:-}"
                actual_sha="${GOVCTL_ARTIFACT_EVENT_ACTUAL:-}"

                if [[ -n "$artifact_ref" && -n "$expected_sha" && -n "$actual_sha" ]]; then
                    if [[ "$pf_exit" -eq 0 ]]; then
                        _govctl_emit_event "$events_file" \
                            "{\"event\":\"artifact_verified\",\"target\":\"$target\",\"artifact\":$(_govctl_json_str "$artifact_ref"),\"expected_sha256\":$(_govctl_json_str "$expected_sha"),\"actual_sha256\":$(_govctl_json_str "$actual_sha"),\"timestamp\":\"$(_govctl_timestamp)\"}"
                    else
                        _govctl_emit_event "$events_file" \
                            "{\"event\":\"artifact_rejected\",\"target\":\"$target\",\"artifact\":$(_govctl_json_str "$artifact_ref"),\"expected_sha256\":$(_govctl_json_str "$expected_sha"),\"actual_sha256\":$(_govctl_json_str "$actual_sha"),\"timestamp\":\"$(_govctl_timestamp)\"}"
                    fi
                fi
            fi
        done

        if [[ "$preflight_ok" -eq 0 ]]; then
            _govctl_emit_event "$events_file" \
                "{\"event\":\"target_skipped\",\"target\":\"$target\",\"reason\":\"preflight failed\",\"timestamp\":\"$(_govctl_timestamp)\"}"
            echo "[govctl] SKIP $target — preflight failed"
            ((total_skipped++)) || true
            _target_failed["$target"]=1

            if [[ "$continue_on_error" != "1" ]]; then
                break
            fi
            continue
        fi

        # ── Acquire lock (if required) ─────────────────────────────────────

        _GOVCTL_LOCK_HELD_BY_US=0
        if [[ "$lock_required" == "1" ]]; then
            if ! _govctl_acquire_lock; then
                _govctl_emit_event "$events_file" \
                    "{\"event\":\"target_failed\",\"target\":\"$target\",\"exit_code\":1,\"duration_seconds\":0,\"reason\":\"lock_timeout\",\"timestamp\":\"$(_govctl_timestamp)\"}"
                ((total_failed++)) || true
                _target_failed["$target"]=1

                if [[ "$continue_on_error" != "1" ]]; then
                    break
                fi
                continue
            fi
        fi

        # ── Emit target_started ────────────────────────────────────────────

        _govctl_emit_event "$events_file" \
            "{\"event\":\"target_started\",\"target\":\"$target\",\"command\":$(_govctl_json_str "$(printf '%s' "$command" | tr '\n' ' ' | sed 's/  */ /g; s/^ //; s/ $//')"),\"timestamp\":\"$(_govctl_timestamp)\"}"

        _govctl_banner "$target"

        # ── Execute command ────────────────────────────────────────────────

        local target_log="${run_dir}/${target//\//_}.log"
        local target_start_epoch exit_code
        target_start_epoch="$(date +%s)"
        exit_code=0

        # Use --foreground so timeout does NOT create a new process group.
        # Without --foreground, snap-confine (snap-installed LXD) hangs
        # when called from a child in a non-leader process group.
        # See design doc §13 and GitHub issue #12.
        (
            cd "$GOVCTL_EXEC_PROJECT_ROOT"
            timeout --foreground "$timeout_sec" bash -c "$command"
        ) 2>&1 | tee "$target_log" || exit_code="${PIPESTATUS[0]:-1}"

        # Detect timeout (exit code 124 from GNU timeout).
        local duration_seconds timeout_reason=""
        duration_seconds=$(( $(date +%s) - target_start_epoch ))
        [[ "$exit_code" -eq 124 ]] && timeout_reason=",\"reason\":\"timeout\""

        # ── Release lock ───────────────────────────────────────────────────

        _govctl_release_lock

        # ── Emit target_passed / target_failed ─────────────────────────────

        if [[ "$exit_code" -eq 0 ]]; then
            _govctl_emit_event "$events_file" \
                "{\"event\":\"target_passed\",\"target\":\"$target\",\"exit_code\":0,\"duration_seconds\":$duration_seconds,\"timestamp\":\"$(_govctl_timestamp)\"}"

            if ! _govctl_emit_build_fingerprint_if_applicable "$events_file" "$target"; then
                _govctl_emit_event "$events_file" \
                    "{\"event\":\"target_failed\",\"target\":\"$target\",\"exit_code\":1,\"duration_seconds\":$duration_seconds,\"reason\":\"fingerprint_emit_failed\",\"timestamp\":\"$(_govctl_timestamp)\"}"
                _govctl_banner "$target: FAILED (fingerprint emit failed)"
                ((total_failed++)) || true
                _target_failed["$target"]=1
                if [[ "$continue_on_error" != "1" ]]; then
                    break
                fi
                continue
            fi

            _govctl_banner "$target: PASSED (${duration_seconds}s)"
            ((total_passed++)) || true
        else
            _govctl_emit_event "$events_file" \
                "{\"event\":\"target_failed\",\"target\":\"$target\",\"exit_code\":$exit_code,\"duration_seconds\":$duration_seconds${timeout_reason},\"timestamp\":\"$(_govctl_timestamp)\"}"
            _govctl_banner "$target: FAILED (exit $exit_code, ${duration_seconds}s)"
            ((total_failed++)) || true
            _target_failed["$target"]=1

            if [[ "$continue_on_error" != "1" ]]; then
                # Skip all remaining targets.
                local remaining_idx
                remaining_idx=0
                local found_current=0
                for remaining in "${resolved[@]}"; do
                    [[ "$remaining" == "$target" ]] && found_current=1 && continue
                    [[ "$found_current" -eq 0 ]] && continue
                    _govctl_emit_event "$events_file" \
                        "{\"event\":\"target_skipped\",\"target\":\"$remaining\",\"reason\":\"dependency $target failed\",\"timestamp\":\"$(_govctl_timestamp)\"}"
                    ((total_skipped++)) || true
                    ((remaining_idx++)) || true
                done
                break
            fi
        fi

        echo ""
    done

    # ── Emit run_finished ──────────────────────────────────────────────────

    local run_duration
    run_duration=$(( $(date +%s) - run_start_epoch ))

    _govctl_emit_event "$events_file" \
        "{\"event\":\"run_finished\",\"timestamp\":\"$(_govctl_timestamp)\",\"run_id\":\"$run_id\",\"total_targets\":${#resolved[@]},\"passed\":$total_passed,\"failed\":$total_failed,\"skipped\":$total_skipped,\"duration_seconds\":$run_duration}"

    # ── Write summary.json ─────────────────────────────────────────────────

    _govctl_write_summary \
        "$run_dir/summary.json" \
        "$run_id" \
        "$requested_targets_str" \
        "$resolved_targets_file" \
        "$events_file" \
        "$total_passed" "$total_failed" "$total_skipped" "$run_duration"

    # ── Print run summary banner ───────────────────────────────────────────

    echo ""
    _govctl_banner "Run complete: $total_passed passed, $total_failed failed, $total_skipped skipped (${run_duration}s)"
    echo "  Events : $events_file"
    echo "  Summary: $run_dir/summary.json"
    echo ""

    # Return non-zero if any target failed or was skipped (skips indicate an
    # unmet preflight or a dependency failure — either way the run is incomplete).
    if [[ "$total_failed" -gt 0 || "$total_skipped" -gt 0 ]]; then
        return 1
    fi
    return 0
}


# ── _govctl_write_summary ─────────────────────────────────────────────────────
#
# Writes summary.json by replaying events.jsonl with python3.

_govctl_write_summary() {
    local summary_file="$1"
    local run_id="$2"
    local requested_str="$3"
    local resolved_file="$4"
    local events_file="$5"
    local total_passed="$6"
    local total_failed="$7"
    local total_skipped="$8"
    local run_duration="$9"

    python3 - \
        "$summary_file" \
        "$run_id" \
        "$requested_str" \
        "$resolved_file" \
        "$events_file" \
        "$total_passed" "$total_failed" "$total_skipped" "$run_duration" \
        <<'PY'
import json, sys
from pathlib import Path

summary_file   = sys.argv[1]
run_id         = sys.argv[2]
requested_str  = sys.argv[3]
resolved_file  = Path(sys.argv[4])
events_file    = Path(sys.argv[5])
total_passed   = int(sys.argv[6])
total_failed   = int(sys.argv[7])
total_skipped  = int(sys.argv[8])
run_duration   = float(sys.argv[9])

requested = requested_str.split()
resolved  = [l for l in resolved_file.read_text().splitlines() if l.strip()]

results = {}
for line in events_file.read_text().splitlines():
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        continue
    t = ev.get("target")
    if not t:
        continue
    event = ev.get("event", "")
    if event == "target_passed":
        results[t] = {
            "status": "passed",
            "exit_code": ev.get("exit_code", 0),
            "duration_seconds": ev.get("duration_seconds", 0),
        }
    elif event == "target_failed":
        results[t] = {
            "status": "failed",
            "exit_code": ev.get("exit_code", 1),
            "duration_seconds": ev.get("duration_seconds", 0),
        }
    elif event == "target_skipped":
        results.setdefault(t, {
            "status": "skipped",
            "reason": ev.get("reason", ""),
        })

summary = {
    "run_id": run_id,
    "requested": requested,
    "resolved": resolved,
    "results": results,
    "totals": {
        "passed":  total_passed,
        "failed":  total_failed,
        "skipped": total_skipped,
    },
    "duration_seconds": run_duration,
}

Path(summary_file).write_text(json.dumps(summary, indent=2) + "\n")
PY
}
