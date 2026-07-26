# NTC Infrastructure

Deployment templates and operational notes for the NTC Newark service stack.

Secrets, live `.env` files, SQLite databases, prompt audio, and generated HLS/runtime data do not belong in this repository. Keep those local to the NAS or the service host.

## Included

- Docker Compose templates
- Nginx/HLS edge configuration
- Cloudflare Telnyx proxy worker source
- WebCall and telephony runbooks
- No-IP hostname renewal helper templates

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

## No-IP Renewal Helper

`tools/noip_confirm_helper.py` checks the configured mailbox for No-IP renewal
emails for `ntcnas.myftp.org`. By default it runs in detect-only mode and writes
the latest report to:

`/home/sysadmin/apps/NTC-Infrastructure/state/noip-renew/latest.md`

Set `NTC_NOIP_AUTO_CONFIRM=1` in the private environment file only when the
helper should follow the official No-IP confirmation link from the email. The
helper does not bypass CAPTCHA, MFA, login prompts, or other interactive
challenges; it reports those as manual-required.

The public IP shown in the report is the runner's public egress IP. It is useful
diagnostic context, but it is not used as proof that `ntcnas.myftp.org` is wrong
when the helper runs from a different network than TrueNAS.

Private runtime config belongs at:

`/home/sysadmin/apps/NTC-Infrastructure/config/noip-renew.env`

Systemd templates:

- `systemd/ntc-noip-renew-check.service`
- `systemd/ntc-noip-renew-check.timer`
