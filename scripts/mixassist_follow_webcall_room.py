#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


POLL_SECONDS = float(os.getenv("MIXASSIST_WEBCALL_FOLLOW_POLL_SECONDS", "2.0"))
HEALTHZ_URL = os.getenv("MIXASSIST_WEBCALL_HEALTHZ_URL", "http://127.0.0.1:1967/healthz")
PCM_ROOT = Path(os.getenv("MIXASSIST_WEBCALL_PCM_ROOT", "/root/NTC-Runtime/shared-pcm"))
RUN_DIR = Path(os.getenv("MIXASSIST_RUN_DIR", "/run/ntc-mixassist"))
AES67_ENV = RUN_DIR / "aes67.env"
APP_ENV = RUN_DIR / "app-source.env"
STATE_PATH = RUN_DIR / "webcall-follow-state.json"
STALE_SECONDS = float(os.getenv("MIXASSIST_WEBCALL_STATE_STALE_SECONDS", "30.0"))
IDLE_LABEL = os.getenv("MIXASSIST_IDLE_SOURCE_LABEL", "No active WebCall room")


ROOM_CONFIG = {
    "room-a": {
        "label": os.getenv("MIXASSIST_ROOM_A_LABEL", "Room A LR (Q-SYS NTC-LR)"),
        "sdp": os.getenv("MIXASSIST_ROOM_A_SDP", "/app/data/aes67/qsys-ntc-lr.sdp"),
        "channel_pair": os.getenv("MIXASSIST_ROOM_A_CHANNEL_PAIR", "1,2"),
    },
    "room-b": {
        "label": os.getenv("MIXASSIST_ROOM_B_LABEL", "Room B Stream LR"),
        "sdp": os.getenv("MIXASSIST_ROOM_B_SDP", "/app/data/aes67/room-b.sdp"),
        "channel_pair": os.getenv("MIXASSIST_ROOM_B_CHANNEL_PAIR", ""),
    },
}


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    last_room = ""
    while True:
        room = active_room()
        if room and room != last_room:
            apply_room(room)
            last_room = room
        elif room and env_missing_or_stale(room):
            apply_room(room)
            last_room = room
        elif not room and (last_room or current_state_room()):
            clear_room()
            last_room = ""
        time.sleep(POLL_SECONDS)


def active_room() -> str:
    room = active_room_from_healthz()
    if room:
        return room
    return active_room_from_pcm_state()


def active_room_from_healthz() -> str:
    try:
        with urlopen(HEALTHZ_URL, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""

    active_call_rooms = payload.get("active_call_rooms")
    if isinstance(active_call_rooms, list):
        for room in active_call_rooms:
            if room in ROOM_CONFIG:
                return room
        return ""

    for key in ("ingesting_rooms", "active_rooms"):
        rooms = payload.get(key)
        if not isinstance(rooms, list):
            continue
        for room in rooms:
            if room in ROOM_CONFIG:
                return room
    return ""


def active_room_from_pcm_state() -> str:
    candidates = []
    now = datetime.now(timezone.utc)
    for room in ROOM_CONFIG:
        state = read_json(PCM_ROOT / room / "state.json")
        if not state.get("active"):
            continue
        updated_at = parse_time(state.get("updated_at"))
        if updated_at and (now - updated_at).total_seconds() > STALE_SECONDS:
            continue
        candidates.append((room, updated_at or datetime.min.replace(tzinfo=timezone.utc)))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def apply_room(room: str):
    config = ROOM_CONFIG[room]
    write_env(
        AES67_ENV,
        {
            "MIXASSIST_AES67_SDP": config["sdp"],
            "MIXASSIST_AES67_SOURCE_LABEL": config["label"],
            "MIXASSIST_AES67_CHANNEL_PAIR": config["channel_pair"],
        },
    )
    write_env(APP_ENV, {"MIXASSIST_UDP_SOURCE_LABEL": config["label"]})
    write_json(
        STATE_PATH,
        {
            "room": room,
            "label": config["label"],
            "sdp": config["sdp"],
            "channel_pair": config["channel_pair"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    restart_analysis_services()


def clear_room():
    write_env(APP_ENV, {"MIXASSIST_UDP_SOURCE_LABEL": IDLE_LABEL})
    write_json(
        STATE_PATH,
        {
            "room": "",
            "label": IDLE_LABEL,
            "sdp": "",
            "channel_pair": "",
            "active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    stop_analysis_feed()


def restart_analysis_services():
    subprocess.run(["systemctl", "restart", "ntc-mixassist.service"], timeout=20, check=False)
    subprocess.run(["systemctl", "restart", "ntc-mixassist-aes67.service"], timeout=20, check=False)


def stop_analysis_feed():
    subprocess.run(["systemctl", "stop", "ntc-mixassist-aes67.service"], timeout=20, check=False)
    subprocess.run(["systemctl", "restart", "ntc-mixassist.service"], timeout=20, check=False)


def env_missing_or_stale(room: str) -> bool:
    if not AES67_ENV.exists() or not APP_ENV.exists() or not STATE_PATH.exists():
        return True
    state = read_json(STATE_PATH)
    return state.get("room") != room


def current_state_room() -> str:
    state = read_json(STATE_PATH)
    room = state.get("room")
    if isinstance(room, str):
        return room
    return ""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_json(path: Path, payload: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def write_env(path: Path, values: dict[str, str]):
    tmp = path.with_suffix(path.suffix + ".tmp")
    lines = [f'{key}="{escape_env(value)}"' for key, value in values.items()]
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


def escape_env(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
