# NTC Infrastructure

Deployment templates and operational notes for the NTC Newark service stack.

Secrets, live `.env` files, SQLite databases, prompt audio, and generated HLS/runtime data do not belong in this repository. Keep those local to the NAS or the service host.

## Included

- Docker Compose templates
- Nginx/HLS edge and public route configuration
- Cloudflare Telnyx proxy worker source
- Reliable mixer-control tunnel configuration
- WebCall and telephony runbooks

## Host Boundaries

TrueNAS remains the public ingress, storage, and control-plane host. Compute
workers may run on other machines, but public clients continue to use
`https://ntcnas.myftp.org`.

The Mac Pro runs `NTC-MultiTrack` and `NTC-MixAssist` behind Tailscale Serve,
plus the stateless `NTC-LiveStream` RTSP-to-HLS worker and the NTC-Agent model
backend on its Tailscale address. TrueNAS remains the only public ingress and
forwards `/multitrack`, `/mixassist`, and `/livestream` to those private
workers. Do not create a second public DNS name for the Mac Pro.

`systemd/ntc-av-local-route.service` makes directly connected
`192.168.10.0/24` AV traffic prefer the Mac Pro's wired AV NIC instead of a
Tailscale subnet route.

The former TrueNAS `ntc-autosyncmix-panel.service` is disabled. The recorder
ingest, promotion, and mixdown pipelines remain in `NTC-AutoSyncMix`; only the
browser/proxy processing surface moved to the Mac Pro as `NTC-MultiTrack`.

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

`mixer-tunnel/` contains the isolated OpenVPN-over-TCP endpoint for remote
MixPad control of devices on the NTC AV LAN. It binds only to the TrueNAS
Tailscale address and does not advertise a default route.

Analysis-only AES67 subscriptions run on the Mac Pro under NTC Dante. The
production Dante-to-WebCall bridge remains on TrueNAS.

## Recorder Pipeline Lanes

Keep the recorder workflows explicitly separated by recorder model. Do not add new generic `recorder` jobs when the source is known.

- `DA6400` is the worship / multitrack recorder lane. It is scheduled through TrueNAS cron as `DA6400 Worship Sync`, `DA6400 Worship Promote`, and `DA6400 Worship AutoMix`. It writes worship outputs under `/mnt/MainRecordings/Recordings/WorshipRecordings` and uses `/mnt/MultitrackRAW` for raw multitrack/cache state.
- `DN700R` is the message / testimony recorder lane. It is scheduled through TrueNAS cron as `DN700R Message Recorder Pipeline`, runs `/root/NTC-Agent/run_dn700r_agent_pipeline.sh`, and labels logs as `dn700r-message-recorder`. It stages raw recorder intake under `/mnt/MainRecordings/Recordings/_IncomingRecorderIntake`, keeps state under `/root/NTC-Runtime/autosyncmix/recorders/DN700R`, and promotes only reviewed/high-confidence files into `/mnt/MainRecordings/Recordings/MessageRecordings` or `/mnt/MainRecordings/Recordings/TestimonyRecordings`.
- DN700R cleanup remains separate as `DN700R Message Clear Verified` so source-card deletion does not get mixed into the DA6400 worship maintenance path.
- `CVAV-DN700R` is an independent portable-rack lane. It uses its own recorder endpoint, manifest, lock, logs, cleanup timer, control-panel instance, review surface, and `/mnt/MainRecordings/Recordings/CVAVRecordings` storage tree. The NTC Recordings container mounts only NTC intake subdirectories, so CVAV raw or review files cannot enter the NTC testimony-review database.
