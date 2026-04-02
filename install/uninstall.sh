#!/usr/bin/env bash
set -euo pipefail

echo "[uninstall:photo-ingress] Removing production LXC container..."

TARGET_CONTAINER="${TARGET_CONTAINER:-${CONTAINER_NAME:-photo-ingress}}"

usage() {
	cat <<EOF
Usage: $(basename "$0") [--container NAME]

Delete the production LXC container for nightfall-photo-ingress.

Options:
	--container NAME   Target LXC container (default: photo-ingress)
	-h, --help         Show this help

Environment:
	TARGET_CONTAINER   Target LXC container name (default: photo-ingress)

NOTE: This removes the entire container, including its installed wheel,
      config, token cache, cursors, and operator documentation.
EOF
}

_info() { printf '[uninstall:photo-ingress] %s\n' "$*"; }
_warn() { printf '[uninstall:photo-ingress] WARN: %s\n' "$*" >&2; }
_fail() { printf '[uninstall:photo-ingress] ERROR: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
	case "$1" in
		--container)
			TARGET_CONTAINER="$2"
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "[uninstall:photo-ingress] Unknown option: $1" >&2
			usage >&2
			exit 1
			;;
	esac
done

command -v lxc >/dev/null 2>&1 || _fail "Required command not found: lxc"

container_exists() {
	lxc list -c n --format csv 2>/dev/null | grep -Fxq "$1"
}

if ! container_exists "$TARGET_CONTAINER"; then
	_fail "container not found: $TARGET_CONTAINER"
fi

_info "target container: $TARGET_CONTAINER"
_info "Deleting LXC container '$TARGET_CONTAINER'"
lxc delete --force "$TARGET_CONTAINER"

echo ""
_info "Done."
