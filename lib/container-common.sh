#!/usr/bin/env bash
# Shared shell helpers for container lifecycle scripts.

set -euo pipefail

nf_log_info() {
    local scope="$1"
    shift
    printf '\033[0;34m[%s]\033[0m %s\n' "$scope" "$*"
}

nf_log_ok() {
    local scope="$1"
    shift
    printf '\033[0;32m[%s] OK:\033[0m %s\n' "$scope" "$*"
}

nf_log_warn() {
    local scope="$1"
    shift
    printf '\033[0;33m[%s] WARN:\033[0m %s\n' "$scope" "$*" >&2
}

nf_log_fail() {
    local scope="$1"
    shift
    printf '\033[0;31m[%s] FAIL:\033[0m %s\n' "$scope" "$*" >&2
    exit 1
}

nf_require_container_exists() {
    local container="$1"
    local hint="$2"
    local scope="${3:-container}"

    if ! lxc info "$container" &>/dev/null; then
        nf_log_fail "$scope" "Container '$container' does not exist. Run: $hint"
    fi
}

nf_require_container_running() {
    local container="$1"
    local hint="$2"
    local scope="${3:-container}"

    if lxc info "$container" 2>/dev/null | grep -Eiq 'Status:[[:space:]]+running'; then
        return
    fi

    local state=""
    state="$(lxc list "$container" -c s --format csv 2>/dev/null | head -n 1 | tr '[:upper:]' '[:lower:]')"
    if [[ "$state" != "running" ]]; then
        nf_log_fail "$scope" "Container '$container' is not running. Run: $hint"
    fi
}
