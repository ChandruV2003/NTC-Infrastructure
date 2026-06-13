# NTC Newark WebCall Operations

## Public listener flow

- Open `https://ntcnas.myftp.org/webcall/`
- Enter the 4-digit PIN `7070`
- The room page will try to start audio automatically
- If the browser blocks autoplay, tap `Start Audio`
- The page will show whether the meeting is active right now
- You can also send people `https://ntcnas.myftp.org/webcall/p/7070` to skip manual PIN entry

## Control panel flow

- Open `https://ntcnas.myftp.org/webcall/admin`
- Enter the admin password
- Pick `Room A` or `Room B`
- Press `Start Call` to bring that room live
- Press `Stop Call` to take the room down
- Use `Settings` for input order and schedule entries
- Use `Auto` from the control panel only if a room was manually held on or off and you want it following the saved schedule again

The admin panel is only a monitor/control surface. Closing the browser does not stop the service.

Settings always uses the current device list reported by each laptop agent, so the panel stays in sync with whatever Windows is actually exposing.

## What the volunteers actually do

- Power on the source laptop and sign into Windows
- Leave the Scarlett interface connected
- Open `/webcall/admin`
- Confirm `Agent online`
- Confirm the current input looks correct
- Confirm listeners can hear audio if this is an active meeting
- Use `Settings` only when schedules or input order need to change

## What the laptop agent does

- Runs in the background on the source laptop
- Polls WebCall for desired state
- Pulls the current Windows input list into the server
- Chooses the first available input from the saved service order
- Starts and stops ffmpeg publishing
- Reports current device, ingest state, and last error
- Warns after sustained silence
- Allows schedule-driven auto-stop only after the scheduled end time. After that point, the call can stop after 5 minutes of sustained silence or when the main mixer input disappears.
- Prevents duplicate agent instances for the same host

Current limitation: the agent does not yet power-cycle USB devices or restart Focusrite drivers. It handles publish/retry logic, not hardware recovery.

## Listener visibility

- The admin panel shows live listener count per room
- `Listeners now` shows who is currently connected
- `Recent access` shows who connected recently and when
- Web listeners are labeled from their IP address
- Phone listeners are labeled from the calling number when the provider passes it through

## Phone recording diagnostics

NTC WebCall keeps two different phone-path captures:

- `data/telnyx-debug-taps/` records the exact mono PCM frames NTC WebCall sends toward Telnyx before provider encoding.
- Telnyx call recording records the provider-side phone call. Pull the latest completed recording with:

```bash
python3 scripts/fetch_telnyx_recording.py
```

The script loads `TELNYX_API_KEY` from `.env`, downloads the latest matching WAV into `data/telnyx-recordings/`, saves redacted metadata beside it, and prints basic channel metrics.

To place an outside-in probe call through Twilio, set these variables in `.env` or the shell:

```bash
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+18449902638
NTC_PHONE_NUMBER=+18628727904
NTC_PHONE_PIN=7070
```

Then run:

```bash
python3 scripts/twilio_probe_call.py --wait --download-recording
```

The script uses Twilio's Calls REST API, sends the PIN as DTMF after answer, keeps the call silent for the configured probe duration, asks Twilio for a dual-channel recording, and downloads/analyzes the recording when available. If the Twilio account is still in trial mode, the destination number must be verified in Twilio before this test can complete.

## Server watchdog and alerts

The NAS runs a separate `ntc-watchdog` container every 60 seconds. It checks:

- `/healthz`
- the public PIN path `/p/7070`
- `/api/live/status`
- the active HLS playlist and first audio segment when a meeting is live
- source laptop heartbeats and ingest state

If the server or public client path fails, the watchdog records an incident and asks Docker to restart the `ntc-webcall` container. Restarts are rate-limited by `NTC_WATCHDOG_RESTART_COOLDOWN_SECONDS` so it does not loop endlessly.

## Browser load testing

Use the browser/HLS load tester before production meetings or after changing streaming code:

```bash
python3 scripts/load_test_webcall.py \
  --base-url https://ntcnas.myftp.org/webcall \
  --pin 7070 \
  --clients 10 \
  --duration-seconds 120
```

This test joins the WebCall like browser listeners, refreshes the HLS playlist, and downloads the latest segment. Passing means zero HTTP errors and playlist/segment p95 latency under one second. It does not place phone calls; use controlled Telnyx/Twilio probes for phone-path testing.

## Telnyx phone stream profile

The phone path uses TeXML bidirectional `<Stream>` over WebSocket/RTP. Keep production on `NTC_TELNYX_STREAM_CODEC=G722` unless a controlled phone probe proves another official TeXML bidirectional codec is better. Do not advertise codecs that the TeXML `<Stream>` docs do not list for `bidirectionalCodec`; unsupported labels can make valid PCM sound like static because Telnyx decodes the bytes as the wrong format.

This is not the old segmented WAV playback path. Telnyx receives a continuous WebSocket media stream from NTC WebCall, with an app-side startup buffer and jitter queue before frames are encoded and sent. HTTP/CDN cache settings do not apply to that WebSocket stream; phone reliability comes from the app buffer, reconnect handling, and keeping the source laptop stream stable.

Production defaults hold about 1.8 seconds of audio before the Telnyx sender starts (`NTC_TELNYX_STREAM_FRAME_MS=60`, `NTC_TELNYX_STARTUP_BUFFER_FRAMES=30`) and allow roughly 7.7 seconds of queue capacity (`NTC_TELNYX_MAX_BUFFER_FRAMES=128`). If callers report short dropouts while browser HLS is clean, tune these before changing codecs.

## HLS Nginx serving

Browser WebCall uses one room-level HLS/AAC stream. The app still owns PIN/session validation and playlist generation, but `.ts` segment bytes are served by the `ntc-hls-nginx` sidecar from `data/hls/`:

```bash
NTC_HLS_EDGE_CACHE_ENABLED=1
NTC_HLS_OUTPUT_ROOT=/app/data/hls
NTC_HLS_PLAYLIST_EDGE_CACHE_SECONDS=1
NTC_HLS_SEGMENT_EDGE_CACHE_SECONDS=30
NTC_HLS_SNAPSHOT_CACHE_SECONDS=0.75
NTC_HLS_CLEANUP_INTERVAL_SECONDS=1.5
```

Playlists stay effectively live with a one-second cache TTL. Segment URLs use `/webcall/listen/hls-nginx/<stream-token>/<room>/...`, so cached segments do not collide across stream restarts. This only directly helps browser listeners; Telnyx phone audio uses bidirectional WebSockets and cannot be CDN-cached. It can still indirectly help calls by reducing Python CPU spent on browser segment downloads.

Nginx Proxy Manager should route `/webcall/listen/hls-nginx/` to `ntc-hls-nginx` on port `1968`. The older `/webcall/listen/hls-edge/` path is kept temporarily only so pre-existing browser sessions do not break during a deploy. If proxy caching is enabled for HLS paths, the cache key must include the full query string:

```nginx
proxy_cache_key "$scheme$request_method$host$uri$is_args$args";
```

Do not use only `$uri` for HLS segments. Segment filenames restart from low sequence numbers when a room stream restarts; the `?v=<stream-token>` query parameter is what prevents old cached segments from being replayed into a new meeting.

## Process priority guard

During meetings, keep `ntc-webcall` ahead of batch jobs and transcription:

```bash
sudo python3 scripts/ntc_priority_guard.py --base-url http://127.0.0.1:1967 --pin 7070
```

The guard does not restart services. It raises priority for the WebCall gunicorn/HLS ffmpeg processes and lowers priority for known background jobs such as Whisper transcription and AutoSyncMix sync/mixdown work when a meeting appears active.

HTML email alerts are configured through environment variables:

```bash
NTC_ALERT_EMAIL_ENABLED=1
NTC_ALERT_EMAIL_TO=alerts@example.com
NTC_ALERT_EMAIL_FROM=ntc-watchdog@example.com
NTC_ALERT_SMTP_HOST=smtp.example.com
NTC_ALERT_SMTP_PORT=587
NTC_ALERT_SMTP_USERNAME=ntc-watchdog@example.com
NTC_ALERT_SMTP_PASSWORD=...
NTC_ALERT_SMTP_STARTTLS=1
NTC_ALERT_COOLDOWN_SECONDS=900
```

Alerts are deduplicated. A repeated failure sends at most one email per cooldown window, and a recovery email is sent when previously open issues clear.

## The Translator

NTC WebCall can run a server-side transcription worker for selected rooms. The worker listens to the existing room audio stream, converts rolling chunks to mono PCM16 at 16 kHz, sends those chunks to the configured speech-to-text provider, and stores final transcript segments.

Caption viewing and translated audio output controls are served by a separate internal service, `ntc-transcriptor`, so Translator viewers do not add request load to the public WebCall app. The service reads the shared SQLite database and polls for new transcript rows.

Current safety defaults:

- Transcription is off per room until it is enabled from The Translator panel
- The room-level transcription switch is stored in SQLite, so toggling it does not require a WebCall container restart
- The default provider is OpenAI; Telnyx, local command, and local HTTP providers are also supported
- Local command transcription is blocked unless `NTC_TRANSCRIPTION_ALLOW_LOCAL_COMMAND=1`; use `local_http` for offloading to the M4 Mac mini
- Translated audio output defaults to off and is controlled from The Translator, not WebCall admin settings
- The translated audio target language is selected in The Translator and saved per source laptop
- Queued translated WAV files are pulled by the Envy agent only when room output is on

Configuration:

```env
NTC_TRANSCRIPTION_PROVIDER=openai
OPENAI_API_KEY=...
```

or:

```env
NTC_TRANSCRIPTION_PROVIDER=telnyx
TELNYX_API_KEY=...
```

For no-cloud local transcription on the NAS, run a local command from inside the `ntc-webcall` container only for private testing. This is disabled by default because it can consume significant CPU/RAM on the NAS. The command must print either plain transcript text or JSON with a `text` field. `{audio}` is replaced with a temporary 16 kHz mono WAV file path.

```env
NTC_TRANSCRIPTION_PROVIDER=local_cmd
NTC_TRANSCRIPTION_ALLOW_LOCAL_COMMAND=1
NTC_TRANSCRIPTION_LOCAL_COMMAND=whisper-cli -m /app/data/models/ggml-base.en.bin -f {audio} -l en -nt -np
NTC_TRANSCRIPTION_TIMEOUT_SECONDS=25
```

For offloading transcription to the M4 Mac mini, run the Whisper large bridge on the M4 and point the NAS at it. Production should use the M4 endpoint, not the Debian Mac mini:

```bash
python3 tools/whisper_large_server.py \
  --host 0.0.0.0 \
  --port 8766 \
  --model openai/whisper-large-v3 \
  --device cpu \
  --quiet
```

```env
NTC_TRANSCRIPTION_PROVIDER=local_http
NTC_TRANSCRIPTION_LOCAL_URL=http://100.66.210.59:8766/transcription
NTC_TRANSCRIPTION_TIMEOUT_SECONDS=45
```

Current production intent: use `local_http` for live transcription so the NAS only prepares chunks and stores transcript rows. The M4 Mac mini owns Whisper large-v3 transcription. The Debian Mac mini is a development/control host and should not run the live transcription workload.

`NTC_TRANSCRIPTION_TIMEOUT_SECONDS` controls how long a single local transcription call may take. If the local command is too slow for the configured chunk size, captions will lag behind the meeting. `NTC_TRANSCRIPTION_MIN_RMS_DB` skips quiet chunks before they reach the transcriber. `NTC_TRANSCRIPTION_SUPPRESS_REGEX` skips final text that only describes non-speech audio, such as `(upbeat music)`.

Replay a saved recording through the same local transcription handoff without touching any live room audio:

```bash
python3 scripts/replay_transcription_sample.py \
  --provider local_http \
  --local-url http://100.66.210.59:8766/transcription \
  --room room-a \
  --limit-seconds 60 \
  data/diagnostic-audio/hearing-example.wav
```

The script normalizes WAV/MP3/WebM input to mono PCM16 at 16 kHz, sends chunks to `local_http` or `local_cmd`, and writes transcript rows with source `diagnostic-replay` unless `--dry-run` is used. Use this to validate captions from stored NAS recordings before enabling a room live.

Internal Translator panel:

```env
NTC_CAPTIONS_PORT=6767
NTC_CAPTIONS_HOST_BIND=0.0.0.0
NTC_CAPTIONS_AUTH_ENABLED=1
NTC_CAPTIONS_TITLE=The Translator
NTC_CAPTIONS_PANEL_PASSWORD=...
NTC_TRANSLATION_AUDIO_DIR=/app/data/translation-audio
```

Use `NTC_CAPTIONS_HOST_BIND=<nas-tailscale-ip>` if the panel should bind only to the NAS Tailscale interface. Set `NTC_CAPTIONS_AUTH_ENABLED=0` only when the panel is Tailscale-only. If auth is enabled and `NTC_CAPTIONS_PANEL_PASSWORD` is omitted, the panel accepts the admin password. Open `http://<nas-tailscale-ip>:6767/` from a Tailscale-connected device.

Place reusable sample WAV files in `NTC_TRANSLATION_AUDIO_DIR` as `sample-<language-code>.wav`, for example `sample-zh-CN.wav`. The Translator page can queue those files to the Envy agent for a controlled playback test.

## Message recording requests

The recordings request panel is a separate service from WebCall and The Translator. It scans the NAS message library read-only, accepts public recording requests by date, and lets an admin prepare a private share link for the matched file.

Default service settings:

```env
NTC_RECORDINGS_PORT=7777
NTC_RECORDINGS_LIBRARY_DIRS=/mnt/MainRecordings/Recordings/MessageRecordings
NTC_RECORDINGS_DB_PATH=/app/data/recording-requests.db
NTC_RECORDINGS_PANEL_TITLE=NTC NAS Recordings
NTC_RECORDINGS_PUBLIC_BASE_URL=https://ntcnas.myftp.org/recordings
NTC_RECORDINGS_ADMIN_PASSWORD=
NTC_RECORDINGS_SHARE_PROVIDER=internal
NTC_RECORDINGS_AUTO_ARCHIVE_DAYS=30
```

The service listens on port `7777` internally. Public access should be routed through the reverse proxy at `https://ntcnas.myftp.org/recordings/` so redirects and generated share links stay on the main `ntcnas.myftp.org` domain.

If `NTC_RECORDINGS_ADMIN_PASSWORD` is omitted, the panel accepts the WebCall admin password. Email sending is intentionally disabled unless SMTP settings are configured:

```env
NTC_RECORDINGS_EMAIL_ENABLED=1
NTC_RECORDINGS_EMAIL_FROM=ntcnewarkrecordings@gmail.com
NTC_RECORDINGS_SMTP_HOST=smtp.gmail.com
NTC_RECORDINGS_SMTP_PORT=587
NTC_RECORDINGS_SMTP_USERNAME=ntcnewarkrecordings@gmail.com
NTC_RECORDINGS_SMTP_PASSWORD=...
NTC_RECORDINGS_SMTP_STARTTLS=1
```

Without SMTP, the admin panel still prepares the private link and shows it for manual sharing. The service stores request state in its own SQLite database and does not write to the WebCall call database.

Completed and revoked requests remain visible until archived. `NTC_RECORDINGS_AUTO_ARCHIVE_DAYS` controls when completed requests automatically move to the Archived tab; set it to `0` to disable automatic archiving.

Nextcloud share links can be enabled after adding an app password and local-to-Nextcloud path mapping:

```env
NTC_RECORDINGS_SHARE_PROVIDER=nextcloud
NTC_NEXTCLOUD_BASE_URL=https://nextcloud.example.com
NTC_NEXTCLOUD_USERNAME=...
NTC_NEXTCLOUD_APP_PASSWORD=...
NTC_NEXTCLOUD_LOCAL_PATH_PREFIX=/mnt/MainRecordings/Recordings/MessageRecordings
NTC_NEXTCLOUD_PATH_PREFIX=Recordings/MessageRecordings
```

If Nextcloud sharing fails or is not configured, the panel falls back to the internal private download link instead of blocking the request.

Phone stream reconnect retention:

```env
NTC_TELNYX_STREAM_RECONNECT_ENABLED=1
NTC_TELEPHONY_SESSION_TTL_SECONDS=300
NTC_TELEPHONY_CLOSURE_TTL_SECONDS=600
```

`NTC_TELEPHONY_SESSION_TTL_SECONDS` is the app-side window for holding a phone session open while Telnyx reconnects its media WebSocket. It cannot stop the carrier from ending a call, but it prevents NTC WebCall from discarding reconnectable sessions too aggressively after a short server or network blip.

## Setting up a new source laptop

1. Copy the WebCall files to the laptop
2. Install Python 3.12+ and ffmpeg
3. Get the host slug and heartbeat token from the server
4. Run the install script:

```powershell
.\install_ntc_agent_task.ps1 `
  -ServerUrl "https://ntcnas.myftp.org/webcall" `
  -HostSlug "<host-slug>" `
  -Token "<heartbeat-token>" `
  -TaskName "WebCall Source Agent" `
  -PollIntervalSeconds 3
```

5. The installer will stop stale NTC WebCall host processes, refresh the task, add startup and logon triggers, and start it immediately
6. Confirm the task is running
7. Open the control panel and verify the new host shows `Agent online`
8. Open `Settings` and confirm the known device list is populated for that host
9. Set the input order for that host so the preferred device is first

That is enough for another Windows source laptop to join the system. The server stays the same; the only host-specific values are the slug and heartbeat token.

## Using another building or network

Yes. A source laptop on another network can publish to the same server as long as:

- it can reach `https://ntcnas.myftp.org/webcall`
- its host slug/token are registered on the server
- the selected input device is available locally

Listeners can join from anywhere that can reach the public WebCall URL.

## Current phone status

- Telnyx is the live public phone provider for `+1 862 872 7904`.
- Twilio can be used as an outside caller/debug probe, not as the production provider.
- NTC WebCall keeps app-side debug taps plus provider recordings so phone quality can be checked from both sides of the handoff.

## 2026-05-10 live service lessons

These points came from the first Sunday production run and should be treated as regression checks before the next live meeting.

- Listener counts must mean current unique listeners, not cumulative joins. Watchdog probes and load-test user agents are internal traffic and must not be counted as real participants.
- Every listener row must have a close reason. Phone and browser issues should be diagnosed from `listener_sessions.close_reason` plus matching `telephony` and `listener` events, not by guessing from join/leave timestamps alone.
- Source input selection must preserve history. The agent should use the first available saved input, fall back only when it disappears, and switch back immediately when the preferred SQ/CQ device returns.
- Device-selection events must include the configured order, available devices, remembered devices, current device, desired-active state, and ingest state. If the mixer disappears again, the event should show exactly why the fallback was selected.
- Telnyx stream stats should be useful, not noisy. Persist periodic stream stats and abnormal stats, especially fallback percentage, buffer milliseconds, late-send milliseconds, source level, source device, and source format.
- Runtime temp cleanup must be visible. Startup cleanup of orphaned HLS/transcription temp folders logs how many directories and bytes were removed, so a repeat disk-growth issue is obvious.
- Transcription should not compete with WebCall during production. If transcription is enabled, use `local_http` offload to the M4 Mac mini instead of running heavy local inference inside the WebCall container or on the Debian Mac mini.
- When reviewing CPU, remember Docker CPU percent is per logical CPU thread. A container showing 250% means roughly 2.5 cores, not 250% of the NAS.
