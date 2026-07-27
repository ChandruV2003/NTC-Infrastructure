#!/bin/sh
set -eu

PKI_DIR=/state/pki
CLIENT_DIR=/state/clients
CLIENT_NAME="${MIXER_TUNNEL_CLIENT_NAME:-ntc-mixpad-mac}"
SERVER_IP="${MIXER_TUNNEL_SERVER_TAILSCALE_IP:?}"
SERVER_PORT="${MIXER_TUNNEL_PORT:-2443}"
TARGET_IP="${MIXER_TUNNEL_TARGET_IP:?}"
OUTPUT="$CLIENT_DIR/$CLIENT_NAME.ovpn"

case "$CLIENT_NAME" in
    *[!a-zA-Z0-9_.-]*|"")
        echo "Client name may contain only letters, numbers, dot, underscore, and dash." >&2
        exit 1
        ;;
esac

case "$SERVER_IP" in
    *[!a-zA-Z0-9.:-]*|"")
        echo "Server address contains an unsupported value: $SERVER_IP" >&2
        exit 1
        ;;
esac

case "$SERVER_PORT" in
    *[!0-9]*|"")
        echo "Server port contains an unsupported value: $SERVER_PORT" >&2
        exit 1
        ;;
esac

case "$TARGET_IP" in
    *[!0-9.]*|""|*.*.*.*.*)
        echo "Target address contains an unsupported value: $TARGET_IP" >&2
        exit 1
        ;;
esac

for path in \
    "$PKI_DIR/ca.crt" \
    "$PKI_DIR/issued/$CLIENT_NAME.crt" \
    "$PKI_DIR/private/$CLIENT_NAME.key" \
    "$PKI_DIR/tls-crypt.key"; do
    if [ ! -s "$path" ]; then
        echo "Missing client PKI file: $path" >&2
        exit 1
    fi
done

install -d -m 0700 "$CLIENT_DIR"
umask 077

{
    printf '%s\n' \
        "client" \
        "dev tun" \
        "proto tcp-client" \
        "remote $SERVER_IP $SERVER_PORT" \
        "nobind" \
        "resolv-retry infinite" \
        "connect-retry 2 30" \
        "connect-retry-max unlimited" \
        "persist-key" \
        "persist-tun" \
        "route-nopull" \
        "route $TARGET_IP 255.255.255.255" \
        "remote-cert-tls server" \
        "auth-nocache" \
        "tls-version-min 1.2" \
        "data-ciphers AES-256-GCM:CHACHA20-POLY1305:AES-128-GCM" \
        "ping 5" \
        "ping-restart 30" \
        "verb 3" \
        "<ca>"
    sed -n '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/p' "$PKI_DIR/ca.crt"
    printf '%s\n' "</ca>" "<cert>"
    sed -n '/-----BEGIN CERTIFICATE-----/,/-----END CERTIFICATE-----/p' \
        "$PKI_DIR/issued/$CLIENT_NAME.crt"
    printf '%s\n' "</cert>" "<key>"
    sed -n '/-----BEGIN PRIVATE KEY-----/,/-----END PRIVATE KEY-----/p' \
        "$PKI_DIR/private/$CLIENT_NAME.key"
    printf '%s\n' "</key>" "<tls-crypt>"
    cat "$PKI_DIR/tls-crypt.key"
    printf '%s\n' "</tls-crypt>"
} > "$OUTPUT"

chmod 0600 "$OUTPUT"
echo "Wrote $OUTPUT"
