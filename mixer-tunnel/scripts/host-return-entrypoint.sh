#!/bin/sh
set -eu

RULE_COMMENT=ntc-mixer-tunnel-return

require_address() {
    name="$1"
    value="$2"
    case "$value" in
        *[!0-9./]*|"")
            echo "$name contains an unsupported value: $value" >&2
            exit 1
            ;;
    esac
}

require_address MIXER_TUNNEL_VPN_CIDR "${MIXER_TUNNEL_VPN_CIDR:?}"
require_address MIXER_TUNNEL_CLIENT_IP "${MIXER_TUNNEL_CLIENT_IP:?}"
require_address MIXER_TUNNEL_CONTAINER_IP "${MIXER_TUNNEL_CONTAINER_IP:?}"
require_address MIXER_TUNNEL_LAN_ADDRESS "${MIXER_TUNNEL_LAN_ADDRESS:?}"
require_address MIXER_TUNNEL_TARGET_IP "${MIXER_TUNNEL_TARGET_IP:?}"

case "${MIXER_TUNNEL_LAN_INTERFACE:?}" in
    *[!A-Za-z0-9_.:-]*|"")
        echo "MIXER_TUNNEL_LAN_INTERFACE contains an unsupported value" >&2
        exit 1
        ;;
esac

case "${MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:?}" in
    *[!0-9]*|"")
        echo "MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START must be numeric" >&2
        exit 1
        ;;
esac
case "${MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END:?}" in
    *[!0-9]*|"")
        echo "MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END must be numeric" >&2
        exit 1
        ;;
esac
if [ "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START" -lt 1 ] ||
    [ "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" -gt 65535 ] ||
    [ "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START" -gt \
        "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" ]; then
    echo "Mixer return UDP source ports are outside the valid range" >&2
    exit 1
fi

nat_rule() {
    iptables -t nat "$@" PREROUTING \
        -i "$MIXER_TUNNEL_LAN_INTERFACE" \
        -s "$MIXER_TUNNEL_TARGET_IP/32" \
        -d "$MIXER_TUNNEL_LAN_ADDRESS/32" \
        -p udp \
        --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
        -m comment --comment "$RULE_COMMENT" \
        -j DNAT --to-destination "$MIXER_TUNNEL_CLIENT_IP"
}

forward_rule() {
    iptables "$@" FORWARD \
        -i "$MIXER_TUNNEL_LAN_INTERFACE" \
        -s "$MIXER_TUNNEL_TARGET_IP/32" \
        -d "$MIXER_TUNNEL_CLIENT_IP/32" \
        -p udp \
        --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
        -m comment --comment "$RULE_COMMENT" \
        -j ACCEPT
}

cleanup() {
    nat_rule -D 2>/dev/null || true
    forward_rule -D 2>/dev/null || true
    if ip route show "$MIXER_TUNNEL_VPN_CIDR" |
        grep -Fq "via $MIXER_TUNNEL_CONTAINER_IP "; then
        ip route del "$MIXER_TUNNEL_VPN_CIDR" \
            via "$MIXER_TUNNEL_CONTAINER_IP" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap 'exit 0' HUP INT TERM

ip link show "$MIXER_TUNNEL_LAN_INTERFACE" >/dev/null
ip -4 address show dev "$MIXER_TUNNEL_LAN_INTERFACE" |
    grep -Fq " $MIXER_TUNNEL_LAN_ADDRESS/"
ip route get "$MIXER_TUNNEL_CONTAINER_IP" >/dev/null

ip route replace "$MIXER_TUNNEL_VPN_CIDR" \
    via "$MIXER_TUNNEL_CONTAINER_IP"
nat_rule -C 2>/dev/null || nat_rule -I
forward_rule -C 2>/dev/null || forward_rule -I

while sleep 5; do
    :
done
