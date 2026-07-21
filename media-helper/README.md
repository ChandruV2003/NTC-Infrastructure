# NTC Media Helper

This bundle separates public media delivery from WebCall.

The intended request paths are:

- `https://ntcnas.myftp.org/videos/...` for the public page/player.
- `https://<ntc-media-helper-host>/media-cache/...` for heavy HLS media bytes.
- `https://ntcnas.myftp.org/media-origin/...` as the locked origin fetched only by the helper.

Do not route `/webcall`, `/webcall/listen/hls-nginx`, `/listen/hls-nginx`, or
telephony traffic through this helper. Those paths stay local to TrueNAS/NPM.

## Design

The helper is a cache, not a second media library.

1. TrueNAS keeps the source recordings and generated public HLS packages.
2. Oracle runs nginx with `proxy_cache`.
3. A cache miss fetches the requested HLS file from the TrueNAS media origin.
4. Later requests are served from Oracle until the cache evicts them.

This avoids uploading/moving the media library to Oracle. The cache can be capped
at `10g`, `50g`, or another operational value.

## Why Disk Cache Instead Of A RAM Disk

Use nginx disk cache with a size cap. Linux will automatically keep hot cached
files in RAM when memory is available. A forced RAM disk is simpler conceptually
but easier to break under pressure because it competes directly with nginx,
TLS, kernel buffers, and the OS.

For an Always Free Oracle VM, start with:

- nginx cache `max_size=10g`
- cache inactive window `7d`
- HLS segment cache `30d`
- HLS playlist/manifest cache `30s`

## Hostname

To keep Oracle out of user-facing links, point a normal media hostname at the
Oracle public IP, for example:

- `ntcmedia.myftp.org`
- `media.<owned-domain>`

The NTCNAS page can still be the only shared link. The browser will fetch video
chunks from the helper hostname behind the player.

If every byte is forced through `ntcnas.myftp.org` as a reverse proxy to Oracle,
TrueNAS still carries the outbound traffic and the helper no longer solves the
bandwidth problem.

