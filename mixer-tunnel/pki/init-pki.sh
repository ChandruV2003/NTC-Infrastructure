#!/bin/sh
set -eu

PKI_DIR=/state/pki
SITE_ID="${MIXER_TUNNEL_SITE_ID:-ntc}"
CLIENT_NAME="${MIXER_TUNNEL_CLIENT_NAME:-ntc-mixpad-mac}"
EASYRSA_BIN=/usr/share/easy-rsa/easyrsa

case "$SITE_ID:$CLIENT_NAME" in
    *[!a-zA-Z0-9_.:-]*|"":*)
        echo "Site and client names may contain only letters, numbers, dot, underscore, and dash." >&2
        exit 1
        ;;
esac

if [ -s "$PKI_DIR/ca.crt" ]; then
    echo "PKI already exists at $PKI_DIR; refusing to overwrite it." >&2
    exit 1
fi

if [ ! -x "$EASYRSA_BIN" ]; then
    echo "Easy-RSA was not found at $EASYRSA_BIN." >&2
    exit 1
fi

install -d -m 0700 /state
export EASYRSA_BATCH=1
export EASYRSA_PKI="$PKI_DIR"
export EASYRSA_CRL_DAYS=3650

"$EASYRSA_BIN" init-pki
EASYRSA_REQ_CN="$SITE_ID Mixer Control Tunnel CA" \
    "$EASYRSA_BIN" build-ca nopass
"$EASYRSA_BIN" build-server-full server nopass
"$EASYRSA_BIN" build-client-full "$CLIENT_NAME" nopass
"$EASYRSA_BIN" gen-crl
openvpn --genkey secret "$PKI_DIR/tls-crypt.key"

chmod 0600 "$PKI_DIR/private/"*.key "$PKI_DIR/tls-crypt.key"
chmod 0644 "$PKI_DIR/ca.crt" "$PKI_DIR/crl.pem" "$PKI_DIR/issued/"*.crt

echo "Created the $SITE_ID PKI and client certificate for $CLIENT_NAME."
