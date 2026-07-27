#!/bin/sh
set -eu

validate_unit() {
    name="$1"
    value="$2"
    suffix="$3"
    number="${value%"$suffix"}"

    if [ "$number" = "$value" ]; then
        echo "$name must end in $suffix" >&2
        exit 1
    fi
    case "$number" in
        *[!0-9]*|"")
            echo "$name contains an unsupported value: $value" >&2
            exit 1
            ;;
    esac
}

require_address() {
    name="$1"
    value="$2"
    case "$value" in
        *[!0-9.]*|"")
            echo "$name contains an unsupported value: $value" >&2
            exit 1
            ;;
    esac
}

RATE="${1:?Missing pacing rate}"
BURST="${2:?Missing pacing burst}"
LATENCY="${3:?Missing pacing latency}"
TARGET_IP="${4:?Missing mixer address}"
CLIENT_IP="${5:?Missing VPN client address}"
DEVICE="${6:?Missing tunnel interface}"

case "$DEVICE" in
    *[!A-Za-z0-9_.:-]*|"")
        echo "OpenVPN supplied an unsupported tunnel interface" >&2
        exit 1
        ;;
esac

validate_unit MIXER_TUNNEL_QOS_RATE "$RATE" mbit
validate_unit MIXER_TUNNEL_QOS_BURST "$BURST" kb
validate_unit MIXER_TUNNEL_QOS_LATENCY "$LATENCY" ms
require_address MIXER_TUNNEL_TARGET_IP "$TARGET_IP"
require_address MIXER_TUNNEL_CLIENT_IP "$CLIENT_IP"

tc qdisc del dev "$DEVICE" root 2>/dev/null || true
tc qdisc add dev "$DEVICE" root handle 1: prio \
    bands 2 \
    priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
tc qdisc add dev "$DEVICE" parent 1:2 handle 20: tbf \
    rate "$RATE" \
    burst "$BURST" \
    latency "$LATENCY"
tc filter add dev "$DEVICE" parent 1: protocol ip priority 1 u32 \
    match ip protocol 17 0xff \
    match ip src "$TARGET_IP/32" \
    match ip dst "$CLIENT_IP/32" \
    flowid 1:2
