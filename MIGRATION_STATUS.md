# NTC NAS Project Migration Status

Last updated: 2026-07-26.

## Live split services

These services now run from split project directories:

- `ntc-webcall`: `/root/NTC-WebCall`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-hls-nginx`: `/root/NTC-Infrastructure/nginx/ntc-hls-nginx.conf`
- `ntc-recordings`: `/root/NTC-Recordings`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-transcriptor`: `/root/NTC-Transcriptor`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-watchdog`: `/root/NTC-WatchDog`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `status-monitor`: `/root/NTC-StatusControl/docker-compose.yml`
- `tascam-control`: `/root/NTC-TascamDA6400Control/docker-compose.yml`
- `denon-dn700r-control`: `/root/NTC-DenonDN700RControl/docker-compose.yml`
- `ntc-autosyncmix-panel`: `/root/NTC-AutoSyncMix/scripts/multitrack_app.py`, managed by `systemd/ntc-autosyncmix-panel.service`
- `ntc-livestream`: Mac Pro worker at `100.109.220.95:8890`; TrueNAS owns only
  the `/livestream` reverse-proxy route

Shared mutable runtime data lives at `/root/NTC-Runtime`.

## Archived legacy paths

The old WebCall/status/Tascam paths were archived under `/root/_legacy` after live references were removed:

- `/root/RoomCast-*`
- `/root/WebCallPreview-*`
- `/root/StatusMonitor-*`
- `/root/TascamControl-*`
- `/root/AutoSyncMix-*`
- `/root/LiveStream-*`

## AutoSyncMix and LiveStream cutover

AutoSyncMix and LiveStream previously ran as orphaned Python processes from old paths:

- `/root/AutoSyncMix`
- `/root/LiveStream`

AutoSyncMix now runs from its renamed TrueNAS project path:

- `/root/NTC-AutoSyncMix`

LiveStream source remains in `/root/NTC-LiveStream` for rollback, but its
TrueNAS service is disabled after cutover to the Mac Pro. Live environment
files remain local and ignored.

AutoSyncMix live NAS code drift was committed to `NTC-AutoSyncMix` before the
cutover. `/root/.tascam.env` and `/root/NTC-AutoSyncMix/.tascam.env` point
`AUTOMIX_WRAPPER` at `/root/NTC-AutoSyncMix/bin/automix_wrapper.sh`.

## Naming note

The only remaining `roomcast` string after migration is the live Nextcloud account value in `/root/NTC-Infrastructure/.env`:

- `NTC_NEXTCLOUD_USERNAME=roomcast-recordings`

That is a real external account/config value and should only be renamed after the corresponding Nextcloud account is created or changed.

## Recorder control naming

`/root/NTC-TascamControl` is retained as a compatibility symlink to `/root/NTC-TascamDA6400Control`. The live DA-6400 container name remains `tascam-control` so dependent status checks and links do not break.
