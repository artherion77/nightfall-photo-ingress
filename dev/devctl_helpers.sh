#!/usr/bin/env bash
# Helper functions for devctl: manifest hashing, drift detection, Node version, and global lock.

set -euo pipefail

MANIFEST_DIR="/opt/nightfall-manifest"
REPO_LOCK_FILE="/tmp/nightfall-repo.lock"

# Compute SHA256 over package.json + package-lock.json for a stack
compute_manifest_hash() {
    local stack_dir="$1"
    local hash_file="$2"
    local pkg_json="$stack_dir/package.json"
    local lock_json="$stack_dir/package-lock.json"
    if [[ ! -f "$pkg_json" || ! -f "$lock_json" ]]; then
        echo "[devctl] Missing manifest files in $stack_dir" >&2
        return 1
    fi
    cat "$pkg_json" "$lock_json" | sha256sum | awk '{print $1}' > "$hash_file"
}

# Compare host and container manifest hashes
compare_manifest_hash() {
    local host_hash_file="$1"
    local container_hash_file="$2"
    local host_hash
    local container_hash
    host_hash=$(cat "$host_hash_file" 2>/dev/null || echo "")
    container_hash=$(cat "$container_hash_file" 2>/dev/null || echo "")
    [[ "$host_hash" == "$container_hash" ]]
}

# Acquire global repo lock
acquire_repo_lock() {
    exec 200>"$REPO_LOCK_FILE"
    flock -w 300 200 || {
        echo "[devctl] Timed out waiting for global repo lock ($REPO_LOCK_FILE)" >&2
        exit 1
    }
}

# Release global repo lock
release_repo_lock() {
    flock -u 200
    exec 200>&-
}

# Read Node version from .nvmrc or .node-version
get_node_version() {
    if [[ -f "$PROJECT_ROOT/.nvmrc" ]]; then
        cat "$PROJECT_ROOT/.nvmrc" | tr -d '\n' | tr -d 'v'
    elif [[ -f "$PROJECT_ROOT/.node-version" ]]; then
        cat "$PROJECT_ROOT/.node-version" | tr -d '\n' | tr -d 'v'
    else
        echo "" # Not found
    fi
}

# Check Node version in container
check_node_version() {
    local required_version="$1"
    local actual_version
    actual_version=$(lxc exec "$CONTAINER" -- node --version 2>/dev/null | tr -d 'v' || echo "")
    [[ "$required_version" == "$actual_version" ]]
}
