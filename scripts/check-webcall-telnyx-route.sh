#!/usr/bin/env sh
set -eu

BASE_URL="${NTC_WEBCALL_PUBLIC_BASE_URL:-https://ntcnas.myftp.org/webcall}"
EXPECTED_ROUTE="${NTC_EXPECTED_TELNYX_ROUTE:-main-webcall}"
CHECK_TOKEN="${NTC_TELNYX_ROUTE_CHECK_TOKEN:-route-check-token}"
URL="${BASE_URL%/}/telephony/telnyx/${CHECK_TOKEN}/voice"

tmp_headers="$(mktemp)"
trap 'rm -f "$tmp_headers"' EXIT

status="$(
  curl -k -sS -o /dev/null -D "$tmp_headers" \
    --connect-timeout "${NTC_ROUTE_CHECK_CONNECT_TIMEOUT:-5}" \
    --max-time "${NTC_ROUTE_CHECK_TIMEOUT:-10}" \
    -w '%{http_code}' \
    "$URL"
)"

route="$(
  awk 'BEGIN {IGNORECASE=1} /^x-ntc-telnyx-route:/ {print $2}' "$tmp_headers" \
    | tr -d '\r' \
    | tail -1
)"

if [ "$route" != "$EXPECTED_ROUTE" ]; then
  echo "bad telnyx route: expected ${EXPECTED_ROUTE}, got ${route:-missing}, status=${status}" >&2
  exit 1
fi

if [ "$status" = "502" ] || [ "$status" = "000" ]; then
  echo "bad telnyx route status: ${status}" >&2
  exit 1
fi

echo "telnyx route ok: route=${route}, status=${status}"
