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

require_address MIXER_TUNNEL_VPN_NETWORK "${MIXER_TUNNEL_VPN_NETWORK:?}"
require_address MIXER_TUNNEL_VPN_NETMASK "${MIXER_TUNNEL_VPN_NETMASK:?}"
require_address MIXER_TUNNEL_VPN_CIDR "${MIXER_TUNNEL_VPN_CIDR:?}"
require_address MIXER_TUNNEL_LAN_NETWORK "${MIXER_TUNNEL_LAN_NETWORK:?}"
require_address MIXER_TUNNEL_LAN_NETMASK "${MIXER_TUNNEL_LAN_NETMASK:?}"
require_address MIXER_TUNNEL_LAN_CIDR "${MIXER_TUNNEL_LAN_CIDR:?}"

install -d -m 0700 "$RUNTIME_DIR"
sed \
    -e "s|@VPN_NETWORK@|$MIXER_TUNNEL_VPN_NETWORK|g" \
    -e "s|@VPN_NETMASK@|$MIXER_TUNNEL_VPN_NETMASK|g" \
    "$TEMPLATE" > "$CONFIG"

iptables -C FORWARD -i tun0 -d "$MIXER_TUNNEL_LAN_CIDR" -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -i tun0 -d "$MIXER_TUNNEL_LAN_CIDR" -j ACCEPT
iptables -C FORWARD -s "$MIXER_TUNNEL_LAN_CIDR" -o tun0 \
    -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null ||
    iptables -A FORWARD -s "$MIXER_TUNNEL_LAN_CIDR" -o tun0 \
        -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -C FORWARD -i tun0 -j DROP 2>/dev/null ||
    iptables -A FORWARD -i tun0 -j DROP
iptables -t nat -C POSTROUTING -s "$MIXER_TUNNEL_VPN_CIDR" \
    -d "$MIXER_TUNNEL_LAN_CIDR" -j MASQUERADE 2>/dev/null ||
    iptables -t nat -A POSTROUTING -s "$MIXER_TUNNEL_VPN_CIDR" \
        -d "$MIXER_TUNNEL_LAN_CIDR" -j MASQUERADE

exec openvpn --config "$CONFIG"
