# TrueNAS Media Origin

This origin is separate from WebCall and Nextcloud.

It serves only generated public delivery files from:

`/mnt/MainRecordings/Recordings/VideoRecordings/.ntc-delivery`

The raw `VideoRecordings` source tree should not be exposed through this origin.
Public recordings should be packaged to HLS first.

## Expected Public Flow

1. NTCNAS player page is shared with people.
2. The player requests HLS media from the Oracle helper hostname.
3. Oracle requests cache misses from this TrueNAS origin using
   `X-NTC-Media-Origin-Key`.

## NPM Path

When deployed, add a new Nginx Proxy Manager custom location:

- Path: `/media-origin`
- Forward host: `192.168.1.212`
- Forward port: `1978`
- Advanced config:

```nginx
rewrite ^/media-origin/(.*)$ /media-origin/$1 break;

proxy_connect_timeout 15s;
proxy_send_timeout 60s;
proxy_read_timeout 60s;
proxy_set_header X-Forwarded-Prefix /media-origin;
```

Do not modify the existing `/webcall` locations for this feature.

