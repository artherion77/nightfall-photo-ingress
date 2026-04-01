#!/usr/bin/env bash
set -euo pipefail

PREFIX="${PREFIX:-/opt/nightfall-photo-ingress}"
CONF_DIR="${CONF_DIR:-/etc/nightfall}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

mkdir -p "$PREFIX/bin" "$CONF_DIR" "$SYSTEMD_DIR"
python3 -m pip install --upgrade .
install -m 0644 conf/photo-ingress.conf.example "$CONF_DIR/photo-ingress.conf"
install -m 0644 systemd/nightfall-photo-ingress.service "$SYSTEMD_DIR/nightfall-photo-ingress.service"
install -m 0644 systemd/nightfall-photo-ingress.timer "$SYSTEMD_DIR/nightfall-photo-ingress.timer"
install -m 0644 systemd/nightfall-photo-ingress-trash.path "$SYSTEMD_DIR/nightfall-photo-ingress-trash.path"
install -m 0644 systemd/nightfall-photo-ingress-trash.service "$SYSTEMD_DIR/nightfall-photo-ingress-trash.service"
systemctl daemon-reload
systemctl enable --now nightfall-photo-ingress.timer
systemctl enable nightfall-photo-ingress-trash.path
