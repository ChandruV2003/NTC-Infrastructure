#!/bin/sh
set -eu

pidof openvpn >/dev/null
ip link show tun0 >/dev/null
tc qdisc show dev tun0 | grep -q ' tbf '
test -s /state/runtime/status.log
