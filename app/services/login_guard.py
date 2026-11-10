"""Brute-force protection with a shared counter in Redis.

A process-local counter would let an attacker get N x limit attempts by
spreading requests across N instances; a Redis counter is global.
"""
from app.config import settings
from app.errors import DomainError
from app.redis_client import redis_client


class TooManyAttempts(DomainError):
    status_code = 429
    code = "too_many_attempts"


def _key(email: str) -> str:
    return f"login_fail:{email.lower()}"


def ensure_not_locked(email: str) -> None:
    failures = redis_client.get(_key(email))
    if failures is not None and int(failures) >= settings.login_max_failures:
        ttl = redis_client.ttl(_key(email))
        raise TooManyAttempts(f"Too many failed logins, retry in {max(ttl, 1)} s")


def register_failure(email: str) -> None:
    pipe = redis_client.pipeline()
    pipe.incr(_key(email))
    pipe.expire(_key(email), settings.login_lockout_seconds, nx=True)
    pipe.execute()


def reset(email: str) -> None:
    redis_client.delete(_key(email))
