"""Login sessions.

Lab 1 baseline: sessions live in a dict inside the process.
NOTE: this is local state - a token issued by one instance is unknown to
another one, and all sessions are lost on restart. Removed in Lab 2.
"""
import secrets
import threading
import time
from datetime import datetime, timezone

from app.config import settings

_sessions: dict[str, tuple[int, float]] = {}  # token -> (member_id, expires_ts)
_lock = threading.Lock()


def create_session(member_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = time.time() + settings.session_ttl_seconds
    with _lock:
        _sessions[token] = (member_id, expires)
    return token, datetime.fromtimestamp(expires, tz=timezone.utc)


def resolve_session(token: str) -> int | None:
    with _lock:
        entry = _sessions.get(token)
        if entry is None:
            return None
        member_id, expires = entry
        if expires < time.time():
            del _sessions[token]
            return None
        return member_id


def revoke_session(token: str) -> None:
    with _lock:
        _sessions.pop(token, None)
