#!/usr/bin/env bash
# Shared deterministic helpers for devctl stack lifecycle and drift checks.

set -euo pipefail

MANIFEST_DIR="/opt/nightfall-manifest"
REPO_LOCK_FILE="${REPO_LOCK_FILE:-/tmp/nightfall-repo.lock}"
REPO_LOCK_TIMEOUT_SEC="${REPO_LOCK_TIMEOUT_SEC:-300}"

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

read_hash_file() {
    local path="$1"
    tr -d '[:space:]' < "$path"
}

compare_manifest_hash() {
    local host_hash_file="$1"
    local container_hash_file="$2"

    local host_hash
    local container_hash
    host_hash="$(read_hash_file "$host_hash_file")"
    container_hash="$(read_hash_file "$container_hash_file")"
    [[ "$host_hash" == "$container_hash" ]]
}

acquire_repo_lock() {
    exec 200>"$REPO_LOCK_FILE"
    flock -w "$REPO_LOCK_TIMEOUT_SEC" 200 || {
        echo "[devctl] Timed out waiting for global repo lock ($REPO_LOCK_FILE)" >&2
        exit 1
    }
}

release_repo_lock() {
    flock -u 200
    exec 200>&-
}

get_node_version() {
    local raw=""
    if [[ -f "$PROJECT_ROOT/.nvmrc" ]]; then
        raw="$(tr -d '[:space:]' < "$PROJECT_ROOT/.nvmrc")"
    elif [[ -f "$PROJECT_ROOT/.node-version" ]]; then
        raw="$(tr -d '[:space:]' < "$PROJECT_ROOT/.node-version")"
    fi

    raw="${raw#v}"
    if [[ -n "$raw" ]]; then
        printf "%s" "$raw"
    fi
}

extract_major_from_semver() {
    local value="$1"
    value="${value#^}"
    value="${value#~}"
    value="${value#>=}"
    value="${value#>}"
    value="${value#<=}"
    value="${value#<}"
    value="${value%%.*}"
    value="${value%%-*}"
    printf "%s" "$value"
}

_json_dependency_version() {
    local package_file="$1"
    local dep_name="$2"
    python3 - <<'PY' "$package_file" "$dep_name"
import json
import sys
from pathlib import Path

pkg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
dep = sys.argv[2]
dev_deps = pkg.get("devDependencies", {})
print(dev_deps.get(dep, ""))
PY
}

assert_web_stack_major_consistency() {
    local web_pkg="$PROJECT_ROOT/webui/package.json"
    local dashboard_pkg="$PROJECT_ROOT/metrics/dashboard/package.json"

    [[ -f "$web_pkg" ]] || { echo "Missing $web_pkg" >&2; return 1; }
    [[ -f "$dashboard_pkg" ]] || { echo "Missing $dashboard_pkg" >&2; return 1; }

    local web_kit web_vite dash_kit dash_vite
    web_kit="$(_json_dependency_version "$web_pkg" "@sveltejs/kit")"
    web_vite="$(_json_dependency_version "$web_pkg" "vite")"
    dash_kit="$(_json_dependency_version "$dashboard_pkg" "@sveltejs/kit")"
    dash_vite="$(_json_dependency_version "$dashboard_pkg" "vite")"

    local web_kit_major web_vite_major dash_kit_major dash_vite_major
    web_kit_major="$(extract_major_from_semver "$web_kit")"
    web_vite_major="$(extract_major_from_semver "$web_vite")"
    dash_kit_major="$(extract_major_from_semver "$dash_kit")"
    dash_vite_major="$(extract_major_from_semver "$dash_vite")"

    [[ -n "$web_kit_major" && -n "$web_vite_major" && -n "$dash_kit_major" && -n "$dash_vite_major" ]] || {
        echo "Unable to derive SvelteKit/Vite majors from package manifests" >&2
        return 1
    }

    [[ "$web_kit_major" == "$dash_kit_major" ]] || {
        echo "SvelteKit major mismatch: webui=$web_kit_major dashboard=$dash_kit_major" >&2
        return 1
    }

    [[ "$web_vite_major" == "$dash_vite_major" ]] || {
        echo "Vite major mismatch: webui=$web_vite_major dashboard=$dash_vite_major" >&2
        return 1
    }
}
