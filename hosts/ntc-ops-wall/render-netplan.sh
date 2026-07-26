#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/netplan/01-ntc-ops-wall.yaml.template"
CONTROL_INTERFACE=""
DANTE_INTERFACE=""
CONTROL_ADDRESS="192.168.10.90/24"
CONTROL_GATEWAY="192.168.10.1"
CONTROL_DNS="192.168.10.1"
DANTE_ADDRESS="192.168.70.90/24"
OUTPUT="-"
APPLY=0

usage() {
  cat <<'EOF'
Usage: render-netplan.sh --control-interface NAME --dante-interface NAME [options]

Options:
  --control-address CIDR   Default: 192.168.10.90/24
  --control-gateway IP     Default: 192.168.10.1
  --control-dns IP         Default: 192.168.10.1
  --dante-address CIDR     Default: 192.168.70.90/24
  --output PATH            Default: stdout
  --apply                  Allow writing only to /etc/netplan/*.yaml
  --help
EOF
}

valid_interface() {
  [[ "$1" =~ ^[a-zA-Z0-9_.:-]+$ ]]
}

valid_ipv4() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

valid_cidr() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]
}

while (($#)); do
  case "$1" in
    --control-interface) CONTROL_INTERFACE="${2:?missing value}"; shift 2 ;;
    --dante-interface) DANTE_INTERFACE="${2:?missing value}"; shift 2 ;;
    --control-address) CONTROL_ADDRESS="${2:?missing value}"; shift 2 ;;
    --control-gateway) CONTROL_GATEWAY="${2:?missing value}"; shift 2 ;;
    --control-dns) CONTROL_DNS="${2:?missing value}"; shift 2 ;;
    --dante-address) DANTE_ADDRESS="${2:?missing value}"; shift 2 ;;
    --output) OUTPUT="${2:?missing value}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$CONTROL_INTERFACE" && -n "$DANTE_INTERFACE" ]] || {
  printf 'Both interface names are required.\n' >&2
  exit 2
}
[[ "$CONTROL_INTERFACE" != "$DANTE_INTERFACE" ]] || {
  printf 'Control and Dante interfaces must be different.\n' >&2
  exit 2
}
valid_interface "$CONTROL_INTERFACE" && valid_interface "$DANTE_INTERFACE" || {
  printf 'Invalid interface name.\n' >&2
  exit 2
}
valid_cidr "$CONTROL_ADDRESS" && valid_cidr "$DANTE_ADDRESS" || {
  printf 'Invalid CIDR address.\n' >&2
  exit 2
}
valid_ipv4 "$CONTROL_GATEWAY" && valid_ipv4 "$CONTROL_DNS" || {
  printf 'Invalid control gateway or DNS address.\n' >&2
  exit 2
}

rendered="$(
  sed \
    -e "s|__CONTROL_INTERFACE__|$CONTROL_INTERFACE|g" \
    -e "s|__DANTE_INTERFACE__|$DANTE_INTERFACE|g" \
    -e "s|__CONTROL_ADDRESS__|$CONTROL_ADDRESS|g" \
    -e "s|__CONTROL_GATEWAY__|$CONTROL_GATEWAY|g" \
    -e "s|__CONTROL_DNS__|$CONTROL_DNS|g" \
    -e "s|__DANTE_ADDRESS__|$DANTE_ADDRESS|g" \
    "$TEMPLATE"
)"

if [[ "$OUTPUT" == "-" ]]; then
  printf '%s\n' "$rendered"
  exit 0
fi

if ((APPLY)); then
  [[ "$EUID" -eq 0 ]] || {
    printf -- '--apply requires root.\n' >&2
    exit 1
  }
  [[ "$OUTPUT" == /etc/netplan/*.yaml ]] || {
    printf -- '--apply may write only to /etc/netplan/*.yaml.\n' >&2
    exit 1
  }
  printf '%s\n' "$rendered" >"$OUTPUT"
  chmod 0600 "$OUTPUT"
  netplan generate
else
  printf '%s\n' "$rendered" >"$OUTPUT"
  printf 'Rendered %s for review; no network changes were applied.\n' "$OUTPUT"
fi
