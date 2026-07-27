FROM alpine:3.21

RUN apk add --no-cache \
        iproute2 \
        iptables \
        openvpn

COPY openvpn/server.conf.template /opt/mixer-tunnel/server.conf.template
COPY scripts/container-entrypoint.sh /opt/mixer-tunnel/container-entrypoint.sh
COPY scripts/healthcheck.sh /opt/mixer-tunnel/healthcheck.sh
COPY scripts/host-return-entrypoint.sh /opt/mixer-tunnel/host-return-entrypoint.sh
COPY scripts/host-return-healthcheck.sh /opt/mixer-tunnel/host-return-healthcheck.sh
COPY scripts/configure-tunnel-qos.sh /opt/mixer-tunnel/configure-tunnel-qos.sh

RUN chmod 0755 /opt/mixer-tunnel/*.sh

ENTRYPOINT ["/opt/mixer-tunnel/container-entrypoint.sh"]
