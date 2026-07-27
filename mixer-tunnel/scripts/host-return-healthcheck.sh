#!/bin/sh
set -eu

RULE_COMMENT=ntc-mixer-tunnel-return

ip route show "$MIXER_TUNNEL_VPN_CIDR" |
    grep -Fq "via $MIXER_TUNNEL_CONTAINER_IP "
iptables -t nat -C PREROUTING \
    -i "$MIXER_TUNNEL_LAN_INTERFACE" \
    -s "$MIXER_TUNNEL_TARGET_IP/32" \
    -d "$MIXER_TUNNEL_LAN_ADDRESS/32" \
    -p udp \
    --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
    -m comment --comment "$RULE_COMMENT" \
    -j DNAT --to-destination "$MIXER_TUNNEL_CLIENT_IP"
iptables -C FORWARD \
    -i "$MIXER_TUNNEL_LAN_INTERFACE" \
    -s "$MIXER_TUNNEL_TARGET_IP/32" \
    -d "$MIXER_TUNNEL_CLIENT_IP/32" \
    -p udp \
    --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
    -m comment --comment "$RULE_COMMENT" \
    -j ACCEPT
