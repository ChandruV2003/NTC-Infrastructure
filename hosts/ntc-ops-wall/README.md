# NTC Operations Wall Host

This package provisions the 2013 Mac Pro as a dedicated Ubuntu operations
display and analysis helper. It does not change the production network, Dante
routing, Q-SYS configuration, or TrueNAS services.

## Installation Decision

- Ubuntu 24.04.4 LTS uses the entire internal SSD.
- The host boots directly into the `ntcops` graphical session.
- Full-disk encryption stays disabled because this appliance must recover from
  unattended restarts.
- The host is the primary NTC Large-v3 transcription worker and Multitrack
  processing/streaming worker. TrueNAS remains the authoritative recording
  store and retains the lightweight take-index service.
- The M4 Mac mini remains dedicated to JVT work rather than running NTC
  transcription or media processing.
- Automatic recovery still depends on completing burn-in validation and
  installing a UPS at the PA position.

## Before Erasing macOS

Boot the verified Ubuntu USB with the Option key and select `EFI Boot`, then use
`Try Ubuntu` to confirm:

1. The Apple Cinema HD Display runs at 2560x1600 through the active dual-link
   DVI adapter.
2. Both built-in Ethernet ports link at 1 Gbps.
3. The internal SSD, 64 GB memory, USB ports, audio, Wi-Fi, and both FirePro
   D700 GPUs are detected.
4. Temperatures and fans remain stable for at least 30 minutes.
5. No firmware password blocks external boot.

After those checks, use the installer option `Erase disk and install Ubuntu`.

## Bootstrap

The installer is dry-run-only unless `--apply` is supplied:

```bash
./install.sh
sudo ./install.sh --apply --operator-user ntcops \
  --authorized-key-file /path/to/codex-admin.pub
```

The apply run:

- requires the operator account created during Ubuntu installation;
- installs the display, analysis, SSH, and diagnostic packages;
- installs CIFS support and stages the TrueNAS recording automounts;
- configures GNOME automatic login and kiosk startup;
- installs the standard NTC embossed desktop background;
- disables suspend and display blanking;
- installs a hardened `ntc-operations@.service`;
- installs example environment files without replacing live configuration;
- blocks routed traffic in either direction between the physical interfaces,
  including after Docker enables IPv4 forwarding for its own bridge;
- optionally installs Tailscale, but never authenticates it automatically.

Use `--source /path/to/NTC-Operations` when the application source is already
available on the host. Otherwise deploy the application later over SSH and
start `ntc-operations@ntcops.service` after `/opt/ntc/NTC-Operations` exists.

## Recording Storage

The host mounts the authoritative TrueNAS recording shares on demand:

- `/mnt/ntc/MultitrackFiles`
- `/mnt/ntc/Recordings`

Create `/etc/ntc/ntc-smb.credentials` locally with the SMB account and password,
owned by root with mode `0600`. The installer never creates, replaces, or
commits that secret. When the credential file exists, it enables:

```bash
mnt-ntc-MultitrackFiles.automount
mnt-ntc-Recordings.automount
```

The Mac Pro keeps generated proxy, waveform, and render caches on its internal
SSD. Source recordings and final recording outputs stay on TrueNAS.

## Network Staging

Do not connect both Ethernet ports to the current flat `192.168.10.0/24`
network. Use one port until the control and Dante VLAN migration is complete.

After VLAN 10 and VLAN 70 exist, render the reviewed static configuration:

```bash
./render-netplan.sh \
  --control-interface enp3s0 \
  --dante-interface enp4s0 \
  --output /tmp/01-ntc-ops-wall.yaml
```

The default addresses follow the staged plan:

- control: `192.168.10.90/24`, gateway `192.168.10.1`;
- Dante/AES67: `192.168.70.90/24`, with no default gateway or DNS.

Review the generated file before applying it. The renderer requires a separate
`--apply` flag before it will write under `/etc/netplan`.

## Validation

Run before transferring this package:

```bash
./validate.sh
```

After the host is installed:

```bash
systemctl status ntc-operations@ntcops.service
systemctl status mnt-ntc-MultitrackFiles.automount
systemctl status mnt-ntc-Recordings.automount
curl -fsS http://127.0.0.1:1986/healthz
journalctl -u ntc-operations@ntcops.service
ntc-ops-host-report
ntc-ops-burn-in 30m
```

The host report captures CPU, memory, both GPUs and their drivers, display
mode, Ethernet links, storage health, temperatures, failed services, and kernel
warnings. Run a second report with `sudo` only when SMART details are needed;
the normal user run has the correct graphical-session access for display and
OpenGL detection. The burn-in stresses CPU and memory, records temperatures
before and after, and reports kernel errors raised during the run. It is never
started automatically.

After the initial Ubuntu installation, the only manual handoff required before
remote provisioning is:

```bash
sudo apt update
sudo apt install -y openssh-server
```

Once SSH is reachable, transfer this package and the operator public key, run
the installer in dry-run mode, review its plan, and then perform the apply run.
