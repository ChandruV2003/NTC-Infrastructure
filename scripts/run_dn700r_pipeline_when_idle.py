#!/usr/bin/env python3
"""Run a DN700R recorder pipeline only when the transport is idle."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

AUTOSYNCMIX_RECORDER_SCRIPTS = Path("/root/NTC-AutoSyncMix/scripts/recorders")
if str(AUTOSYNCMIX_RECORDER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTOSYNCMIX_RECORDER_SCRIPTS))

import staged_recorder_sync as sync  # noqa: E402

RECORDING_STATUS_CODES = {"STRC", "STRP", "STRE"}
STATUS_LABELS = {
    "STST": "stopped",
    "STPL": "playing",
    "STPA": "paused",
    "STCE": "cue",
    "STCU": "cue",
    "STRC": "recording",
    "STRP": "recording paused",
    "STRE": "recording",
}


def denon_sources(config: dict) -> list[dict]:
    return [
        source
        for source in sync.enabled_sources(config)
        if source.get("type") == "denon_ftp"
    ]


def status_label(code: str, raw: str) -> str:
    label = STATUS_LABELS.get(code, code or "unknown")
    return f"{label} ({raw})" if raw else label


def recorder_is_busy(config: dict, *, label: str) -> bool:
    sources = denon_sources(config)
    if not sources:
        print(f"[{label}] idle guard skipped: no enabled DN700R FTP sources in config")
        return False

    busy = False
    for source in sources:
        source_name = str(source.get("name") or "DN700R")
        try:
            code, raw = sync.query_denon_transport_status(source)
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                f"[{label}] idle guard: {source_name} status unavailable; "
                f"skipping pipeline so recording priority is preserved: {exc}"
            )
            return True
        print(f"[{label}] idle guard: {source_name} status {status_label(code, raw)}")
        if code in RECORDING_STATUS_CODES:
            busy = True
    return busy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skip DN700R sync/promote while the recorder is actively recording."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--label", default="DN700R")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if not args.command:
        parser.error("command to run is required after --")
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command to run is required after --")

    config = sync.load_config(args.config)
    if recorder_is_busy(config, label=args.label):
        print(f"[{args.label}] pipeline skipped: recorder is busy or status is unavailable")
        return 0

    if args.dry_run:
        print(f"[{args.label}] dry run: would execute {' '.join(command)}")
        return 0

    completed = subprocess.run(command, env=os.environ.copy(), check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
