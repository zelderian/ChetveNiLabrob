"""Login sessions stored in Redis (Lab 2).

Lab 1 kept sessions in a process-local dict, so a token issued by one
instance was unknown to the others and was lost on restart. Now any
instance can resolve any token.

Key:   session:<sha256(token)>  ->  member_id      (TTL = session lifetime)
Only a hash of the token is stored, so a Redis dump does not leak tokens.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.redis_client import redis_client


def _key(token: str) -> str:
    return "session:" + hashlib.sha256(token.encode()).hexdigest()


def create_session(member_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    redis_client.set(_key(token), member_id, ex=settings.session_ttl_seconds)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
    return token, expires_at


def resolve_session(token: str) -> int | None:
    value = redis_client.get(_key(token))
    return int(value) if value is not None else None


def revoke_session(token: str) -> None:
    redis_client.delete(_key(token))
