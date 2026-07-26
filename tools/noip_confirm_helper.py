#!/usr/bin/env python3
"""No-IP free hostname confirmation helper.

This intentionally uses official links from No-IP email messages. It does not
try to bypass login, CAPTCHA, MFA, or bot checks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email
import html
import imaplib
import json
import os
import re
import shlex
import socket
import ssl
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from email.header import decode_header
from email.message import Message
from pathlib import Path


DEFAULT_HOSTNAME = "ntcnas.myftp.org"
DEFAULT_STATE_DIR = Path("/home/sysadmin/apps/NTC-Infrastructure/state/noip-renew")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 NTC-NoIP-Renew-Helper/1.0"
)

NOIP_LINK_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
HTML_LINK_RE = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}


@dataclass
class CandidateLink:
    url: str
    message_id: str
    subject: str
    sender: str
    received_at: str


@dataclass
class AttemptResult:
    url: str
    status: str
    reason: str
    http_status: int | None = None
    final_url: str | None = None


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def state_dir() -> Path:
    return Path(os.environ.get("NTC_NOIP_STATE_DIR", str(DEFAULT_STATE_DIR)))


def hostname() -> str:
    return os.environ.get("NTC_NOIP_HOSTNAME", DEFAULT_HOSTNAME).strip() or DEFAULT_HOSTNAME


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"processed_urls": {}, "processed_messages": {}, "attempts": []}
    except json.JSONDecodeError:
        return {"processed_urls": {}, "processed_messages": {}, "attempts": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_report(directory: Path, report: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "latest.md").write_text(report, encoding="utf-8")
    (directory / "latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_url(raw_url: str) -> str:
    url = html.unescape(raw_url).strip().rstrip(").,;]")
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key not in TRACKING_KEYS]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def is_noip_candidate(url: str, host: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    netloc = parsed.netloc.lower()
    if not (netloc == "noip.com" or netloc.endswith(".noip.com")):
        return False
    haystack = urllib.parse.unquote(url).lower()
    return any(token in haystack for token in ("confirm", "renew", "hostname", host.lower()))


def extract_urls_from_text(text: str, host: str) -> list[str]:
    urls: list[str] = []
    for match in HTML_LINK_RE.finditer(text):
        urls.append(clean_url(match.group(1)))
    for match in NOIP_LINK_RE.finditer(text):
        urls.append(clean_url(match.group(0)))

    seen: set[str] = set()
    candidates: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        if is_noip_candidate(url, host):
            candidates.append(url)
    return candidates


def message_text_parts(msg: Message) -> str:
    pieces: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            pieces.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            charset = msg.get_content_charset() or "utf-8"
            pieces.append(payload.decode(charset, errors="replace"))
    return "\n".join(pieces)


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    fragments = decode_header(value)
    output: list[str] = []
    for fragment, charset in fragments:
        if isinstance(fragment, bytes):
            output.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            output.append(fragment)
    return "".join(output)


def imap_candidates(host: str) -> list[CandidateLink]:
    imap_host = os.environ.get("NTC_NOIP_IMAP_HOST")
    imap_user = os.environ.get("NTC_NOIP_IMAP_USER")
    imap_password = os.environ.get("NTC_NOIP_IMAP_PASSWORD")
    mailbox = os.environ.get("NTC_NOIP_IMAP_MAILBOX", "INBOX")
    lookback_days = int(os.environ.get("NTC_NOIP_IMAP_LOOKBACK_DAYS", "45"))
    if not (imap_host and imap_user and imap_password):
        return []

    since = (dt.date.today() - dt.timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    context = ssl.create_default_context()
    port = int(os.environ.get("NTC_NOIP_IMAP_PORT", "993"))
    candidates: list[CandidateLink] = []

    with imaplib.IMAP4_SSL(imap_host, port, ssl_context=context) as imap:
        imap.login(imap_user, imap_password)
        imap.select(mailbox, readonly=True)
        status, data = imap.search(None, "SINCE", since)
        if status != "OK":
            return []
        message_nums = data[0].split()
        max_messages = int(os.environ.get("NTC_NOIP_IMAP_MAX_MESSAGES", "120"))
        for num in message_nums[-max_messages:]:
            status, fetched = imap.fetch(num, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            msg = email.message_from_bytes(raw)
            subject = decode_header_value(msg.get("Subject"))
            sender = decode_header_value(msg.get("From"))
            message_id = msg.get("Message-ID") or f"imap:{num.decode()}"
            received_at = decode_header_value(msg.get("Date"))
            haystack = f"{subject}\n{sender}\n{message_text_parts(msg)}"
            if "no-ip" not in haystack.lower() and "noip" not in haystack.lower():
                continue
            for url in extract_urls_from_text(haystack, host):
                candidates.append(
                    CandidateLink(
                        url=url,
                        message_id=message_id,
                        subject=subject,
                        sender=sender,
                        received_at=received_at,
                    )
                )
    return candidates


def resolve_host(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None, family=socket.AF_INET)})
    except socket.gaierror:
        return []


def public_ip() -> str | None:
    endpoint = os.environ.get("NTC_NOIP_PUBLIC_IP_ENDPOINT", "https://api.ipify.org")
    try:
        with urllib.request.urlopen(endpoint, timeout=8) as response:
            return response.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def classify_response(body: str, final_url: str, http_status: int) -> tuple[str, str]:
    lowered = body.lower()
    final_lowered = final_url.lower()
    if any(token in lowered for token in ("captcha", "recaptcha", "hcaptcha")):
        return "manual_required", "No-IP presented a CAPTCHA-style challenge."
    if any(token in lowered for token in ("two-factor", "2fa", "multi-factor", "mfa")):
        return "manual_required", "No-IP requested multi-factor verification."
    if any(token in lowered for token in ("log in", "login", "sign in", "password")):
        if "confirmed" not in lowered and "success" not in lowered:
            return "manual_required", "No-IP requested login before confirmation."
    success_tokens = (
        "has been confirmed",
        "hostname confirmed",
        "hostnames confirmed",
        "successfully confirmed",
        "your hostname is now active",
        "already been confirmed",
    )
    if any(token in lowered for token in success_tokens):
        return "confirmed", "No-IP response looked like a successful confirmation."
    if "confirm" in final_lowered and http_status in {200, 204, 302}:
        return "unknown", "No-IP confirmation page loaded, but success text was not recognized."
    return "unknown", "No-IP response did not match a known confirmation or challenge."


def attempt_url(url: str) -> AttemptResult:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(256_000).decode("utf-8", errors="replace")
            final_url = response.geturl()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(256_000).decode("utf-8", errors="replace")
        final_url = exc.geturl()
        status = exc.code
    except Exception as exc:
        return AttemptResult(url=url, status="failed", reason=str(exc))

    result_status, reason = classify_response(body, final_url, status)
    return AttemptResult(
        url=url,
        status=result_status,
        reason=reason,
        http_status=status,
        final_url=final_url,
    )


def notify(report: str) -> None:
    command = os.environ.get("NTC_NOIP_ALERT_CMD", "").strip()
    if not command:
        return
    subprocess.run(
        shlex.split(command),
        input=report,
        text=True,
        check=False,
        timeout=30,
    )


def build_report(payload: dict) -> str:
    lines = [
        "# NTC No-IP Renewal Check",
        "",
        f"- Checked: `{payload['checked_at']}`",
        f"- Hostname: `{payload['hostname']}`",
        f"- Resolved IPs: `{', '.join(payload['resolved_ips']) or 'none'}`",
        f"- Runner public IP: `{payload['public_ip'] or 'unknown'}`",
        f"- Mode: `{payload['mode']}`",
        f"- Candidates found: `{len(payload['candidates'])}`",
        f"- Attempts: `{len(payload['attempts'])}`",
        "",
    ]
    if payload["attempts"]:
        lines.append("## Attempts")
        for attempt in payload["attempts"]:
            lines.extend(
                [
                    "",
                    f"- Status: `{attempt['status']}`",
                    f"  Reason: {attempt['reason']}",
                    f"  HTTP: `{attempt.get('http_status') or 'n/a'}`",
                    f"  Final URL: `{attempt.get('final_url') or 'n/a'}`",
                ]
            )
    elif payload["candidates"]:
        lines.extend(
            [
                "## Candidate Links",
                "",
                "Auto-confirm is disabled, so the helper did not open the links.",
            ]
        )
    else:
        lines.extend(
            [
                "## Result",
                "",
                "No current No-IP confirmation email/link was found.",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_check(source_url: str | None = None) -> int:
    host = hostname()
    directory = state_dir()
    state_path = directory / "state.json"
    state = load_state(state_path)
    auto_confirm = env_bool("NTC_NOIP_AUTO_CONFIRM", False)

    candidates: list[CandidateLink] = []
    if source_url:
        candidates.append(
            CandidateLink(
                url=source_url,
                message_id="manual-url",
                subject="manual-url",
                sender="manual",
                received_at=now_utc(),
            )
        )
    else:
        candidates.extend(imap_candidates(host))

    attempts: list[AttemptResult] = []
    processed_urls = state.setdefault("processed_urls", {})
    processed_messages = state.setdefault("processed_messages", {})

    for candidate in candidates:
        if processed_urls.get(candidate.url) and not source_url:
            continue
        if not auto_confirm and not source_url:
            continue
        attempt = attempt_url(candidate.url)
        attempts.append(attempt)
        state.setdefault("attempts", []).append({**asdict(attempt), "attempted_at": now_utc()})
        if attempt.status in {"confirmed", "manual_required", "unknown"}:
            processed_urls[candidate.url] = {"status": attempt.status, "at": now_utc()}
            processed_messages[candidate.message_id] = {"status": attempt.status, "at": now_utc()}

    payload = {
        "checked_at": now_utc(),
        "hostname": host,
        "resolved_ips": resolve_host(host),
        "public_ip": public_ip(),
        "mode": "auto-confirm" if auto_confirm or source_url else "detect-only",
        "candidates": [asdict(candidate) for candidate in candidates],
        "attempts": [asdict(attempt) for attempt in attempts],
    }
    report = build_report(payload)
    write_report(directory, report, payload)
    save_state(state_path, state)

    needs_attention = any(attempt.status != "confirmed" for attempt in attempts)
    if needs_attention or (candidates and not auto_confirm and not source_url):
        notify(report)
    print(report)
    if any(attempt.status in {"failed", "manual_required"} for attempt in attempts):
        return 2
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Check and optionally follow No-IP hostname confirmation links.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              noip_confirm_helper.py check
              NTC_NOIP_AUTO_CONFIRM=1 noip_confirm_helper.py check
              noip_confirm_helper.py confirm-url 'https://www.noip.com/...'
            """
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="scan configured email and optionally confirm")
    confirm = sub.add_parser("confirm-url", help="attempt one explicit confirmation URL")
    confirm.add_argument("url")
    args = parser.parse_args(argv)

    if args.command == "check":
        return run_check()
    if args.command == "confirm-url":
        return run_check(args.url)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
