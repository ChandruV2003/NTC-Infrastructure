#!/usr/bin/env sh
set -eu

BASE_URL="${NTC_WEBCALL_PUBLIC_BASE_URL:-https://ntcnas.myftp.org/webcall}"
EXPECTED_ROUTE="${NTC_EXPECTED_TELNYX_ROUTE:-main-webcall}"
CHECK_TOKEN="${NTC_TELNYX_ROUTE_CHECK_TOKEN:-route-check-token}"
WEBHOOK_TOKEN="${NTC_TELNYX_WEBHOOK_TOKEN:-}"
if [ -z "$WEBHOOK_TOKEN" ] && command -v docker >/dev/null 2>&1; then
  WEBHOOK_TOKEN="$(docker exec ntc-webcall printenv NTC_TELNYX_WEBHOOK_TOKEN 2>/dev/null || true)"
fi
ROUTE_TOKEN="${WEBHOOK_TOKEN:-$CHECK_TOKEN}"
URL="${BASE_URL%/}/telephony/telnyx/${ROUTE_TOKEN}/voice"

tmp_headers="$(mktemp)"
tmp_body="$(mktemp)"
trap 'rm -f "$tmp_headers" "$tmp_body"' EXIT

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

if [ -n "$WEBHOOK_TOKEN" ]; then
  voice_url="${BASE_URL%/}/telephony/telnyx/${WEBHOOK_TOKEN}/voice"
  voice_status="$(
    curl -k -sS -o "$tmp_body" -D "$tmp_headers" \
      --connect-timeout "${NTC_ROUTE_CHECK_CONNECT_TIMEOUT:-5}" \
      --max-time "${NTC_ROUTE_CHECK_TIMEOUT:-10}" \
      -X POST \
      -w '%{http_code}' \
      "$voice_url"
  )"
  voice_route="$(
    awk 'BEGIN {IGNORECASE=1} /^x-ntc-telnyx-route:/ {print $2}' "$tmp_headers" \
      | tr -d '\r' \
      | tail -1
  )"
  if [ "$voice_status" != "200" ]; then
    echo "bad telnyx voice response: status=${voice_status}" >&2
    sed -n '1,8p' "$tmp_body" >&2
    exit 1
  fi
  if [ "$voice_route" != "$EXPECTED_ROUTE" ]; then
    echo "bad telnyx voice route: expected ${EXPECTED_ROUTE}, got ${voice_route:-missing}" >&2
    exit 1
  fi
  if ! grep -q "<Response>" "$tmp_body"; then
    echo "bad telnyx voice response: missing TeXML Response" >&2
    sed -n '1,8p' "$tmp_body" >&2
    exit 1
  fi

  prompt_url="$(
    sed -n 's#.*<Play>\(.*\)</Play>.*#\1#p' "$tmp_body" \
      | sed 's/&amp;/\&/g' \
      | head -1
  )"
  if [ -n "$prompt_url" ]; then
    python3 - "$prompt_url" <<'PY'
import ssl
import struct
import sys
from urllib.request import Request, urlopen

url = sys.argv[1]
request = Request(url, headers={"Range": "bytes=0-127", "User-Agent": "ntc-webcall-route-check"})
with urlopen(request, timeout=10, context=ssl._create_unverified_context()) as response:
    data = response.read(256)
if len(data) < 36 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
    raise SystemExit(f"bad telnyx prompt wav: not RIFF/WAVE: {url}")
offset = 12
while offset + 8 <= len(data):
    chunk_id = data[offset : offset + 4]
    chunk_size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
    offset += 8
    chunk_data = data[offset : offset + min(chunk_size, len(data) - offset)]
    if chunk_id == b"fmt ":
        if len(chunk_data) < 16:
            raise SystemExit(f"bad telnyx prompt wav: short fmt chunk: {url}")
        audio_format, channels, sample_rate, _, _, bits_per_sample = struct.unpack("<HHIIHH", chunk_data[:16])
        if not (audio_format == 1 and channels == 1 and sample_rate in {8000, 16000} and bits_per_sample == 16):
            raise SystemExit(
                "bad telnyx prompt wav: expected mono PCM16 at 8k/16k, "
                f"got format={audio_format} channels={channels} rate={sample_rate} bits={bits_per_sample}: {url}"
            )
        break
    offset += chunk_size + (chunk_size % 2)
else:
    raise SystemExit(f"bad telnyx prompt wav: missing fmt chunk: {url}")
PY
  fi
fi

echo "telnyx route ok: route=${route}, status=${status}, voice_status=${voice_status:-skipped}"
