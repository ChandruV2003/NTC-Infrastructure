# NTC Mixer Control Tunnel

This endpoint carries SQ/CQ control traffic through a reliable TCP stream
between the MixPad Mac and TrueNAS. The TCP session itself travels over
Tailscale, so the service is not exposed to the public internet.

The tunnel uses OpenVPN as the transport engine. This repository owns the
site-specific routing, isolation, health check, certificate workflow, and
client profile.

## Traffic boundaries

- Outer endpoint: `100.69.202.29:2443/tcp` by default.
- Tunnel network: `10.254.10.0/24`.
- Client route: SQ at `192.168.10.56/32`.
- Server forwarding boundary: `192.168.10.0/24`.
- No default route or DNS settings are sent to the client.
- Mixer discovery broadcasts are not bridged. Connect to the SQ by its direct
  address when automatic discovery is unavailable.

All addresses are configured in `.env`. A future AV LAN renumber requires
changing the three `MIXER_TUNNEL_LAN_*` values and
`MIXER_TUNNEL_TARGET_IP`, then rendering a new client profile. The PKI does
not need to be replaced.

The generated profile installs a host route instead of another
`192.168.10.0/24` route. That host route takes precedence over Tailscale's
existing subnet route without disabling other Tailscale routes.

## Generate private material

Generate the PKI on a trusted Docker host, not on TrueNAS:

```sh
cp .env.example .env
install -d -m 0700 admin-state
docker compose -f pki/compose.yml build
docker compose -f pki/compose.yml run --rm \
  pki /opt/mixer-tunnel/init-pki.sh
docker compose -f pki/compose.yml run --rm \
  pki /opt/mixer-tunnel/render-client.sh
docker compose -f pki/compose.yml run --rm \
  pki /opt/mixer-tunnel/export-server.sh
```

The client profile is written to
`admin-state/clients/ntc-mixpad-mac.ovpn`. Keep `admin-state/` on the trusted
administrative host; it contains the CA and client private key.

Only `admin-state/server-bundle/` may be copied to TrueNAS. Stage its contents
as `mixer-tunnel/server-state/`. The server bundle contains the server key,
public CA certificate, CRL, and TLS control-channel key, but not the CA private
key or any client profile.

Set `MIXER_TUNNEL_PKI_UID` and `MIXER_TUNNEL_PKI_GID` in `.env` to the
numeric user and group that own the administrative checkout.

## Start on TrueNAS

Review `.env` and the staged server bundle before starting the endpoint:

```sh
test -s server-state/pki/private/server.key
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Import the generated profile into an OpenVPN client on the Mac. Tailscale must
already be connected because the profile's remote endpoint is a Tailscale IP.

## Validation

Check container health and verify the restricted route from the Mac:

```sh
docker compose ps
docker compose logs --tail=100 mixer-tunnel
route -n get 192.168.10.56
ping -c 5 192.168.10.56
```

The OpenVPN interface should own the mixer route while the profile is active.
Disconnect the profile and confirm that the existing Tailscale subnet route
resumes ownership.

## Expected behavior

TCP retransmission can turn intermittent packet loss into delayed control
updates instead of immediate missing packets. It cannot remove underlying
latency, and a severely degraded path can still stall while retransmissions
complete. Validate with MixPad before treating this as the normal control path.
