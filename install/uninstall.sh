#!/usr/bin/env bash
set -euo pipefail

SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

systemctl disable --now nightfall-photo-ingress.timer 2>/dev/null || true
systemctl disable --now nightfall-photo-ingress-trash.path 2>/dev/null || true
rm -f "$SYSTEMD_DIR/nightfall-photo-ingress.service"
rm -f "$SYSTEMD_DIR/nightfall-photo-ingress.timer"
rm -f "$SYSTEMD_DIR/nightfall-photo-ingress-trash.path"
rm -f "$SYSTEMD_DIR/nightfall-photo-ingress-trash.service"
systemctl daemon-reload
