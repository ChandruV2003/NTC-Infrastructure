#!/usr/bin/env python3
"""Analyze recorder manifest rows for message/testimony/worship segments.

This is intentionally advisory. It does not move, split, promote, delete, or
rename audio. The recorder pipeline owns file movement; this records a
deterministic "shape" pass that UIs and later agent steps can use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ANALYSIS_VERSION = 1

WINDOW_RE = re.compile(r"(?m)^\[(start|\+\d+s)\]\s*")

GENERIC_TRANSCRIPTION_PROMPTS = (
    "preserve any speaker names",
    "noise-snippet",
    "this recording is a work of fiction",
    "any resemblance to actual persons",
)

MESSAGE_PATTERNS = (
    r"\bturn (with me )?(to|your bibles to)\b",
    r"\bopen (your )?bibles?\b",
    r"\bscripture\b",
    r"\bword of god\b",
    r"\bmessage\b",
    r"\bsermon\b",
    r"\bpreach(?:ed|ing)?\b",
    r"\bbook of\b",
    r"\bchapter\b",
    r"\bverse\b",
    r"\bthe bible says\b",
    r"\bsubject\b",
    r"\btitle\b",
    r"\bbe seated\b",
)

TESTIMONY_PATTERNS = (
    r"\btestif(?:y|ies|ied|ying)\b",
    r"\btestimony\b",
    r"\bmy name is\b",
    r"\bfor those (of you )?who do not know me\b",
    r"\bi am (brother|sister)\b",
    r"\bi want to (thank|praise)\b",
    r"\bi thank and praise god\b",
    r"\bgod (has|had|did|was) (done|been|helped|healed|provided|faithful)\b",
    r"\bin my life\b",
    r"\bwhen i\b",
    r"\bi was\b",
)

WORSHIP_PATTERNS = (
    r"\blet us (sing|worship|praise)\b",
    r"\bwe are going to sing\b",
    r"\bsong\b",
    r"\bchorus\b",
    r"\bhymn\b",
    r"\bworship\b",
    r"\bhallelujah\b",
    r"\bpraise the lord\b",
    r"\bthank you jesus\b",
    r"\bglory to god\b",
    r"\bamen\b",
)

NOISE_PATTERNS = (
    r"^\W*$",
    r"^thank you\.?$",
    r"^testing\b",
    r"^\.+$",
)


@dataclass(frozen=True)
class Window:
    label: str
    start_seconds: float
    text: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recorder_segment_analysis (
            recorder_file_id INTEGER PRIMARY KEY,
            lane_label TEXT NOT NULL,
            analysis_version INTEGER NOT NULL DEFAULT 1,
            analysis_status TEXT NOT NULL,
            file_kind TEXT NOT NULL,
            combined_likelihood REAL NOT NULL DEFAULT 0,
            segment_count INTEGER NOT NULL DEFAULT 0,
            segments_json TEXT NOT NULL DEFAULT '[]',
            reasons_json TEXT NOT NULL DEFAULT '[]',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            transcript_hash TEXT NOT NULL DEFAULT '',
            analyzed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_analysis_kind ON recorder_segment_analysis(file_kind)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_analysis_analyzed_at ON recorder_segment_analysis(analyzed_at)"
    )


def transcript_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def marker_to_seconds(label: str) -> float:
    if label == "start":
        return 0.0
    if label.startswith("+") and label.endswith("s"):
        try:
            return float(label[1:-1])
        except ValueError:
            return 0.0
    return 0.0


def parse_windows(transcript: str) -> list[Window]:
    text = transcript or ""
    matches = list(WINDOW_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        return [Window("start", 0.0, stripped)] if stripped else []

    windows: list[Window] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[match.end() : next_start].strip()
        if chunk:
            label = match.group(1)
            windows.append(Window(label, marker_to_seconds(label), chunk))
    return windows


def pattern_hits(patterns: Iterable[str], text: str) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text):
            hits.append(pattern)
    return hits


def repeated_word_score(text: str, words: Iterable[str]) -> int:
    score = 0
    for word in words:
        count = text.count(word)
        if count >= 3:
            score += min(count, 8)
    return score


def classify_window(window: Window, duration_seconds: float | None) -> dict:
    clean = normalize_text(window.text)
    prompt_hits = [item for item in GENERIC_TRANSCRIPTION_PROMPTS if item in clean]
    noise_hits = pattern_hits(NOISE_PATTERNS, clean)
    message_hits = pattern_hits(MESSAGE_PATTERNS, clean)
    testimony_hits = pattern_hits(TESTIMONY_PATTERNS, clean)
    worship_hits = pattern_hits(WORSHIP_PATTERNS, clean)

    scores = {
        "noise": 0,
        "message": len(message_hits) * 3,
        "testimony": len(testimony_hits) * 3,
        "worship": len(worship_hits) * 2,
    }
    if prompt_hits:
        scores["noise"] += 6
    if noise_hits:
        scores["noise"] += 8
    if len(clean) < 35:
        scores["noise"] += 4
    scores["worship"] += repeated_word_score(clean, ("hallelujah", "praise the lord", "amen"))

    if window.start_seconds == 0 and duration_seconds and duration_seconds >= 1500:
        # Long files often start with worship or opening prayer. Avoid letting
        # the first window dominate a later message segment.
        scores["message"] += 1 if message_hits else 0

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    kind, score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if score <= 0:
        kind = "unknown"
        confidence = 0.25
    else:
        confidence = min(0.96, 0.45 + (score - second_score) * 0.08 + score * 0.02)

    evidence: list[str] = []
    if prompt_hits:
        evidence.append("transcription prompt/generic text detected")
    if noise_hits:
        evidence.append("very short or empty transcript")
    if message_hits:
        evidence.append("message language: " + ", ".join(message_hits[:3]))
    if testimony_hits:
        evidence.append("testimony language: " + ", ".join(testimony_hits[:3]))
    if worship_hits:
        evidence.append("worship language: " + ", ".join(worship_hits[:3]))
    return {
        "kind": kind,
        "confidence": round(confidence, 2),
        "score": score,
        "scores": scores,
        "evidence": evidence[:6],
        "label": window.label,
        "start_seconds": window.start_seconds,
    }


def collapse_segments(segments: list[dict], duration_seconds: float | None) -> list[dict]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: item["start_seconds"])
    collapsed: list[dict] = []
    for segment in ordered:
        if collapsed and collapsed[-1]["kind"] == segment["kind"]:
            collapsed[-1]["end_seconds"] = segment.get("end_seconds")
            collapsed[-1]["confidence"] = max(collapsed[-1]["confidence"], segment["confidence"])
            collapsed[-1]["evidence"] = (collapsed[-1]["evidence"] + segment["evidence"])[:8]
            continue
        collapsed.append(dict(segment))
    for index, segment in enumerate(collapsed):
        if index + 1 < len(collapsed):
            segment["end_seconds"] = collapsed[index + 1]["start_seconds"]
        elif duration_seconds:
            segment["end_seconds"] = float(duration_seconds)
        else:
            segment["end_seconds"] = None
    return collapsed


def file_kind_from_segments(
    row: sqlite3.Row,
    segments: list[dict],
) -> tuple[str, float, list[str], list[str]]:
    duration = row["duration_seconds"]
    classification = normalize_text(str(row["classification"] or ""))
    reasons: list[str] = []
    warnings: list[str] = []

    if duration is not None and float(duration) <= 45:
        return "noise", 0.0, ["duration <= 45 seconds"], []

    non_noise = [segment for segment in segments if segment["kind"] not in {"noise", "unknown"}]
    kinds = {segment["kind"] for segment in non_noise}

    if "worship" in classification:
        reasons.append("existing classifier marked worship")
    if "message" in classification:
        reasons.append("existing classifier marked message")
    if "testimony" in classification:
        reasons.append("existing classifier marked testimony")

    if len(kinds) >= 2:
        likelihood = 0.78
        if duration and float(duration) >= 1800:
            likelihood = 0.88
        warnings.append("multiple recording types appear in the transcript windows")
        return "combined", likelihood, reasons + [f"detected segment kinds: {', '.join(sorted(kinds))}"], warnings

    if "message" in kinds:
        if duration and float(duration) >= 1800 and any(segment["kind"] == "worship" for segment in segments[:1]):
            return "combined", 0.72, reasons + ["long file starts with worship/opening material"], warnings
        return "message", 0.0, reasons + ["message segment evidence dominates"], warnings
    if "testimony" in kinds:
        return "testimony", 0.0, reasons + ["testimony segment evidence dominates"], warnings
    if "worship" in kinds:
        return "worship", 0.0, reasons + ["worship segment evidence dominates"], warnings

    if "noise" in classification:
        return "noise", 0.0, reasons + ["existing classifier marked noise/snippet"], warnings
    return "unknown", 0.0, reasons + ["insufficient transcript evidence"], warnings


def analyze_row(row: sqlite3.Row, lane_label: str) -> dict:
    duration = row["duration_seconds"]
    transcript = str(row["transcript_text"] or "")
    windows = parse_windows(transcript)
    raw_segments: list[dict] = []
    for window in windows:
        result = classify_window(window, duration)
        snippet = re.sub(r"\s+", " ", window.text).strip()
        result["snippet"] = snippet[:220]
        raw_segments.append(result)

    segments = collapse_segments(raw_segments, duration)
    kind, combined_likelihood, reasons, warnings = file_kind_from_segments(row, segments)
    status = "analyzed" if transcript.strip() or duration is not None else "missing_transcript"
    return {
        "recorder_file_id": int(row["id"]),
        "lane_label": lane_label,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_status": status,
        "file_kind": kind,
        "combined_likelihood": round(combined_likelihood, 2),
        "segment_count": len(segments),
        "segments_json": json.dumps(segments, ensure_ascii=False, sort_keys=True),
        "reasons_json": json.dumps(reasons, ensure_ascii=False, sort_keys=True),
        "warnings_json": json.dumps(warnings, ensure_ascii=False, sort_keys=True),
        "transcript_hash": transcript_hash(transcript),
        "analyzed_at": utc_now(),
    }


def row_needs_analysis(row: sqlite3.Row, existing: sqlite3.Row | None) -> bool:
    if existing is None:
        return True
    if int(existing["analysis_version"] or 0) != ANALYSIS_VERSION:
        return True
    return str(existing["transcript_hash"] or "") != transcript_hash(str(row["transcript_text"] or ""))


def analyze_manifest(manifest: Path, lane_label: str, limit: int | None, apply: bool) -> dict[str, int]:
    counts = {"checked": 0, "analyzed": 0, "unchanged": 0, "errors": 0}
    with sqlite3.connect(manifest) as connection:
        connection.row_factory = sqlite3.Row
        ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT id, source_name, source_relative_path, duration_seconds,
                   classification, status, transcript_text
            FROM recorder_files
            WHERE COALESCE(staged_path, '') <> ''
               OR COALESCE(transcript_text, '') <> ''
               OR COALESCE(status, '') IN ('already_archived', 'source_cleared')
            ORDER BY id DESC
            """
        ).fetchall()
        if limit is not None:
            rows = rows[: max(0, limit)]

        for row in rows:
            counts["checked"] += 1
            try:
                existing = connection.execute(
                    """
                    SELECT analysis_version, transcript_hash
                    FROM recorder_segment_analysis
                    WHERE recorder_file_id = ?
                    """,
                    (int(row["id"]),),
                ).fetchone()
                if not row_needs_analysis(row, existing):
                    counts["unchanged"] += 1
                    continue

                payload = analyze_row(row, lane_label)
                counts["analyzed"] += 1
                if apply:
                    connection.execute(
                        """
                        INSERT INTO recorder_segment_analysis (
                            recorder_file_id, lane_label, analysis_version, analysis_status,
                            file_kind, combined_likelihood, segment_count, segments_json,
                            reasons_json, warnings_json, transcript_hash, analyzed_at
                        )
                        VALUES (
                            :recorder_file_id, :lane_label, :analysis_version, :analysis_status,
                            :file_kind, :combined_likelihood, :segment_count, :segments_json,
                            :reasons_json, :warnings_json, :transcript_hash, :analyzed_at
                        )
                        ON CONFLICT(recorder_file_id) DO UPDATE SET
                            lane_label = excluded.lane_label,
                            analysis_version = excluded.analysis_version,
                            analysis_status = excluded.analysis_status,
                            file_kind = excluded.file_kind,
                            combined_likelihood = excluded.combined_likelihood,
                            segment_count = excluded.segment_count,
                            segments_json = excluded.segments_json,
                            reasons_json = excluded.reasons_json,
                            warnings_json = excluded.warnings_json,
                            transcript_hash = excluded.transcript_hash,
                            analyzed_at = excluded.analyzed_at
                        """,
                        payload,
                    )
            except Exception as exc:  # noqa: BLE001 - keep per-row diagnostics robust.
                counts["errors"] += 1
                print(f"row {row['id']} failed: {exc}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze recorder manifest rows for segment shape.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--lane-label", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}")
        return 2
    counts = analyze_manifest(args.manifest, args.lane_label, args.limit, args.apply)
    mode = "applied" if args.apply else "dry-run"
    print(
        f"recorder segment analyzer {mode}: "
        f"{counts['checked']} checked, {counts['analyzed']} analyzed, "
        f"{counts['unchanged']} unchanged, {counts['errors']} errors"
    )
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
