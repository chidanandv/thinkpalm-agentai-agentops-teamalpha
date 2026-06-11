"""Simple signed-cookie session auth for the operations dashboard."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

COOKIE_NAME = "fleet_session"
DEFAULT_TTL_HOURS = 24


def create_session_token(username: str, secret: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> str:
    payload = {"user": username, "exp": int(time.time()) + ttl_hours * 3600}
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
    return f"{sig}.{data.decode()}"


def verify_session_token(token: str | None, secret: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    sig, _, raw = token.partition(".")
    try:
        data = raw.encode()
        expected = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(raw)
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except (json.JSONDecodeError, UnicodeError):
        return None


def get_user_from_cookie(cookies: dict[str, str], secret: str) -> str | None:
    session = verify_session_token(cookies.get(COOKIE_NAME), secret)
    return session.get("user") if session else None
