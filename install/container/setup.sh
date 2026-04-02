#!/usr/bin/env bash
# container/setup.sh — bootstraps the production photo-ingress LXC container.

set -euo pipefail

VENV_ROOT="${VENV_ROOT:-/opt/nightfall-photo-ingress}"
CONF_DIR="${CONF_DIR:-/etc/nightfall}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
DOC_DIR="${DOC_DIR:-$VENV_ROOT/share/doc/nightfall-photo-ingress}"

echo "[setup] Installing system packages ..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ca-certificates curl

echo "[setup] Creating application directories ..."
mkdir -p "$CONF_DIR"
mkdir -p "$SYSTEMD_DIR"
mkdir -p "$DOC_DIR"
mkdir -p /var/lib/ingress/{staging,accepted,trash,evidence,tokens,cursors}
mkdir -p /var/log/nightfall
mkdir -p /var/cache/nightfall-photo-ingress
mkdir -p /run/nightfall-status.d

if [[ ! -x "$VENV_ROOT/bin/python" ]]; then
    echo "[setup] Creating Python venv at $VENV_ROOT ..."
    python3 -m venv "$VENV_ROOT"
fi

"$VENV_ROOT/bin/pip" install --quiet --upgrade pip

echo "[setup] Done."