#!/bin/sh
set -eu

TEMPLATE=/opt/mixer-tunnel/server.conf.template
RUNTIME_DIR=/state/runtime
CONFIG="$RUNTIME_DIR/server.conf"

required_files="
/state/pki/ca.crt
/state/pki/issued/server.crt
/state/pki/private/server.key
/state/pki/crl.pem
/state/pki/tls-crypt.key
"

for path in $required_files; do
    if [ ! -s "$path" ]; then
        echo "Missing PKI file: $path" >&2
        echo "Stage the server-only PKI bundle before starting the tunnel." >&2
        exit 1
    fi
done

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

require_address MIXER_TUNNEL_VPN_NETWORK "${MIXER_TUNNEL_VPN_NETWORK:?}"
require_address MIXER_TUNNEL_VPN_NETMASK "${MIXER_TUNNEL_VPN_NETMASK:?}"
require_address MIXER_TUNNEL_VPN_CIDR "${MIXER_TUNNEL_VPN_CIDR:?}"
require_address MIXER_TUNNEL_LAN_NETWORK "${MIXER_TUNNEL_LAN_NETWORK:?}"
require_address MIXER_TUNNEL_LAN_NETMASK "${MIXER_TUNNEL_LAN_NETMASK:?}"
require_address MIXER_TUNNEL_LAN_CIDR "${MIXER_TUNNEL_LAN_CIDR:?}"
require_address MIXER_TUNNEL_TARGET_IP "${MIXER_TUNNEL_TARGET_IP:?}"
require_address MIXER_TUNNEL_CLIENT_IP "${MIXER_TUNNEL_CLIENT_IP:?}"
validate_unit MIXER_TUNNEL_QOS_RATE "${MIXER_TUNNEL_QOS_RATE:?}" mbit
validate_unit MIXER_TUNNEL_QOS_BURST "${MIXER_TUNNEL_QOS_BURST:?}" kb
validate_unit MIXER_TUNNEL_QOS_LATENCY "${MIXER_TUNNEL_QOS_LATENCY:?}" ms

case "${MIXER_TUNNEL_CLIENT_NAME:?}" in
    *[!A-Za-z0-9_.-]*|"")
        echo "MIXER_TUNNEL_CLIENT_NAME contains an unsupported value" >&2
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

install -d -m 0700 "$RUNTIME_DIR"
install -d -m 0700 "$RUNTIME_DIR/ccd"
printf 'ifconfig-push %s %s\n' \
    "$MIXER_TUNNEL_CLIENT_IP" "$MIXER_TUNNEL_VPN_NETMASK" \
    > "$RUNTIME_DIR/ccd/$MIXER_TUNNEL_CLIENT_NAME"
sed \
    -e "s|@VPN_NETWORK@|$MIXER_TUNNEL_VPN_NETWORK|g" \
    -e "s|@VPN_NETMASK@|$MIXER_TUNNEL_VPN_NETMASK|g" \
    -e "s|@QOS_RATE@|$MIXER_TUNNEL_QOS_RATE|g" \
    -e "s|@QOS_BURST@|$MIXER_TUNNEL_QOS_BURST|g" \
    -e "s|@QOS_LATENCY@|$MIXER_TUNNEL_QOS_LATENCY|g" \
    -e "s|@TARGET_IP@|$MIXER_TUNNEL_TARGET_IP|g" \
    -e "s|@CLIENT_IP@|$MIXER_TUNNEL_CLIENT_IP|g" \
    "$TEMPLATE" > "$CONFIG"

iptables -C FORWARD -i tun0 -d "$MIXER_TUNNEL_LAN_CIDR" -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -i tun0 -d "$MIXER_TUNNEL_LAN_CIDR" -j ACCEPT
iptables -C FORWARD -s "$MIXER_TUNNEL_LAN_CIDR" -o tun0 \
    -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -s "$MIXER_TUNNEL_LAN_CIDR" -o tun0 \
        -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -C FORWARD -i eth0 -o tun0 \
    -s "$MIXER_TUNNEL_TARGET_IP/32" -d "$MIXER_TUNNEL_CLIENT_IP/32" \
    -p udp --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
    -j ACCEPT 2>/dev/null ||
    iptables -I FORWARD 1 -i eth0 -o tun0 \
        -s "$MIXER_TUNNEL_TARGET_IP/32" -d "$MIXER_TUNNEL_CLIENT_IP/32" \
        -p udp --sport "$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_START:$MIXER_TUNNEL_RETURN_UDP_SOURCE_PORT_END" \
        -j ACCEPT
iptables -C FORWARD -i tun0 -j DROP 2>/dev/null ||
    iptables -A FORWARD -i tun0 -j DROP
iptables -t nat -C POSTROUTING -s "$MIXER_TUNNEL_VPN_CIDR" \
    -d "$MIXER_TUNNEL_LAN_CIDR" -j MASQUERADE 2>/dev/null ||
    iptables -t nat -A POSTROUTING -s "$MIXER_TUNNEL_VPN_CIDR" \
        -d "$MIXER_TUNNEL_LAN_CIDR" -j MASQUERADE

exec openvpn --config "$CONFIG"
