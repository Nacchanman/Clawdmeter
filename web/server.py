#!/usr/bin/env python3
"""Local browser dashboard for Clawdmeter.

Run on the same machine where Claude Code is logged in, then open the
served URL from Safari on an iPhone on the same Wi-Fi network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-3-5-haiku-latest"


def load_access_token() -> str:
    env_token = os.environ.get("CLAUDE_ACCESS_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if env_token:
        return env_token.strip()

    if not CREDENTIALS_PATH.exists():
        raise RuntimeError(f"Credentials file not found: {CREDENTIALS_PATH}")

    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    token = find_token(data)
    if not token:
        raise RuntimeError("Could not find an access token in ~/.claude/.credentials.json")
    return token


def find_token(value: Any) -> str | None:
    """Find a plausible OAuth access token in Claude Code credentials JSON."""
    if isinstance(value, dict):
        preferred_keys = [
            "accessToken",
            "access_token",
            "claudeAiOauth/accessToken",
            "oauthAccessToken",
            "token",
        ]
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
    elif isinstance(value, str):
        if looks_like_token(value):
            return value
    return None


def looks_like_token(value: str) -> bool:
    if len(value) < 30:
        return False
    lowered = value.lower()
    if "token" in lowered and len(value) < 80:
        return False
    return bool(re.search(r"[A-Za-z0-9_-]{30,}", value))


def fetch_usage() -> dict[str, Any]:
    token = load_access_token()
    headers = {
        "authorization": f"Bearer {token}",
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
        "status": "allowed",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def header_value(response: requests.Response, name: str) -> str | None:
    for key, value in response.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def header_number(response: requests.Response, name: str, default: int) -> int:
    value = header_value(response, name)
    if value is None:
        return default
    try:
        return round(float(value))
    except ValueError:
        return default


def header_minutes(response: requests.Response, name: str) -> int | None:
    value = header_value(response, name)
    if not value:
        return None

    stripped = value.strip()
    try:
        numeric = float(stripped)
        # Existing daemon payloads use minutes. Some API headers may use seconds.
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
    server_version = "ClawdmeterWeb/0.1"

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
        self.send_error(404)

    def send_usage(self) -> None:
        try:
            payload = fetch_usage()
            status = 200
        except Exception as exc:
            payload = {
                "ok": False,
                "error": str(exc),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
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
    parser = argparse.ArgumentParser(description="Run the Clawdmeter browser dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Use 0.0.0.0 for iPhone access on LAN.")
    parser.add_argument("--port", default=8787, type=int, help="Port to bind.")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Clawdmeter Web is running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
