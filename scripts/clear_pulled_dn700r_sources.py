#!/usr/bin/env python3
"""Clear DN700R source files after the NAS-side pulled copy is verified."""

from __future__ import annotations

import argparse
import fcntl
import ftplib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

AUTOSYNCMIX_RECORDER_SCRIPTS = Path("/root/NTC-AutoSyncMix/scripts/recorders")
if str(AUTOSYNCMIX_RECORDER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTOSYNCMIX_RECORDER_SCRIPTS))

import staged_recorder_sync as sync  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_text(row: sqlite3.Row, key: str) -> str:
    if key not in row.keys():
        return ""
    return str(row[key] or "")


def _verified_local_copy_reason(row: sqlite3.Row) -> str:
    """Return why the local copy is safe, or an empty string when it is not."""
    status = _row_text(row, "status")
    if status in {"staged", "duplicate"} and sync.row_path_hash_matches(row, "staged_path"):
        return "verified staged copy"
    if status == "already_archived" and sync.row_path_hash_matches(row, "matched_path"):
        return "verified archived copy"
    if status == "already_archived" and sync.row_path_hash_matches(row, "staged_path"):
        return "verified staged copy for archived row"
    return ""


def _delete_denon_ftp_source(source: dict, source_path: str, prepared_sources: dict[str, str]) -> tuple[bool, str]:
    try:
        return sync.delete_denon_ftp_source_file(source, source_path)
    except ftplib.error_perm as exc:
        if "not idle status" not in str(exc).lower():
            raise
        source_name = str(source["name"])
        if source_name not in prepared_sources:
            prepared_sources[source_name] = sync.prepare_denon_ftp_source_for_clear(source)
        ok, raw = sync.delete_denon_ftp_source_file(source, source_path)
        return ok, f"{raw}; {prepared_sources[source_name]}"


def _clear_sources(config: dict, *, limit: int | None, apply: bool) -> dict[str, int]:
    counts = {"checked": 0, "verified": 0, "deleted": 0, "skipped": 0, "errors": 0}
    sources = {str(source["name"]): source for source in sync.enabled_sources(config)}
    prepared_sources: dict[str, str] = {}
    with sync.connect_database(config) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM recorder_files
            WHERE source_path != ''
              AND COALESCE(source_cleared_at, '') = ''
              AND status IN ('staged', 'already_archived', 'duplicate')
            ORDER BY source_name, source_path
            """
        ).fetchall()
        candidates: list[tuple[sqlite3.Row, dict, str]] = []
        for row in rows:
            counts["checked"] += 1
            source = sources.get(_row_text(row, "source_name"))
            if not source or source.get("type") != "denon_ftp":
                counts["skipped"] += 1
                continue
            source_path = _row_text(row, "source_path")
            if not source_path.startswith("/"):
                counts["skipped"] += 1
                if apply:
                    connection.execute(
                        "UPDATE recorder_files SET source_clear_result = ?, last_seen_at = ? WHERE id = ?",
                        ("cannot clear source before absolute FTP path is known", utc_now(), row["id"]),
                    )
                continue
            reason = _verified_local_copy_reason(row)
            if not reason:
                counts["skipped"] += 1
                if apply:
                    connection.execute(
                        "UPDATE recorder_files SET source_clear_result = ?, last_seen_at = ? WHERE id = ?",
                        ("source retained: NAS copy hash was not verified", utc_now(), row["id"]),
                    )
                continue
            counts["verified"] += 1
            candidates.append((row, source, reason))

        if limit is not None:
            candidates = candidates[: max(0, limit)]

        for row, source, reason in candidates:
            source_path = _row_text(row, "source_path")
            if not apply:
                counts["deleted"] += 1
                print(f"would delete {source['name']}:{source_path} ({reason})")
                continue
            try:
                ok, raw = _delete_denon_ftp_source(source, source_path, prepared_sources)
                if not ok:
                    raise RuntimeError(raw or "DN700R FTP delete was not acknowledged")
                counts["deleted"] += 1
                connection.execute(
                    """
                    UPDATE recorder_files
                    SET source_cleared_at = ?,
                        source_clear_result = ?,
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (utc_now(), f"{raw}; {reason}", utc_now(), row["id"]),
                )
            except (OSError, RuntimeError, ValueError, ftplib.Error) as exc:
                if "source cleanup deferred" in str(exc).lower():
                    counts["skipped"] += 1
                    connection.execute(
                        "UPDATE recorder_files SET source_clear_result = ?, last_seen_at = ? WHERE id = ?",
                        (str(exc), utc_now(), row["id"]),
                    )
                    continue
                counts["errors"] += 1
                connection.execute(
                    "UPDATE recorder_files SET source_clear_result = ?, last_seen_at = ? WHERE id = ?",
                    (f"delete failed for {source_path}: {exc}", utc_now(), row["id"]),
                )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear verified source files from a DN700R FTP recorder.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--lock", type=Path, help="Pipeline lock to share with the sync/promote job.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true", help="Actually delete files from the DN700R. Without this, dry-run only.")
    args = parser.parse_args()

    lock_handle = None
    if args.lock:
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = args.lock.open("a+")
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"cleanup skipped: pipeline lock held at {args.lock}")
            return 0

    config = sync.load_config(args.config)
    counts = _clear_sources(config, limit=args.limit, apply=args.apply)
    mode = "deleted" if args.apply else "would delete"
    print(
        "source cleanup complete: "
        f"{counts['checked']} checked, {counts['verified']} verified, "
        f"{counts['deleted']} {mode}, {counts['skipped']} skipped, {counts['errors']} errors"
    )
    if lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
