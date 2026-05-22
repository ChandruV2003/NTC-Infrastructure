# NTC NAS Project Migration Status

Last updated: 2026-05-22.

## Live split services

These services now run from split project directories:

- `ntc-webcall`: `/root/NTC-WebCall`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-hls-nginx`: `/root/NTC-Infrastructure/nginx/ntc-hls-nginx.conf`
- `ntc-recordings`: `/root/NTC-Recordings`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-transcriptor`: `/root/NTC-Transcriptor`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `ntc-watchdog`: `/root/NTC-WatchDog`, orchestrated by `/root/NTC-Infrastructure/docker-compose.ntc.yml`
- `status-monitor`: `/root/NTC-StatusControl/docker-compose.yml`
- `tascam-control`: `/root/NTC-TascamControl/docker-compose.yml`
- `ntc-autosyncmix-panel`: `/root/NTC-AutoSyncMix/scripts/multitrack_app.py`, managed by `systemd/ntc-autosyncmix-panel.service`
- `ntc-livestream`: `/root/NTC-LiveStream/stream_server.py`, managed by `systemd/ntc-livestream.service`

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

They now run from renamed project paths:

- `/root/NTC-AutoSyncMix`
- `/root/NTC-LiveStream`

AutoSyncMix live NAS code drift was committed to `NTC-AutoSyncMix` before the cutover. Live environment files remain local and ignored. `/root/.tascam.env` and `/root/NTC-AutoSyncMix/.tascam.env` now point `AUTOMIX_WRAPPER` at `/root/NTC-AutoSyncMix/bin/automix_wrapper.sh`.

## Naming note

The only remaining `roomcast` string after migration is the live Nextcloud account value in `/root/NTC-Infrastructure/.env`:

- `NTC_NEXTCLOUD_USERNAME=roomcast-recordings`

That is a real external account/config value and should only be renamed after the corresponding Nextcloud account is created or changed.
