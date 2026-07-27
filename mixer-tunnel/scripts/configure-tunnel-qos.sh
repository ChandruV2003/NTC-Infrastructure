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

RATE="${1:?Missing pacing rate}"
BURST="${2:?Missing pacing burst}"
LATENCY="${3:?Missing pacing latency}"
DEVICE="${4:?Missing tunnel interface}"

case "$DEVICE" in
    *[!A-Za-z0-9_.:-]*|"")
        echo "OpenVPN supplied an unsupported tunnel interface" >&2
        exit 1
        ;;
esac

validate_unit MIXER_TUNNEL_QOS_RATE "$RATE" mbit
validate_unit MIXER_TUNNEL_QOS_BURST "$BURST" kb
validate_unit MIXER_TUNNEL_QOS_LATENCY "$LATENCY" ms

tc qdisc replace dev "$DEVICE" root tbf \
    rate "$RATE" \
    burst "$BURST" \
    latency "$LATENCY"
