#!/usr/bin/env bash
set -euo pipefail

LANE_ID="${LANE_ID:-google-message-exporter}"
SOURCE_ROOT="${SOURCE_ROOT:-/mnt/MainRecordings/Recordings/MessageRecordings}"
REMOTE="${REMOTE:-ntc-message-recordings-drive:}"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-45}"
LOG_DIR="${LOG_DIR:-/root/NTC-Runtime/google-message-exporter/logs}"
STATE_DB="${STATE_DB:-/root/NTC-Runtime/google-message-exporter/manifest.sqlite3}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/google-message-exporter.log}"

mkdir -p "$LOG_DIR"

log() {
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$LANE_ID" "$*" | tee -a "$LOG_FILE"
}

LOCK_FILE="${LOCK_FILE:-$LOG_DIR/google-message-exporter.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "skip previous run still active"
    exit 0
fi

log "start source=$SOURCE_ROOT remote=$REMOTE max_age_days=$MAX_AGE_DAYS"
/usr/bin/python3 /root/NTC-Infrastructure/message-google-exporter/google_message_exporter.py \
    --source-root "$SOURCE_ROOT" \
    --remote "$REMOTE" \
    --state-db "$STATE_DB" \
    --max-age-days "$MAX_AGE_DAYS" \
    "$@" 2>&1 | tee -a "$LOG_FILE"
log "done"
