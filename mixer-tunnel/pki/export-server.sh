#!/bin/sh
set -eu

PKI_DIR=/state/pki
BUNDLE_ROOT=/state/server-bundle
BUNDLE_DIR="$BUNDLE_ROOT/pki"

for path in \
    "$PKI_DIR/ca.crt" \
    "$PKI_DIR/issued/server.crt" \
    "$PKI_DIR/private/server.key" \
    "$PKI_DIR/crl.pem" \
    "$PKI_DIR/tls-crypt.key"; do
    if [ ! -s "$path" ]; then
        echo "Missing server PKI file: $path" >&2
        exit 1
    fi
done

unexpected_file="$(
    find "$BUNDLE_ROOT" \( -type f -o -type l \) \
        ! -path "$BUNDLE_DIR/ca.crt" \
        ! -path "$BUNDLE_DIR/issued/server.crt" \
        ! -path "$BUNDLE_DIR/private/server.key" \
        ! -path "$BUNDLE_DIR/crl.pem" \
        ! -path "$BUNDLE_DIR/tls-crypt.key" \
        -print -quit 2>/dev/null || true
)"
if [ -n "$unexpected_file" ]; then
    echo "Refusing server bundle with unexpected material: $unexpected_file" >&2
    exit 1
fi

install -d -m 0700 "$BUNDLE_DIR/issued" "$BUNDLE_DIR/private"
install -m 0644 "$PKI_DIR/ca.crt" "$BUNDLE_DIR/ca.crt"
install -m 0644 "$PKI_DIR/issued/server.crt" "$BUNDLE_DIR/issued/server.crt"
install -m 0600 "$PKI_DIR/private/server.key" "$BUNDLE_DIR/private/server.key"
install -m 0644 "$PKI_DIR/crl.pem" "$BUNDLE_DIR/crl.pem"
install -m 0600 "$PKI_DIR/tls-crypt.key" "$BUNDLE_DIR/tls-crypt.key"

echo "Wrote the server-only bundle to /state/server-bundle."
