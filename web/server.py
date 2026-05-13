#!/usr/bin/env python3
"""Local browser dashboard for Clawdmeter.

The default `official` mode preserves the original Clawdmeter idea: it asks
Anthropic for Claude Code account rate-limit headers using Claude Code's own
OAuth credential, then shows those official utilization percentages in the
browser. The old local transcript estimate remains available as `--mode local`,
but it is intentionally opt-in because it cannot match Claude's real limits.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
CREDENTIALS_PATH = CLAUDE_DIR / ".credentials.json"

ANTHROPIC_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com") + "/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = os.environ.get("CLAWDMETER_MODEL", "claude-sonnet-4-6")
FALLBACK_MODELS = [
    DEFAULT_MODEL,
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
]

# Only used by --mode local. These are not official Claude limits.
DEFAULT_FIVE_HOUR_TOKEN_BUDGET = int(os.environ.get("CLAWDMETER_5H_TOKEN_BUDGET", "200000"))
DEFAULT_WEEKLY_TOKEN_BUDGET = int(os.environ.get("CLAWDMETER_WEEKLY_TOKEN_BUDGET", "1400000"))

SERVER_MODE = "official"


def fetch_usage() -> dict[str, Any]:
    if SERVER_MODE == "official":
        return fetch_usage_from_claude_code_oauth()
    if SERVER_MODE == "api":
        return fetch_usage_from_api_key()
    return fetch_usage_from_local_files()


def fetch_usage_from_claude_code_oauth() -> dict[str, Any]:
    token = load_claude_code_access_token()
    return fetch_usage_from_anthropic({"authorization": f"Bearer {token}"}, source="claude_code_oauth")


def fetch_usage_from_api_key() -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Use --mode official for Claude Code OAuth, or set ANTHROPIC_API_KEY for --mode api.")
    return fetch_usage_from_anthropic({"x-api-key": api_key.strip()}, source="anthropic_api_key")


def fetch_usage_from_anthropic(auth_header: dict[str, str], source: str) -> dict[str, Any]:
    import requests

    headers = {
        **auth_header,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    attempted_errors: list[str] = []
    response = None
    used_model = None
    for model in unique_models(FALLBACK_MODELS):
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        candidate = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=20)
        if 200 <= candidate.status_code < 300:
            response = candidate
            used_model = model
            break
        attempted_errors.append(f"{model}: HTTP {candidate.status_code}: {candidate.text[:180]}")
        # Only try fallback models for missing/unknown model errors. Auth and quota errors
        # should be surfaced immediately because fallback models will not fix them.
        if candidate.status_code != 404 or "model" not in candidate.text.lower():
            raise RuntimeError(f"Anthropic API returned HTTP {candidate.status_code}: {candidate.text[:300]}")

    if response is None:
        raise RuntimeError("Anthropic API model lookup failed. Tried: " + " | ".join(attempted_errors))

    session_percent = first_header_number(response, [
        "anthropic-ratelimit-unified-5h-utilization",
        "anthropic-ratelimit-5h-utilization",
        "anthropic-ratelimit-input-tokens-utilization",
    ], 0)
    weekly_percent = first_header_number(response, [
        "anthropic-ratelimit-unified-7d-utilization",
        "anthropic-ratelimit-7d-utilization",
    ], 0)

    return {
        "ok": True,
        "sessionPercent": session_percent,
        "sessionResetMinutes": first_header_minutes(response, [
            "anthropic-ratelimit-unified-5h-reset",
            "anthropic-ratelimit-5h-reset",
            "anthropic-ratelimit-input-tokens-reset",
        ]),
        "weeklyPercent": weekly_percent,
        "weeklyResetMinutes": first_header_minutes(response, [
            "anthropic-ratelimit-unified-7d-reset",
            "anthropic-ratelimit-7d-reset",
        ]),
        "status": "official rate limit",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "debug": {
            "mode": SERVER_MODE,
            "model": used_model,
            "headerNames": sorted(str(k) for k in response.headers.keys() if str(k).lower().startswith("anthropic-ratelimit")),
        },
    }


def unique_models(models: list[str]) -> list[str]:
    seen = set()
    result = []
    for model in models:
        if model and model not in seen:
            result.append(model)
            seen.add(model)
    return result


def load_claude_code_access_token() -> str:
    # Explicit env vars always win. Useful if the Keychain cannot be read from this terminal.
    for name in ("CLAUDE_ACCESS_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value.strip()

    # Linux / Windows Claude Code location, or custom CLAUDE_CONFIG_DIR.
    if CREDENTIALS_PATH.exists():
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        token = find_token(data)
        if token:
            return token

    # macOS Claude Code location. This may show a Keychain permission prompt.
    if platform.system() == "Darwin":
        token = load_token_from_macos_keychain()
        if token:
            return token

    raise RuntimeError(
        "Could not read Claude Code OAuth credentials. Run `claude` and /login first. "
        "On macOS, allow Keychain access if prompted. If Keychain access is blocked, run: "
        "security find-generic-password -s 'Claude Code-credentials' -w"
    )


def load_token_from_macos_keychain() -> str | None:
    # Known Claude Code service names. v2.x has used both names depending on version.
    service_names = [
        "Claude Code-credentials",
        "Claude Code",
        "claude-code-credentials",
        "claude-code",
    ]
    for service in service_names:
        secret = keychain_password(service)
        if not secret:
            continue
        token = parse_secret_for_token(secret)
        if token:
            return token
    return None


def keychain_password(service: str) -> str | None:
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def parse_secret_for_token(secret: str) -> str | None:
    if not secret:
        return None
    try:
        data = json.loads(secret)
        token = find_token(data)
        if token:
            return token
    except Exception:
        pass
    if looks_like_token(secret):
        return secret
    return None


def find_token(value: Any) -> str | None:
    if isinstance(value, dict):
        preferred_keys = [
            "accessToken",
            "access_token",
            "claudeAiOauth/accessToken",
            "oauthAccessToken",
            "token",
            "apiKey",
            "api_key",
        ]
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and looks_like_token(candidate):
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
    return len(value) >= 30 and bool(re.search(r"[A-Za-z0-9_\-.]{30,}", value))


def fetch_usage_from_local_files() -> dict[str, Any]:
    if not CLAUDE_DIR.exists():
        raise RuntimeError(f"Claude Code directory not found: {CLAUDE_DIR}")

    now = datetime.now(timezone.utc)
    five_hours_ago = now - timedelta(hours=5)
    seven_days_ago = now - timedelta(days=7)

    five_hour_tokens = 0
    weekly_tokens = 0
    scanned_files = 0
    parsed_records = 0
    matched_usage_objects = 0
    scanned_roots = [str(path) for path in local_roots()]

    for path in local_candidate_files():
        scanned_files += 1
        for record in read_json_records(path):
            parsed_records += 1
            for usage, timestamp in iter_usage_objects(record):
                matched_usage_objects += 1
                tokens = usage_token_total(usage)
                if tokens <= 0:
                    continue
                when = timestamp or file_mtime(path)
                if when >= seven_days_ago:
                    weekly_tokens += tokens
                if when >= five_hours_ago:
                    five_hour_tokens += tokens

    return {
        "ok": True,
        "sessionPercent": percent(five_hour_tokens, DEFAULT_FIVE_HOUR_TOKEN_BUDGET),
        "sessionResetMinutes": minutes_until_next_five_hour_window(now),
        "weeklyPercent": percent(weekly_tokens, DEFAULT_WEEKLY_TOKEN_BUDGET),
        "weeklyResetMinutes": None,
        "status": f"local estimate · {matched_usage_objects} usage records",
        "updatedAt": now.isoformat(),
        "source": "local_estimate",
        "debug": {
            "mode": SERVER_MODE,
            "scannedRoots": scanned_roots,
            "scannedFiles": scanned_files,
            "parsedRecords": parsed_records,
            "matchedUsageObjects": matched_usage_objects,
            "fiveHourTokens": five_hour_tokens,
            "weeklyTokens": weekly_tokens,
            "fiveHourTokenBudget": DEFAULT_FIVE_HOUR_TOKEN_BUDGET,
            "weeklyTokenBudget": DEFAULT_WEEKLY_TOKEN_BUDGET,
        },
    }


def local_roots() -> list[Path]:
    roots = []
    for path in (SESSIONS_DIR, PROJECTS_DIR):
        if path.exists():
            roots.append(path)
    return roots or [CLAUDE_DIR]


def local_candidate_files() -> list[Path]:
    candidates: list[Path] = []
    for root in local_roots():
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() in (".json", ".jsonl", ".log") or path.stat().st_size < 20_000_000:
                candidates.append(path)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def read_json_records(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    stripped = text.strip()
    if not stripped:
        return
    if stripped[0] in "[{":
        try:
            yield json.loads(stripped)
            return
        except Exception:
            pass
    for line in stripped.splitlines():
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def iter_usage_objects(value: Any, inherited_timestamp: datetime | None = None):
    if isinstance(value, dict):
        timestamp = parse_timestamp(value) or inherited_timestamp
        usage = value.get("usage")
        if isinstance(usage, dict):
            yield usage, timestamp
        message = value.get("message")
        if isinstance(message, dict):
            message_usage = message.get("usage")
            if isinstance(message_usage, dict):
                yield message_usage, timestamp
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
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
        "inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens",
    ):
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def percent(used: int, budget: int) -> int:
    if budget <= 0:
        return 0
    return max(0, min(100, round((used / budget) * 100)))


def minutes_until_next_five_hour_window(now: datetime) -> int:
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(1, round((next_hour - now).total_seconds() / 60))


def header_value(response: Any, name: str) -> str | None:
    for key, value in response.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def first_header_number(response: Any, names: list[str], default: int) -> int:
    for name in names:
        value = header_value(response, name)
        if value is None:
            continue
        try:
            return max(0, min(100, round(float(value))))
        except ValueError:
            continue
    return default


def first_header_minutes(response: Any, names: list[str]) -> int | None:
    for name in names:
        minutes = header_minutes(response, name)
        if minutes is not None:
            return minutes
    return None


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
    server_version = "ClawdmeterWeb/1.0"

    def do_GET(self) -> None:
        if self.path == "/api/usage":
            self.send_usage()
            return
        routes = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
        }
        if self.path in routes:
            filename, content_type = routes[self.path]
            self.send_static(filename, content_type)
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
            payload = {"ok": False, "error": str(exc), "updatedAt": datetime.now(timezone.utc).isoformat(), "source": SERVER_MODE}
            status = 500
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, filename: str, content_type: str) -> None:
        body = (STATIC_DIR / filename).read_bytes()
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
    parser.add_argument("--mode", choices=["official", "local", "api"], default=os.environ.get("CLAWDMETER_MODE", "official"), help="official uses Claude Code OAuth rate-limit headers; local is an estimate; api uses ANTHROPIC_API_KEY.")
    args = parser.parse_args()
    SERVER_MODE = args.mode

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Clawdmeter Web is running at http://{args.host}:{args.port}")
    print(f"Mode: {SERVER_MODE}")
    if SERVER_MODE == "official":
        print("Using Claude Code OAuth credentials and official Anthropic rate-limit headers.")
        print("On macOS, allow Keychain access if prompted.")
    elif SERVER_MODE == "local":
        print("Using local estimate from ~/.claude/projects and ~/.claude/sessions. This will not match Claude's official limits.")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
