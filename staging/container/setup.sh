#!/usr/bin/env bash
# container/setup.sh — bootstraps the staging-photo-ingress LXC container.
# Runs exactly once, pushed + executed by "stagingctl create".

set -euo pipefail

VENV_ROOT="/opt/ingress"
STAGING_VOLATILE="${STAGING_VOLATILE:-0}"

echo "[setup] Installing system packages ..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ca-certificates curl

echo "[setup] Creating application directories ..."
mkdir -p /etc/nightfall
mkdir -p /var/lib/ingress/{staging,pending,accepted,rejected,trash,evidence,tokens,cursors,hashes}
mkdir -p /var/log/nightfall
mkdir -p /var/cache/nightfall-photo-ingress
mkdir -p /run/nightfall-status.d

if [[ "$STAGING_VOLATILE" == "1" ]]; then
    echo "[setup] Preparing volatile runtime directories under /run/staging-photo-ingress ..."
    mkdir -p /run/staging-photo-ingress/{evidence,logs}
fi

echo "[setup] Creating Python venv at $VENV_ROOT ..."
python3 -m venv "$VENV_ROOT"
"$VENV_ROOT/bin/pip" install --quiet --upgrade pip

echo "[setup] Done."
