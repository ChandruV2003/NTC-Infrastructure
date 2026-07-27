#!/bin/sh
set -eu

pidof openvpn >/dev/null
ip link show tun0 >/dev/null
tc qdisc show dev tun0 | grep -q 'qdisc prio 1:'
tc qdisc show dev tun0 | grep -q 'qdisc tbf 20:'
tc filter show dev tun0 parent 1: | grep -q 'flowid 1:2'
test -s /state/runtime/status.log
