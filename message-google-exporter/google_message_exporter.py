#!/usr/bin/env python3
"""Temporary Google Drive exporter for polished NTC message recordings.

The NAS message library remains the source of truth. This script only mirrors
eligible, already-promoted message files to a scoped Google Drive rclone remote.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
MONTH_RE = "|".join(MONTHS)

DEFAULT_SOURCE_ROOT = Path("/mnt/MainRecordings/Recordings/MessageRecordings")
DEFAULT_REMOTE = "ntc-message-recordings-drive:"
DEFAULT_STATE_DB = Path("/root/NTC-Runtime/google-message-exporter/manifest.sqlite3")

EXCLUDED_PARTS = {
    "DN300R",
    "GoogleMessageTakeout",
    "_IncomingRecorderIntake",
    "_NeedsDate",
    "Sunday Testimonies",
    "Sunday Worship Services",
}


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative_path: str
    size: int
    mtime: float
    service_date: str
    destination_path: str


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    service_date: Optional[str]


def run_cmd(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def parse_date_from_name(name: str) -> tuple[Optional[str], str]:
    stem = Path(name).stem
    match = re.match(r"^(20\d{2})(\d{2})(\d{2})\s*-\s*(.+)$", stem)
    if match:
        year, month, day, rest = match.groups()
        return f"{year}-{month}-{day}", rest.strip()

    match = re.match(r"^(\d{2})(\d{2})(20\d{2})\s*-\s*(.+)$", stem)
    if match:
        month, day, year, rest = match.groups()
        return f"{year}-{month}-{day}", rest.strip()

    match = re.match(rf"^({MONTH_RE})\s+(\d{{1,2}}),\s*(20\d{{2}})\s*-\s*(.+)$", stem)
    if match:
        month_name, day, year, rest = match.groups()
        return f"{year}-{MONTHS[month_name]:02d}-{int(day):02d}", rest.strip()

    return None, stem.strip()


def yyyymmdd(service_date: str) -> str:
    return service_date.replace("-", "")


def remote_join(root: str, relative_path: str) -> str:
    if root.endswith(":") or root.endswith("/"):
        return root + relative_path
    return root + "/" + relative_path


def eligible_path(path: Path, source_root: Path, min_year: int, extensions: set[str]) -> Optional[SourceFile]:
    try:
        rel_path = path.relative_to(source_root)
    except ValueError:
        return None

    if path.suffix.lower() not in extensions:
        return None

    parts = rel_path.parts
    if any(part in EXCLUDED_PARTS or part.startswith(".") for part in parts):
        return None

    first = parts[0] if parts else ""
    if first != "Combined Wednesday Messages":
        if not re.fullmatch(r"20\d{2}", first):
            return None
        if int(first) < min_year:
            return None

    service_date, remainder = parse_date_from_name(path.name)
    if not service_date:
        return None

    ext = path.suffix.lower()
    destination_name = f"{yyyymmdd(service_date)} - {remainder}{ext}"
    destination = rel_path.parent / destination_name
    stat = path.stat()
    return SourceFile(
        path=path,
        relative_path=rel_path.as_posix(),
        size=stat.st_size,
        mtime=stat.st_mtime,
        service_date=service_date,
        destination_path=destination.as_posix(),
    )


def scan_sources(source_root: Path, min_year: int, extensions: set[str], max_age_days: Optional[int]) -> list[SourceFile]:
    cutoff = None
    if max_age_days is not None:
        cutoff = dt.datetime.now().timestamp() - (max_age_days * 86400)

    out: list[SourceFile] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        if cutoff is not None and path.stat().st_mtime < cutoff:
            continue
        item = eligible_path(path, source_root, min_year, extensions)
        if item:
            out.append(item)
    out.sort(key=lambda item: (item.service_date, item.relative_path))
    return out


def scan_remote(remote_root: str) -> list[RemoteFile]:
    proc = run_cmd(["rclone", "lsf", remote_root, "--recursive", "--files-only", "--format", "pst"], check=False)
    if proc.returncode != 0:
        combined = ((proc.stderr or "") + "\n" + (proc.stdout or "")).lower()
        if "directory not found" in combined or "couldn't find root directory id" in combined:
            return []
        raise subprocess.CalledProcessError(proc.returncode, proc.args, output=proc.stdout, stderr=proc.stderr)
    out: list[RemoteFile] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(";")
        if len(parts) < 2:
            continue
        path = parts[0]
        try:
            size = int(parts[1] or "0")
        except ValueError:
            size = 0
        service_date, _ = parse_date_from_name(Path(path).name)
        out.append(RemoteFile(path=path, size=size, service_date=service_date))
    return out


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exports (
            source_path TEXT PRIMARY KEY,
            destination_path TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            service_date TEXT NOT NULL,
            status TEXT NOT NULL,
            remote_match TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def record(conn: sqlite3.Connection, item: SourceFile, status: str, remote_match: str = "", error: str = "") -> None:
    conn.execute(
        """
        INSERT INTO exports(source_path, destination_path, size, mtime, service_date, status, remote_match, last_error, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            destination_path=excluded.destination_path,
            size=excluded.size,
            mtime=excluded.mtime,
            service_date=excluded.service_date,
            status=excluded.status,
            remote_match=excluded.remote_match,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        (
            item.relative_path,
            item.destination_path,
            item.size,
            item.mtime,
            item.service_date,
            status,
            remote_match,
            error,
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def export_items(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    remote_root = args.remote
    extensions = {ext if ext.startswith(".") else f".{ext}" for ext in args.extensions}
    max_age_days = None if args.full_scan else args.max_age_days

    conn = init_db(Path(args.state_db))
    sources = scan_sources(source_root, args.min_year, extensions, max_age_days)
    if args.limit:
        sources = sources[-args.limit :]

    remote_files = scan_remote(remote_root)
    remote_by_path = {rf.path: rf for rf in remote_files}
    remote_date_size = {(rf.service_date, rf.size): rf for rf in remote_files if rf.service_date}

    exported = existing = alternate = skipped = errors = 0
    for item in sources:
        exact = remote_by_path.get(item.destination_path)
        if exact and exact.size == item.size:
            existing += 1
            record(conn, item, "already_exported", exact.path)
            continue

        same_date_size = remote_date_size.get((item.service_date, item.size))
        if same_date_size:
            alternate += 1
            record(conn, item, "already_present_alternate_name", same_date_size.path)
            continue

        target = remote_join(remote_root, item.destination_path)
        if args.dry_run:
            skipped += 1
            print(f"DRY-RUN upload {item.path} -> {target}")
            record(conn, item, "dry_run_pending", "")
            continue

        try:
            print(f"upload {item.relative_path} -> {item.destination_path}")
            run_cmd([
                "rclone",
                "copyto",
                str(item.path),
                target,
                "--drive-chunk-size",
                args.drive_chunk_size,
            ])
            exported += 1
            record(conn, item, "exported", item.destination_path)
        except subprocess.CalledProcessError as exc:
            errors += 1
            message = ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip()[-1000:]
            print(f"ERROR exporting {item.relative_path}: {message}", file=sys.stderr)
            record(conn, item, "error", "", message)

    print(
        f"checked={len(sources)} exported={exported} existing={existing} "
        f"alternate_name={alternate} dry_run_pending={skipped} errors={errors}"
    )
    return 1 if errors else 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export polished NTC message recordings to Google Drive.")
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB))
    parser.add_argument("--max-age-days", type=int, default=45)
    parser.add_argument("--full-scan", action="store_true")
    parser.add_argument("--min-year", type=int, default=2025)
    parser.add_argument("--extensions", nargs="+", default=[".mp3"])
    parser.add_argument("--drive-chunk-size", default="64M")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return export_items(args)


if __name__ == "__main__":
    raise SystemExit(main())
