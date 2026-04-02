#!/usr/bin/env bash
set -euo pipefail

echo "[install:photo-ingress] Installing container-managed Nightfall files..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET_CONTAINER="${TARGET_CONTAINER:-${CONTAINER_NAME:-photo-ingress}}"
CONTAINER_IMAGE="${CONTAINER_IMAGE:-ubuntu:24.04}"
LXC_PROFILE="${LXC_PROFILE:-default}"
PREFIX="${PREFIX:-/opt/nightfall-photo-ingress}"
CONF_DIR="${CONF_DIR:-/etc/nightfall}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
DOC_DIR="$PREFIX/share/doc/nightfall-photo-ingress"
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/container/setup.sh"
WHEEL_BUILD_DIR=""

usage() {
	cat <<EOF
Usage: $(basename "$0") [--container NAME] [--image IMAGE] [--profile NAME]

Create or update a production LXC container for nightfall-photo-ingress.

Options:
	--container NAME   Target LXC container (default: photo-ingress)
	--image IMAGE      LXC image to launch when the container is missing (default: ubuntu:24.04)
	--profile NAME     LXC profile to use when launching the container (default: default)
	-h, --help         Show this help

Environment:
	TARGET_CONTAINER   Target LXC container name (default: photo-ingress)
	CONTAINER_IMAGE    LXC image to launch when container is missing (default: ubuntu:24.04)
	LXC_PROFILE        LXC profile to use when launching the container (default: default)
	PREFIX             Container install prefix (default: /opt/nightfall-photo-ingress)
EOF
}

_info() { printf '[install:photo-ingress] %s\n' "$*"; }
_warn() { printf '[install:photo-ingress] WARN: %s\n' "$*" >&2; }
_fail() { printf '[install:photo-ingress] ERROR: %s\n' "$*" >&2; exit 1; }

_require_command() {
	command -v "$1" >/dev/null 2>&1 || _fail "Required command not found: $1"
}

_cleanup() {
	if [[ -n "$WHEEL_BUILD_DIR" && -d "$WHEEL_BUILD_DIR" ]]; then
		rm -rf "$WHEEL_BUILD_DIR"
	fi
}

_container_exists() {
	lxc list -c n --format csv 2>/dev/null | grep -Fxq "$TARGET_CONTAINER"
}

_container_running() {
	lxc info "$TARGET_CONTAINER" 2>/dev/null | grep -Eiq 'Status:[[:space:]]+running'
}

_wait_for_container() {
	local waited=0
	while ! lxc exec "$TARGET_CONTAINER" -- systemctl is-system-running --quiet >/dev/null 2>&1; do
		sleep 2
		waited=$((waited + 2))
		[[ $waited -lt 60 ]] || _fail "Container '$TARGET_CONTAINER' did not become ready within 60 seconds"
	done
}

_ensure_container() {
	if ! _container_exists; then
		_info "Launching LXC container '$TARGET_CONTAINER' from $CONTAINER_IMAGE with profile '$LXC_PROFILE'"
		lxc launch "$CONTAINER_IMAGE" "$TARGET_CONTAINER" -p "$LXC_PROFILE"
	elif ! _container_running; then
		_info "Starting existing LXC container '$TARGET_CONTAINER'"
		lxc start "$TARGET_CONTAINER"
	else
		_info "Using existing running LXC container '$TARGET_CONTAINER'"
	fi

	_wait_for_container

	_info "Bootstrapping container runtime"
	lxc file push "$BOOTSTRAP_SCRIPT" "$TARGET_CONTAINER/tmp/nightfall-photo-ingress-setup.sh"
	lxc exec "$TARGET_CONTAINER" -- env \
		VENV_ROOT="$PREFIX" \
		CONF_DIR="$CONF_DIR" \
		SYSTEMD_DIR="$SYSTEMD_DIR" \
		DOC_DIR="$DOC_DIR" \
		bash /tmp/nightfall-photo-ingress-setup.sh
}

_build_wheel() {
	WHEEL_BUILD_DIR="$(mktemp -d)"
	_info "Building wheel from current working tree"
	python3 -m pip wheel --no-deps --wheel-dir "$WHEEL_BUILD_DIR" "$PROJECT_ROOT" >/dev/null
	ls -t "$WHEEL_BUILD_DIR"/*.whl | head -1
}

_push_systemd_units() {
	_info "Installing systemd units into container"
	lxc file push "$PROJECT_ROOT/systemd/nightfall-photo-ingress.service" \
		"$TARGET_CONTAINER$SYSTEMD_DIR/nightfall-photo-ingress.service"
	lxc file push "$PROJECT_ROOT/systemd/nightfall-photo-ingress.timer" \
		"$TARGET_CONTAINER$SYSTEMD_DIR/nightfall-photo-ingress.timer"
	lxc file push "$PROJECT_ROOT/systemd/nightfall-photo-ingress-trash.path" \
		"$TARGET_CONTAINER$SYSTEMD_DIR/nightfall-photo-ingress-trash.path"
	lxc file push "$PROJECT_ROOT/systemd/nightfall-photo-ingress-trash.service" \
		"$TARGET_CONTAINER$SYSTEMD_DIR/nightfall-photo-ingress-trash.service"
}

_push_docs() {
	_info "Installing operator documentation into container"
	lxc file push "$PROJECT_ROOT/docs/operations-runbook.md" \
		"$TARGET_CONTAINER$DOC_DIR/operations-runbook.md"
}

_push_config_if_missing() {
	if lxc exec "$TARGET_CONTAINER" -- test -f "$CONF_DIR/photo-ingress.conf"; then
		_warn "Config already exists at $CONF_DIR/photo-ingress.conf; leaving it unchanged"
		return
	fi

	_info "Installing example config into container"
	lxc file push "$PROJECT_ROOT/conf/photo-ingress.conf.example" \
		"$TARGET_CONTAINER$CONF_DIR/photo-ingress.conf"
}

_install_wheel() {
	local wheel_path="$1"
	local whl_name
	whl_name="$(basename "$wheel_path")"

	_info "Pushing wheel $whl_name into container"
	lxc file push "$wheel_path" "$TARGET_CONTAINER/tmp/$whl_name"
	_info "Installing wheel into container venv at $PREFIX"
	lxc exec "$TARGET_CONTAINER" -- "$PREFIX/bin/pip" install --quiet --upgrade "/tmp/$whl_name"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--container)
			TARGET_CONTAINER="$2"
			shift 2
			;;
		--image)
			CONTAINER_IMAGE="$2"
			shift 2
			;;
		--profile)
			LXC_PROFILE="$2"
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "[install:photo-ingress] Unknown option: $1" >&2
			usage >&2
			exit 1
			;;
	esac
done

_require_command lxc
_require_command python3
trap _cleanup EXIT

_info "target container: $TARGET_CONTAINER"
_info "launch policy: image=$CONTAINER_IMAGE profile=$LXC_PROFILE"

wheel_path="$(_build_wheel)"
_ensure_container
_push_systemd_units
_push_docs
_push_config_if_missing
_install_wheel "$wheel_path"

_info "Reloading systemd and enabling production units"
lxc exec "$TARGET_CONTAINER" -- systemctl daemon-reload
lxc exec "$TARGET_CONTAINER" -- systemctl enable --now nightfall-photo-ingress.timer
lxc exec "$TARGET_CONTAINER" -- systemctl enable --now nightfall-photo-ingress-trash.path

echo ""
_info "Done."
_info "To inspect the deployed service, run:"
echo "  lxc exec $TARGET_CONTAINER -- systemctl status nightfall-photo-ingress.timer"
echo "  lxc exec $TARGET_CONTAINER -- systemctl status nightfall-photo-ingress-trash.path"
