# NTC Infrastructure

Deployment templates and operational notes for the NTC Newark service stack.

Secrets, live `.env` files, SQLite databases, prompt audio, and generated HLS/runtime data do not belong in this repository. Keep those local to the NAS or the service host.

## Included

- Docker Compose templates
- Nginx/HLS edge configuration
- Cloudflare Telnyx proxy worker source
- WebCall and telephony runbooks

## Runtime Services

- `ntc-webcall`
- `ntc-hls-nginx`
- `ntc-recordings`
- `ntc-transcriptor`
- `ntc-watchdog`
- `ntc-status`
- `ntc-autosync-mix`
- `ntc-tascam-da6400-control`
- `ntc-denon-dn700r-control`

## Recorder Pipeline Lanes

Keep the recorder workflows explicitly separated by recorder model. Do not add new generic `recorder` jobs when the source is known.

- `DA6400` is the worship / multitrack recorder lane. It is scheduled through TrueNAS cron as `DA6400 Worship Sync`, `DA6400 Worship Promote`, and `DA6400 Worship AutoMix`. It writes worship outputs under `/mnt/MainRecordings/Recordings/WorshipRecordings` and uses `/mnt/MultitrackRAW` for raw multitrack/cache state.
- `DN700R` is the message / testimony recorder lane. It is scheduled through TrueNAS cron as `DN700R Message Recorder Pipeline`, runs `/root/NTC-Agent/run_dn700r_agent_pipeline.sh`, and labels logs as `dn700r-message-recorder`. It stages raw recorder intake under `/mnt/MainRecordings/Recordings/_IncomingRecorderIntake`, keeps state under `/root/NTC-Runtime/autosyncmix/recorders/DN700R`, and promotes only reviewed/high-confidence files into `/mnt/MainRecordings/Recordings/MessageRecordings` or `/mnt/MainRecordings/Recordings/TestimonyRecordings`.
- DN700R cleanup remains separate as `DN700R Message Clear Verified` so source-card deletion does not get mixed into the DA6400 worship maintenance path.
