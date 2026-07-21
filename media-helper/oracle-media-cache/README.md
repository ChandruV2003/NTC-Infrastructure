# Oracle Media Cache Helper

This runs on the Oracle Always Free VM and caches only public HLS media files.

It must not be used for WebCall, phone audio, admin panels, Nextcloud, or any
latency-sensitive live control path.

## Required DNS

Create a public hostname that points to the Oracle VM public IP, such as:

`ntcmedia.myftp.org`

Open inbound TCP `80` and `443` in the Oracle VCN security list / network
security group so Caddy can get a Let's Encrypt certificate.

## Install

On the Oracle VM:

```bash
sudo mkdir -p /opt/ntc-media-helper
sudo cp -a oracle-media-cache/. /opt/ntc-media-helper/
cd /opt/ntc-media-helper
sudo cp .env.example .env
sudo vi .env
sudo mkdir -p /var/cache/ntc-media-helper
sudo docker compose up -d
```

The `.env` values that must be changed:

- `NTC_MEDIA_HOSTNAME`
- `NTC_ORIGIN_KEY`

The same `NTC_ORIGIN_KEY` must be configured on the TrueNAS media origin.

## Cache Behavior

- HLS playlists and manifests cache for 30 seconds.
- HLS segments, subtitles, thumbnails, and images cache for 30 days.
- The cache is capped by `NTC_CACHE_MAX_SIZE`, default `10g`.
- Raw source video extensions are denied.

Check cache status:

```bash
curl -I https://$NTC_MEDIA_HOSTNAME/media-cache/example/master.m3u8
```

Look for:

`X-NTC-Media-Cache: MISS`, then `HIT` on the second request.

