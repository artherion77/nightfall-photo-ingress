#!/usr/bin/env bash
# govctl-preflights.sh — Reusable preflight check predicates for govctl.
#
# SOURCE this file; do not execute it directly.
#
# Each check function returns exit 0 (pass) or exit 1 (fail).
# On failure it prints a one-line reason string to stdout.
#
# The dispatch entry point is:
#   govctl_run_preflight <check-string>
# where <check-string> is one of the built-in check names (see §6.1 of the
# build-governor design doc), optionally followed by a colon-delimited param:
#   e.g.  container-running:dev-photo-ingress
#         snapshot-exists:dev-photo-ingress/base
#         stack-drift-free:webui

# Resolve paths relative to this file's location at source time.
_GOVCTL_PF_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOVCTL_PREFLIGHTS_PROJECT_ROOT="$(cd "$_GOVCTL_PF_SCRIPT_DIR/../.." && pwd)"
_GOVCTL_MANIFEST_HASH_PY="$_GOVCTL_PF_SCRIPT_DIR/manifest_hash.py"
_GOVCTL_PACKAGE_META_PY="$_GOVCTL_PF_SCRIPT_DIR/package_meta.py"

# Overridable dev container name; matches devctl's CONTAINER variable.
GOVCTL_DEV_CONTAINER="${GOVCTL_DEV_CONTAINER:-dev-photo-ingress}"

# Cache device names — must match the names in devctl.
_GOVCTL_CACHE_DEVICE_NPM_HOME="cache-root-npm-home"
_GOVCTL_CACHE_DEVICE_NPM="cache-root-cache-npm"
_GOVCTL_CACHE_DEVICE_PIP="cache-root-cache-pip"
_GOVCTL_CACHE_DEVICE_PLAYWRIGHT="cache-root-cache-playwright"


# ── container-exists:<name> ───────────────────────────────────────────────────
# Passes if `lxc info <name>` exits 0.

_preflight_container_exists() {
    local name="$1"
    if lxc info "$name" &>/dev/null; then
        return 0
    fi
    echo "container-exists: container '$name' does not exist"
    return 1
}


# ── container-running:<name> ──────────────────────────────────────────────────
# Passes if the container's status is RUNNING according to `lxc list`.

_preflight_container_running() {
    local name="$1"
    local state
    state="$(lxc list "$name" -c s --format csv 2>/dev/null | head -n 1 | tr '[:upper:]' '[:lower:]')"
    if [[ "$state" == "running" ]]; then
        return 0
    fi
    echo "container-running: container '$name' is ${state:-not found} (expected: running)"
    return 1
}


# ── snapshot-exists:<container>/<snap> ────────────────────────────────────────
# Passes if `lxc info <container>/<snap>` exits 0 (LXC snapshot reference).

_preflight_snapshot_exists() {
    local param="$1"
    local container="${param%%/*}"
    local snap="${param#*/}"
    if lxc info "$container/$snap" &>/dev/null; then
        return 0
    fi
    echo "snapshot-exists: snapshot '$snap' not found on container '$container'"
    return 1
}


# ── cache-mounts-active ───────────────────────────────────────────────────────
# Passes if all 4 bind-mount cache devices are attached to GOVCTL_DEV_CONTAINER.

_preflight_cache_mounts_active() {
    local devices
    devices="$(lxc config device list "$GOVCTL_DEV_CONTAINER" 2>/dev/null)" || {
        echo "cache-mounts-active: cannot list devices on '$GOVCTL_DEV_CONTAINER'"
        return 1
    }
    local missing=()
    local dev
    for dev in \
        "$_GOVCTL_CACHE_DEVICE_NPM_HOME" \
        "$_GOVCTL_CACHE_DEVICE_NPM" \
        "$_GOVCTL_CACHE_DEVICE_PIP" \
        "$_GOVCTL_CACHE_DEVICE_PLAYWRIGHT"
    do
        if ! printf '%s\n' "$devices" | grep -qxF "$dev"; then
            missing+=("$dev")
        fi
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        return 0
    fi
    echo "cache-mounts-active: missing cache devices: ${missing[*]}"
    return 1
}


# ── stack-drift-free:<stack> ──────────────────────────────────────────────────
# Passes if the host manifest hash matches the stored container hash.
# <stack> must be "webui" or "dashboard".
# This is a read-only check; it never installs or reinstalls anything.

_preflight_stack_drift_free() {
    local stack="$1"
    local stack_dir container_hash_file

    case "$stack" in
        webui)
            stack_dir="$GOVCTL_PREFLIGHTS_PROJECT_ROOT/webui"
            container_hash_file="/opt/nightfall-manifest/webui.hash"
            ;;
        dashboard)
            stack_dir="$GOVCTL_PREFLIGHTS_PROJECT_ROOT/metrics/dashboard"
            container_hash_file="/opt/nightfall-manifest/dashboard.hash"
            ;;
        *)
            echo "stack-drift-free: unknown stack '$stack' (expected: webui or dashboard)"
            return 1
            ;;
    esac

    if [[ ! -f "$stack_dir/package.json" || ! -f "$stack_dir/package-lock.json" ]]; then
        echo "stack-drift-free: missing package.json or package-lock.json in $stack_dir"
        return 1
    fi

    local host_hash container_hash
    host_hash="$(python3 "$_GOVCTL_MANIFEST_HASH_PY" compute "$stack_dir" 2>/dev/null)" || {
        echo "stack-drift-free: failed to compute host manifest hash for $stack"
        return 1
    }
    container_hash="$(lxc exec "$GOVCTL_DEV_CONTAINER" -- \
        bash -c "cat '$container_hash_file' 2>/dev/null | tr -d '[:space:]' || true" \
        2>/dev/null)" || {
        echo "stack-drift-free: cannot exec in container '$GOVCTL_DEV_CONTAINER'"
        return 1
    }

    local tmp_hash_file
    tmp_hash_file="$(mktemp)"
    printf '%s\n' "$container_hash" > "$tmp_hash_file"
    if python3 "$_GOVCTL_MANIFEST_HASH_PY" compare "$stack_dir" "$tmp_hash_file" >/dev/null 2>&1; then
        rm -f "$tmp_hash_file"
        return 0
    fi
    rm -f "$tmp_hash_file"
    echo "stack-drift-free: $stack manifest drift (host=${host_hash} container=${container_hash:-MISSING})"
    return 1
}


# ── node-version-match ────────────────────────────────────────────────────────
# Passes if the container's `node --version` output matches the version pinned
# in .nvmrc or .node-version at the project root.

_preflight_node_version_match() {
    local pinned_version
    pinned_version="$(python3 "$_GOVCTL_PACKAGE_META_PY" node-version "$GOVCTL_PREFLIGHTS_PROJECT_ROOT" 2>/dev/null || true)"
    if [[ -z "$pinned_version" ]]; then
        echo "node-version-match: no .nvmrc or .node-version found in project root"
        return 1
    fi

    local container_version
    container_version="$(lxc exec "$GOVCTL_DEV_CONTAINER" -- \
        node --version 2>/dev/null | tr -d '[:space:]')" || {
        echo "node-version-match: cannot query node --version in container '$GOVCTL_DEV_CONTAINER'"
        return 1
    }
    container_version="${container_version#v}"

    if [[ "$container_version" == "$pinned_version"* ]]; then
        return 0
    fi
    echo "node-version-match: container has node $container_version, pinned to $pinned_version"
    return 1
}


# ── venv-exists:<path> ────────────────────────────────────────────────────────
# Passes if the directory at <path> exists inside GOVCTL_DEV_CONTAINER.

_preflight_venv_exists() {
    local path="$1"
    if lxc exec "$GOVCTL_DEV_CONTAINER" -- test -d "$path" 2>/dev/null; then
        return 0
    fi
    echo "venv-exists: directory '$path' does not exist in container '$GOVCTL_DEV_CONTAINER'"
    return 1
}


# ── wheel-exists ──────────────────────────────────────────────────────────────
# Passes if at least one .whl file is present in the project's dist/ directory.

_preflight_wheel_exists() {
    if ls "$GOVCTL_PREFLIGHTS_PROJECT_ROOT/dist/"*.whl &>/dev/null; then
        return 0
    fi
    echo "wheel-exists: no .whl files found in $GOVCTL_PREFLIGHTS_PROJECT_ROOT/dist/"
    return 1
}


# ── bridge-network:<bridge> ───────────────────────────────────────────────────
# Passes if the named bridge appears in the device config of GOVCTL_DEV_CONTAINER.

_preflight_bridge_network() {
    local bridge="$1"
    local devices
    devices="$(lxc config device show "$GOVCTL_DEV_CONTAINER" 2>/dev/null)" || {
        echo "bridge-network: cannot show devices for container '$GOVCTL_DEV_CONTAINER'"
        return 1
    }
    if printf '%s\n' "$devices" | grep -qF "$bridge"; then
        return 0
    fi
    echo "bridge-network: bridge '$bridge' not found in device config for '$GOVCTL_DEV_CONTAINER'"
    return 1
}


# ── Dispatch ──────────────────────────────────────────────────────────────────
# govctl_run_preflight <check-string>
#
# Parses the check name (and optional colon-delimited param) and routes to the
# matching check function.  Returns 0 on pass, 1 on fail; on failure the
# reason string is already on stdout from the called function.

govctl_run_preflight() {
    local check_string="$1"
    local check_name check_param

    check_name="${check_string%%:*}"
    if [[ "$check_string" == *:* ]]; then
        check_param="${check_string#*:}"
    else
        check_param=""
    fi

    case "$check_name" in
        container-exists)    _preflight_container_exists    "$check_param" ;;
        container-running)   _preflight_container_running   "$check_param" ;;
        snapshot-exists)     _preflight_snapshot_exists     "$check_param" ;;
        cache-mounts-active) _preflight_cache_mounts_active ;;
        stack-drift-free)    _preflight_stack_drift_free    "$check_param" ;;
        node-version-match)  _preflight_node_version_match ;;
        venv-exists)         _preflight_venv_exists         "$check_param" ;;
        wheel-exists)        _preflight_wheel_exists ;;
        bridge-network)      _preflight_bridge_network      "$check_param" ;;
        *)
            echo "govctl_run_preflight: unknown check '$check_name'"
            return 1
            ;;
    esac
}
