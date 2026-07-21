#!/usr/bin/env python3
"""Mirror CVAV DN700R staged files into a visible review/source folder."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cvav_visible_files (
            recorder_file_id INTEGER PRIMARY KEY,
            visible_path TEXT NOT NULL,
            visible_sha256 TEXT NOT NULL,
            mirrored_at TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT ''
        )
        """
    )


def clean_relative_path(value: str) -> Path:
    candidate = Path(value or "").as_posix().lstrip("/")
    parts = [part for part in Path(candidate).parts if part not in {"", ".", ".."}]
    if not parts:
        raise ValueError("empty source-relative path")
    return Path(*parts)


def destination_for(row: sqlite3.Row, dest_root: Path) -> Path:
    source_name = str(row["source_name"] or "unknown-source").strip() or "unknown-source"
    return dest_root / source_name / clean_relative_path(str(row["source_relative_path"] or ""))


def unique_destination(path: Path, row_id: int) -> Path:
    stem = path.stem
    suffix = path.suffix
    candidate = path.with_name(f"{stem}__row{row_id}{suffix}")
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = path.with_name(f"{stem}__row{row_id}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def copy_verified(src: Path, dest: Path, expected_hash: str, row_id: int) -> tuple[Path, str, str]:
    source_hash = sha256_file(src)
    if expected_hash and source_hash != expected_hash:
        return dest, source_hash, f"source hash mismatch: expected {expected_hash}, got {source_hash}"

    if dest.exists():
        existing_hash = sha256_file(dest)
        if existing_hash == source_hash:
            return dest, source_hash, "already mirrored"
        dest = unique_destination(dest, row_id)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(dest.parent), prefix=f".{dest.name}.", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy2(src, tmp_path)
        copied_hash = sha256_file(tmp_path)
        if copied_hash != source_hash:
            return dest, copied_hash, f"copied hash mismatch: expected {source_hash}, got {copied_hash}"
        tmp_path.replace(dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return dest, source_hash, "mirrored"


def mirror_files(manifest: Path, dest_root: Path, limit: int | None, apply: bool) -> dict[str, int]:
    counts = {"checked": 0, "mirrored": 0, "already": 0, "missing": 0, "errors": 0}
    with sqlite3.connect(manifest) as connection:
        connection.row_factory = sqlite3.Row
        ensure_schema(connection)
        query = """
            SELECT id, source_name, source_relative_path, staged_path, sha256
            FROM recorder_files
            WHERE COALESCE(staged_path, '') <> ''
            ORDER BY first_seen_at, id
        """
        rows = connection.execute(query).fetchall()
        if limit is not None:
            rows = rows[: max(0, limit)]

        for row in rows:
            counts["checked"] += 1
            row_id = int(row["id"])
            src = Path(str(row["staged_path"] or ""))
            try:
                if not src.exists() or not src.is_file():
                    counts["missing"] += 1
                    if apply:
                        connection.execute(
                            """
                            INSERT INTO cvav_visible_files
                                (recorder_file_id, visible_path, visible_sha256, mirrored_at, result)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(recorder_file_id) DO UPDATE SET
                                result = excluded.result,
                                mirrored_at = excluded.mirrored_at
                            """,
                            (row_id, "", "", utc_now(), f"staged file missing: {src}"),
                        )
                    continue
                dest = destination_for(row, dest_root)
                dest, file_hash, result = copy_verified(src, dest, str(row["sha256"] or ""), row_id)
                if result == "already mirrored":
                    counts["already"] += 1
                elif result == "mirrored":
                    counts["mirrored"] += 1
                else:
                    counts["errors"] += 1
                if apply:
                    connection.execute(
                        """
                        INSERT INTO cvav_visible_files
                            (recorder_file_id, visible_path, visible_sha256, mirrored_at, result)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(recorder_file_id) DO UPDATE SET
                            visible_path = excluded.visible_path,
                            visible_sha256 = excluded.visible_sha256,
                            mirrored_at = excluded.mirrored_at,
                            result = excluded.result
                        """,
                        (row_id, str(dest), file_hash, utc_now(), result),
                    )
            except Exception as exc:  # noqa: BLE001 - keep mirror robust per row.
                counts["errors"] += 1
                if apply:
                    connection.execute(
                        """
                        INSERT INTO cvav_visible_files
                            (recorder_file_id, visible_path, visible_sha256, mirrored_at, result)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(recorder_file_id) DO UPDATE SET
                            result = excluded.result,
                            mirrored_at = excluded.mirrored_at
                        """,
                        (row_id, "", "", utc_now(), f"mirror failed: {exc}"),
                    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror CVAV DN700R staged files into visible storage.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dest-root", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    counts = mirror_files(args.manifest, args.dest_root, args.limit, args.apply)
    mode = "applied" if args.apply else "dry-run"
    print(
        f"cvav review mirror {mode}: "
        f"{counts['checked']} checked, {counts['mirrored']} mirrored, "
        f"{counts['already']} already, {counts['missing']} missing, {counts['errors']} errors"
    )
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
