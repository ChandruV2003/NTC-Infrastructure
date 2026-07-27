#!/bin/sh
set -eu

pidof openvpn >/dev/null
ip link show tun0 >/dev/null
test -s /state/runtime/status.log
