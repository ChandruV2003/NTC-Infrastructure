#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

bash -n "$SCRIPT_DIR/install.sh"
bash -n "$SCRIPT_DIR/render-netplan.sh"
bash -n "$SCRIPT_DIR/bin/ntc-ops-burn-in"
bash -n "$SCRIPT_DIR/bin/ntc-ops-host-report"
bash -n "$SCRIPT_DIR/bin/ntc-ops-wall-kiosk"

"$SCRIPT_DIR/install.sh" >"$TEMP_DIR/install-plan.txt"
grep -q 'Dry run only' "$TEMP_DIR/install-plan.txt"
grep -q 'Network configuration is intentionally not applied' "$TEMP_DIR/install-plan.txt"

"$SCRIPT_DIR/render-netplan.sh" \
  --control-interface enp3s0 \
  --dante-interface enp4s0 \
  --output "$TEMP_DIR/netplan.yaml" >/dev/null

grep -q 'enp3s0:' "$TEMP_DIR/netplan.yaml"
grep -q '192.168.10.90/24' "$TEMP_DIR/netplan.yaml"
grep -q 'enp4s0:' "$TEMP_DIR/netplan.yaml"
grep -q '192.168.70.90/24' "$TEMP_DIR/netplan.yaml"
[[ "$(grep -c 'to: default' "$TEMP_DIR/netplan.yaml")" -eq 1 ]]

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$SCRIPT_DIR/systemd/ntc-operations@.service"
fi

python3 "$SCRIPT_DIR/test_host_package.py" -v
