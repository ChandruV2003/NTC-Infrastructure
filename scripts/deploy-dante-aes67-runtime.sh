#!/usr/bin/env sh
set -eu

INFRA_ROOT="${INFRA_ROOT:-/root/NTC-Infrastructure}"
RUNTIME_AES67_DIR="${RUNTIME_AES67_DIR:-/root/NTC-Runtime/dante/aes67}"

install -d "$RUNTIME_AES67_DIR"
install -m 0644 "$INFRA_ROOT/dante/aes67/room-a-stream-lr.sdp" "$RUNTIME_AES67_DIR/room-a.sdp"
install -m 0644 "$INFRA_ROOT/dante/aes67/room-b-stream-lr.sdp" "$RUNTIME_AES67_DIR/room-b.sdp"
install -m 0644 "$INFRA_ROOT/dante/aes67/qsys-ntc-lr.sdp" "$RUNTIME_AES67_DIR/qsys-ntc-lr.sdp"
