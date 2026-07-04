#!/usr/bin/env sh
set -eu

INFRA_ROOT="${INFRA_ROOT:-/root/NTC-Infrastructure}"
RUNTIME_AES67_DIR="${RUNTIME_AES67_DIR:-/root/NTC-Runtime/dante/aes67}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

install -d "$RUNTIME_AES67_DIR"
install -m 0644 "$INFRA_ROOT/dante/aes67/room-a-stream-lr.sdp" "$RUNTIME_AES67_DIR/room-a.sdp"
install -m 0644 "$INFRA_ROOT/dante/aes67/room-b-stream-lr.sdp" "$RUNTIME_AES67_DIR/room-b.sdp"
install -m 0644 "$INFRA_ROOT/dante/aes67/qsys-ntc-lr.sdp" "$RUNTIME_AES67_DIR/qsys-ntc-lr.sdp"

install -d "$SYSTEMD_DIR/ntc-mixassist.service.d"
install -m 0644 "$INFRA_ROOT/systemd/ntc-mixassist.service.d/source-label.conf" "$SYSTEMD_DIR/ntc-mixassist.service.d/source-label.conf"
install -m 0644 "$INFRA_ROOT/systemd/ntc-mixassist-aes67.service" "$SYSTEMD_DIR/ntc-mixassist-aes67.service"
systemctl daemon-reload
