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

Shared mutable runtime data lives at `/root/NTC-Runtime`.

## Archived legacy paths

The old WebCall/status/Tascam paths were archived under `/root/_legacy` after live references were removed:

- `/root/RoomCast-*`
- `/root/WebCallPreview-*`
- `/root/StatusMonitor-*`
- `/root/TascamControl-*`

## Not cut over yet

These old paths still have live Python processes and should not be renamed in-place:

- `/root/AutoSyncMix`
- `/root/LiveStream`

Renamed repos are cloned beside them for comparison and a future planned cutover:

- `/root/NTC-AutoSyncMix`
- `/root/NTC-LiveStream`

`NTC-AutoSyncMix` has known live-code drift versus the GitHub repo. Reconcile the live NAS copy before restarting from `/root/NTC-AutoSyncMix`.

## Naming note

The only remaining `roomcast` string after migration is the live Nextcloud account value in `/root/NTC-Infrastructure/.env`:

- `NTC_NEXTCLOUD_USERNAME=roomcast-recordings`

That is a real external account/config value and should only be renamed after the corresponding Nextcloud account is created or changed.
