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
- `ntc-tascam-control`
