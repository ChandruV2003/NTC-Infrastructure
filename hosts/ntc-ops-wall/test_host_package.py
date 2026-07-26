from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class HostPackageTests(unittest.TestCase):
    def test_installer_is_dry_run_by_default(self) -> None:
        result = subprocess.run(
            [str(ROOT / "install.sh")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Dry run only", result.stdout)
        self.assertIn("apply changes:       0", result.stdout)

    def test_netplan_keeps_default_route_off_dante_interface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "netplan.yaml"
            subprocess.run(
                [
                    str(ROOT / "render-netplan.sh"),
                    "--control-interface",
                    "enp3s0",
                    "--dante-interface",
                    "enp4s0",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            rendered = output.read_text(encoding="utf-8")

        self.assertEqual(rendered.count("to: default"), 1)
        dante_section = rendered.split("enp4s0:", 1)[1]
        self.assertNotIn("to: default", dante_section)
        self.assertNotIn("nameservers:", dante_section)
        self.assertIn("link-local: []", dante_section)

    def test_renderer_refuses_same_interface(self) -> None:
        result = subprocess.run(
            [
                str(ROOT / "render-netplan.sh"),
                "--control-interface",
                "enp3s0",
                "--dante-interface",
                "enp3s0",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be different", result.stderr)

    def test_service_is_local_and_hardened(self) -> None:
        unit = (ROOT / "systemd/ntc-operations@.service").read_text(encoding="utf-8")
        self.assertIn("--host 127.0.0.1", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("Restart=always", unit)

    def test_kiosk_targets_read_only_wall(self) -> None:
        kiosk = (ROOT / "bin/ntc-ops-wall-kiosk").read_text(encoding="utf-8")
        env = (ROOT / "env/ntc-ops-wall.env.example").read_text(encoding="utf-8")
        self.assertIn("--kiosk", kiosk)
        self.assertIn("/opswall", env)
        self.assertIn("lock-enabled false", kiosk)
        self.assertIn("show-banners false", kiosk)
        self.assertIn("dock-fixed false", kiosk)
        self.assertIn("autohide true", kiosk)
        self.assertIn("show-trash false", kiosk)
        self.assertIn("show-mounts false", kiosk)
        self.assertIn("ntc-embossed-background.jpg", kiosk)
        self.assertNotIn("/opsadmin", env)

    def test_installer_deploys_ntc_wallpaper(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        wallpaper = ROOT / "assets/ntc-embossed-background.jpg"

        self.assertTrue(wallpaper.is_file())
        self.assertGreater(wallpaper.stat().st_size, 100_000)
        self.assertIn(
            "/usr/local/share/backgrounds/ntc-embossed-background.jpg",
            installer,
        )

    def test_installer_stages_truenas_automounts_without_credentials(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        templates = [
            ROOT / "systemd/mnt-ntc-MultitrackFiles.mount.template",
            ROOT / "systemd/mnt-ntc-Recordings.mount.template",
        ]

        self.assertIn("cifs-utils", installer)
        self.assertIn('[[ -f /etc/ntc/ntc-smb.credentials ]]', installer)
        self.assertIn("mnt-ntc-MultitrackFiles.automount", installer)
        self.assertIn("mnt-ntc-Recordings.automount", installer)
        self.assertIn('loginctl enable-linger "$OPERATOR_USER"', installer)
        for template in templates:
            content = template.read_text(encoding="utf-8")
            self.assertIn("credentials=/etc/ntc/ntc-smb.credentials", content)
            self.assertIn("uid=@OPERATOR_UID@", content)
            self.assertIn("gid=@OPERATOR_GID@", content)
            self.assertIn("_netdev", content)
            self.assertNotIn("password=", content)

    def test_burn_in_is_explicit_and_bounded(self) -> None:
        burn_in = (ROOT / "bin/ntc-ops-burn-in").read_text(encoding="utf-8")
        desktop = (ROOT / "desktop/ntc-ops-wall.desktop").read_text(encoding="utf-8")
        self.assertIn('--timeout "$DURATION"', burn_in)
        self.assertIn("--verify", burn_in)
        self.assertNotIn("ntc-ops-burn-in", desktop)

    def test_host_report_covers_av_hardware(self) -> None:
        report = (ROOT / "bin/ntc-ops-host-report").read_text(encoding="utf-8")
        self.assertIn("lspci -nnk", report)
        self.assertIn("ethtool", report)
        self.assertIn("org.gnome.Mutter.DisplayConfig.GetCurrentState", report)
        self.assertIn("xrandr --current", report)
        self.assertIn("glxinfo -B", report)
        self.assertIn("smartctl", report)
        self.assertIn("sensors", report)

    def test_physical_interface_forwarding_is_blocked_after_docker(self) -> None:
        script = (
            ROOT / "bin/ntc-ops-block-physical-forwarding"
        ).read_text(encoding="utf-8")
        unit = (
            ROOT / "systemd/ntc-ops-block-physical-forwarding.service"
        ).read_text(encoding="utf-8")

        self.assertIn("/sys/class/net/*", script)
        self.assertIn("iptables -C DOCKER-USER", script)
        self.assertIn("-j DROP", script)
        self.assertIn("After=network-online.target docker.service tailscaled.service", unit)
        self.assertIn("RemainAfterExit=yes", unit)


if __name__ == "__main__":
    unittest.main()
