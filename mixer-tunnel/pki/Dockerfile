FROM alpine:3.21

RUN apk add --no-cache \
        easy-rsa \
        openvpn

COPY init-pki.sh /opt/mixer-tunnel/init-pki.sh
COPY render-client.sh /opt/mixer-tunnel/render-client.sh
COPY export-server.sh /opt/mixer-tunnel/export-server.sh

RUN chmod 0755 /opt/mixer-tunnel/*.sh
