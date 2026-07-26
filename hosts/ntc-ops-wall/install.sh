#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APPLY=0
OPERATOR_USER="ntcops"
AUTHORIZED_KEY_FILE=""
SOURCE_ROOT=""
INSTALL_TAILSCALE=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --apply                       Perform the installation; otherwise dry-run
  --operator-user USER          Existing Ubuntu desktop account (default: ntcops)
  --authorized-key-file PATH    Public SSH key to install for the operator
  --source PATH                 Existing NTC-Operations source to deploy
  --install-tailscale           Install Tailscale from its official repository
  --help
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --operator-user) OPERATOR_USER="${2:?missing value}"; shift 2 ;;
    --authorized-key-file) AUTHORIZED_KEY_FILE="${2:?missing value}"; shift 2 ;;
    --source) SOURCE_ROOT="${2:?missing value}"; shift 2 ;;
    --install-tailscale) INSTALL_TAILSCALE=1; shift ;;
    --help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$OPERATOR_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || {
  printf 'Invalid operator user: %s\n' "$OPERATOR_USER" >&2
  exit 2
}

if [[ -n "$AUTHORIZED_KEY_FILE" ]]; then
  [[ -f "$AUTHORIZED_KEY_FILE" ]] || {
    printf 'SSH public key not found: %s\n' "$AUTHORIZED_KEY_FILE" >&2
    exit 2
  }
  grep -Eq '^(ssh-(ed25519|rsa)|ecdsa-sha2-nistp(256|384|521)) ' "$AUTHORIZED_KEY_FILE" || {
    printf 'The authorized key file does not contain a recognized SSH public key.\n' >&2
    exit 2
  }
fi

if [[ -n "$SOURCE_ROOT" ]]; then
  [[ -f "$SOURCE_ROOT/pyproject.toml" && -d "$SOURCE_ROOT/ntc_operations" ]] || {
    printf 'Invalid NTC-Operations source directory: %s\n' "$SOURCE_ROOT" >&2
    exit 2
  }
fi

cat <<EOF
NTC Operations wall host plan
  operator user:       $OPERATOR_USER
  SSH key:             ${AUTHORIZED_KEY_FILE:-not supplied}
  application source: ${SOURCE_ROOT:-deploy later}
  install Tailscale:  $INSTALL_TAILSCALE
  apply changes:       $APPLY

Network configuration is intentionally not applied by this installer.
Use render-netplan.sh only after the control and Dante VLANs exist.
EOF

if ((!APPLY)); then
  printf '\nDry run only. Re-run with --apply after reviewing this plan.\n'
  exit 0
fi

[[ "$EUID" -eq 0 ]] || {
  printf '%s\n' '--apply requires root.' >&2
  exit 1
}

source /etc/os-release
[[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]] || {
  printf 'This installer supports Ubuntu 24.04 only; found %s %s.\n' \
    "${ID:-unknown}" "${VERSION_ID:-unknown}" >&2
  exit 1
}

id "$OPERATOR_USER" >/dev/null 2>&1 || {
  printf 'Create the %s desktop account during Ubuntu installation first.\n' "$OPERATOR_USER" >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  alsa-utils \
  chromium-browser \
  cifs-utils \
  curl \
  ethtool \
  ffmpeg \
  git \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-tools \
  glmark2 \
  jq \
  linuxptp \
  lm-sensors \
  mesa-utils \
  openssh-server \
  pciutils \
  python3 \
  python3-venv \
  rsync \
  smartmontools \
  snapd \
  stress-ng \
  ufw \
  x11-xserver-utils

if ((INSTALL_TAILSCALE)); then
  tailscale_installer="$(mktemp)"
  trap 'rm -f "$tailscale_installer"' EXIT
  curl --fail --silent --show-error --location \
    https://tailscale.com/install.sh >"$tailscale_installer"
  sh "$tailscale_installer"
  rm -f "$tailscale_installer"
  trap - EXIT
fi

for group in sudo audio video render plugdev; do
  if getent group "$group" >/dev/null; then
    usermod -aG "$group" "$OPERATOR_USER"
  fi
done

operator_home="$(getent passwd "$OPERATOR_USER" | cut -d: -f6)"
[[ -d "$operator_home" ]] || {
  printf 'Operator home directory is missing: %s\n' "$operator_home" >&2
  exit 1
}

install -d -m 0755 /etc/ntc /opt/ntc
install -d -m 0755 /usr/local/share/backgrounds
install -m 0644 "$SCRIPT_DIR/assets/ntc-embossed-background.jpg" \
  /usr/local/share/backgrounds/ntc-embossed-background.jpg
install -m 0755 "$SCRIPT_DIR/bin/ntc-ops-wall-kiosk" /usr/local/bin/ntc-ops-wall-kiosk
install -m 0755 "$SCRIPT_DIR/bin/ntc-ops-host-report" /usr/local/bin/ntc-ops-host-report
install -m 0755 "$SCRIPT_DIR/bin/ntc-ops-burn-in" /usr/local/bin/ntc-ops-burn-in
install -m 0755 "$SCRIPT_DIR/bin/ntc-ops-block-physical-forwarding" \
  /usr/local/sbin/ntc-ops-block-physical-forwarding
install -m 0644 "$SCRIPT_DIR/systemd/ntc-operations@.service" \
  /etc/systemd/system/ntc-operations@.service
install -m 0644 "$SCRIPT_DIR/systemd/ntc-ops-block-physical-forwarding.service" \
  /etc/systemd/system/ntc-ops-block-physical-forwarding.service

operator_uid="$(id -u "$OPERATOR_USER")"
operator_gid="$(id -g "$OPERATOR_USER")"
for template in \
  mnt-ntc-MultitrackFiles.mount.template \
  mnt-ntc-Recordings.mount.template; do
  destination="/etc/systemd/system/${template%.template}"
  sed \
    -e "s/@OPERATOR_UID@/$operator_uid/g" \
    -e "s/@OPERATOR_GID@/$operator_gid/g" \
    "$SCRIPT_DIR/systemd/$template" >"$destination"
  chmod 0644 "$destination"
done
for unit in \
  mnt-ntc-MultitrackFiles.automount \
  mnt-ntc-Recordings.automount; do
  install -m 0644 "$SCRIPT_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
install -d -m 0755 \
  /mnt/ntc/MultitrackFiles \
  /mnt/ntc/Recordings

if [[ ! -e /etc/ntc/ntc-operations.env ]]; then
  install -m 0640 "$SCRIPT_DIR/env/ntc-operations.env.example" \
    /etc/ntc/ntc-operations.env
fi
if [[ ! -e /etc/ntc/ntc-ops-wall.env ]]; then
  install -m 0644 "$SCRIPT_DIR/env/ntc-ops-wall.env.example" \
    /etc/ntc/ntc-ops-wall.env
fi

install -d -m 0755 -o "$OPERATOR_USER" -g "$OPERATOR_USER" \
  "$operator_home/.config/autostart"
install -m 0644 -o "$OPERATOR_USER" -g "$OPERATOR_USER" \
  "$SCRIPT_DIR/desktop/ntc-ops-wall.desktop" \
  "$operator_home/.config/autostart/ntc-ops-wall.desktop"

if [[ -n "$AUTHORIZED_KEY_FILE" ]]; then
  install -d -m 0700 -o "$OPERATOR_USER" -g "$OPERATOR_USER" \
    "$operator_home/.ssh"
  install -m 0600 -o "$OPERATOR_USER" -g "$OPERATOR_USER" \
    "$AUTHORIZED_KEY_FILE" "$operator_home/.ssh/authorized_keys"
fi

gdm_config=/etc/gdm3/custom.conf
[[ -f "$gdm_config" ]] || {
  printf 'GDM configuration is missing: %s\n' "$gdm_config" >&2
  exit 1
}
python3 - "$gdm_config" "$OPERATOR_USER" <<'PY'
from configparser import ConfigParser
from pathlib import Path
import sys

path = Path(sys.argv[1])
user = sys.argv[2]
config = ConfigParser(strict=False)
config.optionxform = str
config.read(path)
if not config.has_section("daemon"):
    config.add_section("daemon")
config.set("daemon", "AutomaticLoginEnable", "true")
config.set("daemon", "AutomaticLogin", user)
with path.open("w", encoding="utf-8") as handle:
    config.write(handle)
PY

cat >/etc/sysctl.d/99-ntc-ops-wall-no-forwarding.conf <<'EOF'
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0
EOF
sysctl --system >/dev/null

if [[ -n "$SOURCE_ROOT" ]]; then
  install -d -m 0755 /opt/ntc/NTC-Operations
  rsync -a --delete \
    --exclude .git \
    --exclude __pycache__ \
    --exclude '*.pyc' \
    "$SOURCE_ROOT/" /opt/ntc/NTC-Operations/
  chown -R root:root /opt/ntc/NTC-Operations
  find /opt/ntc/NTC-Operations -type d -exec chmod 0755 {} +
  find /opt/ntc/NTC-Operations -type f -exec chmod u=rw,go=r {} +
fi

systemctl daemon-reload
systemctl enable ssh.service
systemctl enable gdm3.service
systemctl enable --now ntc-ops-block-physical-forwarding.service
loginctl enable-linger "$OPERATOR_USER"
if [[ -f /etc/ntc/ntc-smb.credentials ]]; then
  chmod 0600 /etc/ntc/ntc-smb.credentials
  systemctl enable --now \
    mnt-ntc-MultitrackFiles.automount \
    mnt-ntc-Recordings.automount
fi
systemctl set-default graphical.target
systemctl mask \
  sleep.target \
  suspend.target \
  hibernate.target \
  hybrid-sleep.target

if [[ -n "$SOURCE_ROOT" ]]; then
  systemctl enable --now "ntc-operations@$OPERATOR_USER.service"
fi

printf '\nHost provisioning completed.\n'
if [[ -z "$SOURCE_ROOT" ]]; then
  printf 'Deploy NTC-Operations to /opt/ntc/NTC-Operations before enabling its service.\n'
fi
if ((INSTALL_TAILSCALE)); then
  printf 'Tailscale is installed but not authenticated; run tailscale up interactively.\n'
fi
if [[ ! -f /etc/ntc/ntc-smb.credentials ]]; then
  printf 'Create /etc/ntc/ntc-smb.credentials, then enable the two NTC automount units.\n'
fi
printf 'Reboot once to enter the automatic kiosk session.\n'
