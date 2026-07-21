#!/usr/bin/env python3
"""Run a DN700R recorder pipeline only when the transport is idle."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
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


def denon_sources(config: dict, *, timeout_seconds: float, attempts: int) -> list[dict]:
    sources = [
        source
        for source in sync.enabled_sources(config)
        if source.get("type") == "denon_ftp"
    ]
    guard_sources: list[dict] = []
    for source in sources:
        guard_source = dict(source)
        guard_source["serial_timeout_seconds"] = timeout_seconds
        guard_source["serial_attempts"] = attempts
        guard_source["serial_retry_sleep_seconds"] = 0
        guard_sources.append(guard_source)
    return guard_sources


def status_label(code: str, raw: str) -> str:
    label = STATUS_LABELS.get(code, code or "unknown")
    return f"{label} ({raw})" if raw else label


def recorder_state(config: dict, *, label: str, timeout_seconds: float, attempts: int) -> str:
    sources = denon_sources(config, timeout_seconds=timeout_seconds, attempts=attempts)
    if not sources:
        print(f"[{label}] idle guard skipped: no enabled DN700R FTP sources in config")
        return "idle"

    state = "idle"
    for source in sources:
        source_name = str(source.get("name") or "DN700R")
        try:
            code, raw = sync.query_denon_transport_status(source)
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                f"[{label}] idle guard: {source_name} status unavailable; "
                f"recording priority check could not confirm idle: {exc}"
            )
            return "unavailable"
        print(f"[{label}] idle guard: {source_name} status {status_label(code, raw)}")
        if code in RECORDING_STATUS_CODES:
            state = "busy"
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skip DN700R sync/promote while the recorder is actively recording."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--label", default="DN700R")
    parser.add_argument("--active-check-interval", type=float, default=2.0)
    parser.add_argument("--active-unavailable-strikes", type=int, default=6)
    parser.add_argument("--status-timeout", type=float, default=1.2)
    parser.add_argument("--status-attempts", type=int, default=1)
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
    initial_state = recorder_state(
        config,
        label=args.label,
        timeout_seconds=args.status_timeout,
        attempts=args.status_attempts,
    )
    if initial_state != "idle":
        print(f"[{args.label}] pipeline skipped: recorder is {initial_state}")
        return 0

    if args.dry_run:
        print(f"[{args.label}] dry run: would execute {' '.join(command)}")
        return 0

    process = subprocess.Popen(command, env=os.environ.copy(), start_new_session=True)
    unavailable_strikes = 0
    while process.poll() is None:
        time.sleep(max(0.5, args.active_check_interval))
        if process.poll() is not None:
            break
        active_state = recorder_state(
            config,
            label=args.label,
            timeout_seconds=args.status_timeout,
            attempts=args.status_attempts,
        )
        if active_state == "idle":
            unavailable_strikes = 0
            continue
        if active_state == "unavailable":
            unavailable_strikes += 1
            max_strikes = max(1, args.active_unavailable_strikes)
            print(
                f"[{args.label}] idle guard: status unavailable during active pull "
                f"({unavailable_strikes}/{max_strikes}); letting current transfer continue"
            )
            if unavailable_strikes < max_strikes:
                continue

        if active_state in {"busy", "unavailable"}:
            print(
                f"[{args.label}] pipeline interrupted: recorder became {active_state} "
                "while the pull/promote job was running"
            )
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            return 0
    return int(process.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
