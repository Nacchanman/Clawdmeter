#!/usr/bin/env python3
"""Local browser dashboard for Clawdmeter.

Default mode is free and local-only: it reads Claude Code session JSON files under
~/.claude/sessions and estimates recent usage without calling Anthropic's API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
CREDENTIALS_PATH = CLAUDE_DIR / ".credentials.json"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-3-5-haiku-latest"

# These are only used for the free local estimate. They are not official limits.
DEFAULT_FIVE_HOUR_TOKEN_BUDGET = int(os.environ.get("CLAWDMETER_5H_TOKEN_BUDGET", "200000"))
DEFAULT_WEEKLY_TOKEN_BUDGET = int(os.environ.get("CLAWDMETER_WEEKLY_TOKEN_BUDGET", "1400000"))

SERVER_MODE = "local"


def fetch_usage() -> dict[str, Any]:
    if SERVER_MODE == "api":
        return fetch_usage_from_api()
    return fetch_usage_from_local_sessions()


def fetch_usage_from_local_sessions() -> dict[str, Any]:
    if not SESSIONS_DIR.exists():
        raise RuntimeError(f"Claude Code sessions directory not found: {SESSIONS_DIR}")

    now = datetime.now(timezone.utc)
    five_hours_ago = now - timedelta(hours=5)
    seven_days_ago = now - timedelta(days=7)

    five_hour_tokens = 0
    weekly_tokens = 0
    scanned_files = 0
    matched_usage_objects = 0

    for path in SESSIONS_DIR.rglob("*.json"):
        scanned_files += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for usage, timestamp in iter_usage_objects(data):
            matched_usage_objects += 1
            tokens = usage_token_total(usage)
            if tokens <= 0:
                continue
            when = timestamp or file_mtime(path)
            if when >= seven_days_ago:
                weekly_tokens += tokens
            if when >= five_hours_ago:
                five_hour_tokens += tokens

    session_percent = percent(five_hour_tokens, DEFAULT_FIVE_HOUR_TOKEN_BUDGET)
    weekly_percent = percent(weekly_tokens, DEFAULT_WEEKLY_TOKEN_BUDGET)

    return {
        "ok": True,
        "sessionPercent": session_percent,
        "sessionResetMinutes": minutes_until_next_five_hour_window(now),
        "weeklyPercent": weekly_percent,
        "weeklyResetMinutes": None,
        "status": f"local estimate · {matched_usage_objects} usage records",
        "updatedAt": now.isoformat(),
        "source": "local_sessions",
        "debug": {
            "scannedFiles": scanned_files,
            "matchedUsageObjects": matched_usage_objects,
            "fiveHourTokens": five_hour_tokens,
            "weeklyTokens": weekly_tokens,
            "fiveHourTokenBudget": DEFAULT_FIVE_HOUR_TOKEN_BUDGET,
            "weeklyTokenBudget": DEFAULT_WEEKLY_TOKEN_BUDGET,
        },
    }


def iter_usage_objects(value: Any, inherited_timestamp: datetime | None = None):
    if isinstance(value, dict):
        timestamp = parse_timestamp(value) or inherited_timestamp
        usage = value.get("usage")
        if isinstance(usage, dict):
            yield usage, timestamp

        # Some Claude Code builds may store usage fields directly on a message object.
        if any(key in value for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")):
            yield value, timestamp

        for child in value.values():
            yield from iter_usage_objects(child, timestamp)
    elif isinstance(value, list):
        for child in value:
            yield from iter_usage_objects(child, inherited_timestamp)


def parse_timestamp(value: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "created_at", "createdAt", "time", "datetime", "date"):
        raw = value.get(key)
        if isinstance(raw, str):
            parsed = parse_datetime(raw)
            if parsed:
                return parsed
    return None


def parse_datetime(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def file_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def usage_token_total(usage: dict[str, Any]) -> int:
    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "inputTokens",
        "outputTokens",
        "cacheCreationInputTokens",
        "cacheReadInputTokens",
    ):
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            total += int(value)
    return total


def percent(used: int, budget: int) -> int:
    if budget <= 0:
        return 0
    return max(0, min(100, round((used / budget) * 100)))


def minutes_until_next_five_hour_window(now: datetime) -> int:
    # A rough countdown for the rolling 5-hour local estimate.
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(1, round((next_hour - now).total_seconds() / 60))


def fetch_usage_from_api() -> dict[str, Any]:
    import requests

    headers = {
        **auth_headers(),
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": os.environ.get("CLAWDMETER_MODEL", DEFAULT_MODEL),
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }

    response = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=20)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Anthropic API returned HTTP {response.status_code}: {response.text[:300]}")

    return {
        "ok": True,
        "sessionPercent": header_number(response, "anthropic-ratelimit-unified-5h-utilization", 0),
        "sessionResetMinutes": header_minutes(response, "anthropic-ratelimit-unified-5h-reset"),
        "weeklyPercent": header_number(response, "anthropic-ratelimit-unified-7d-utilization", 0),
        "weeklyResetMinutes": header_minutes(response, "anthropic-ratelimit-unified-7d-reset"),
        "status": "api",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "anthropic_api",
    }


def auth_headers() -> dict[str, str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return {"x-api-key": api_key.strip()}

    token = load_access_token()
    return {"authorization": f"Bearer {token}"}


def load_access_token() -> str:
    env_token = os.environ.get("CLAUDE_ACCESS_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if env_token:
        return env_token.strip()

    if not CREDENTIALS_PATH.exists():
        raise RuntimeError(
            "Claude Code credentials file was not found. On macOS, Claude Code often stores credentials "
            "in the macOS Keychain, not in ~/.claude/.credentials.json. Use default --mode local for free "
            "local estimates, or set ANTHROPIC_API_KEY and run --mode api."
        )

    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    token = find_token(data)
    if not token:
        raise RuntimeError("Could not find an access token in ~/.claude/.credentials.json")
    return token


def find_token(value: Any) -> str | None:
    if isinstance(value, dict):
        preferred_keys = ["accessToken", "access_token", "claudeAiOauth/accessToken", "oauthAccessToken", "token"]
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and len(candidate) > 20:
                return candidate
        for child in value.values():
            found = find_token(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_token(child)
            if found:
                return found
    elif isinstance(value, str) and looks_like_token(value):
        return value
    return None


def looks_like_token(value: str) -> bool:
    if len(value) < 30:
        return False
    lowered = value.lower()
    if "token" in lowered and len(value) < 80:
        return False
    return bool(re.search(r"[A-Za-z0-9_-]{30,}", value))


def header_value(response: Any, name: str) -> str | None:
    for key, value in response.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def header_number(response: Any, name: str, default: int) -> int:
    value = header_value(response, name)
    if value is None:
        return default
    try:
        return round(float(value))
    except ValueError:
        return default


def header_minutes(response: Any, name: str) -> int | None:
    value = header_value(response, name)
    if not value:
        return None

    stripped = value.strip()
    try:
        numeric = float(stripped)
        if numeric > 60 * 24 * 14:
            return round(numeric / 60)
        return round(numeric)
    except ValueError:
        pass

    try:
        reset_time = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        delta_seconds = (reset_time - datetime.now(timezone.utc)).total_seconds()
        return max(0, round(delta_seconds / 60))
    except ValueError:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "ClawdmeterWeb/0.3"

    def do_GET(self) -> None:
        if self.path == "/api/usage":
            self.send_usage()
            return
        if self.path in ("/", "/index.html"):
            self.send_static("index.html", "text/html; charset=utf-8")
            return
        if self.path == "/styles.css":
            self.send_static("styles.css", "text/css; charset=utf-8")
            return
        if self.path == "/app.js":
            self.send_static("app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/manifest.webmanifest":
            self.send_static("manifest.webmanifest", "application/manifest+json; charset=utf-8")
            return
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def send_usage(self) -> None:
        try:
            payload = fetch_usage()
            status = 200
        except Exception as exc:
            print(f"/api/usage failed: {exc}", file=sys.stderr)
            payload = {"ok": False, "error": str(exc), "updatedAt": datetime.now(timezone.utc).isoformat()}
            status = 500
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-cache")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


def main() -> None:
    global SERVER_MODE

    parser = argparse.ArgumentParser(description="Run the Clawdmeter browser dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Use 0.0.0.0 for iPhone access on LAN.")
    parser.add_argument("--port", default=8787, type=int, help="Port to bind.")
    parser.add_argument("--mode", choices=["local", "api"], default=os.environ.get("CLAWDMETER_MODE", "local"), help="local is free and reads Claude Code session files; api calls Anthropic API.")
    args = parser.parse_args()
    SERVER_MODE = args.mode

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Clawdmeter Web is running at http://{args.host}:{args.port}")
    print(f"Mode: {SERVER_MODE}")
    if SERVER_MODE == "local":
        print("Using free local estimate from ~/.claude/sessions. No Anthropic API call will be made.")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
