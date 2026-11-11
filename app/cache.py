import hashlib
import json
import logging
import random
import threading
import time
from collections import Counter
from collections.abc import Callable
from typing import TypeVar

import redis

from app.config import settings

T = TypeVar("T")
log = logging.getLogger("libra.cache")

PREFIX = "libra"

cache_client: redis.Redis = redis.Redis.from_url(
    settings.cache_url,
    decode_responses=True,
    socket_timeout=0.3,
    socket_connect_timeout=0.3,
    retry_on_timeout=False,
)

_stats: Counter = Counter()
_stats_lock = threading.Lock()
_breaker_open_until = 0.0


def _count(event: str) -> None:
    with _stats_lock:
        _stats[event] += 1


def _available() -> bool:
    return time.monotonic() >= _breaker_open_until


def _trip(exc: Exception) -> None:
    global _breaker_open_until
    _breaker_open_until = time.monotonic() + settings.cache_breaker_seconds
    _count("errors")
    log.warning("cache unavailable (%s) - bypassing for %ss", exc, settings.cache_breaker_seconds)


def params_hash(**params) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def version_key(name: str) -> str:
    return f"{PREFIX}:ver:{name}"


def _ttl(seconds: int) -> int:
    return max(1, int(seconds * random.uniform(0.9, 1.1)))


def cache_aside(
    key: str,
    ttl: int,
    loader: Callable[[], T],
    dump: Callable[[T], str],
    load: Callable[[str], T],
    versions: tuple[str, ...] = (),
) -> tuple[T, str]:
    if not settings.cache_enabled:
        return loader(), "DISABLED"
    if not _available():
        _count("bypass")
        return loader(), "BYPASS"

    lock_key, have_lock = None, False
    try:
        if versions:
            vals = cache_client.mget([version_key(v) for v in versions])
            key = f"{key}:v{'.'.join(v or '0' for v in vals)}"
        cached = cache_client.get(key)
        if cached is not None:
            _count("hit")
            log.debug("cache HIT %s", key)
            return load(cached), "HIT"

        lock_key = f"{key}:lock"
        have_lock = bool(cache_client.set(lock_key, settings.instance_id, nx=True,
                                          px=settings.cache_lock_ms))
        if not have_lock:
            for _ in range(10):
                time.sleep(0.02)
                cached = cache_client.get(key)
                if cached is not None:
                    _count("hit_after_wait")
                    return load(cached), "HIT"
    except redis.RedisError as exc:
        _trip(exc)
        _count("bypass")
        return loader(), "BYPASS"

    value = loader()
    try:
        cache_client.set(key, dump(value), ex=_ttl(ttl))
        if have_lock:
            cache_client.delete(lock_key)
    except redis.RedisError as exc:
        _trip(exc)
    _count("miss")
    log.debug("cache MISS %s", key)
    return value, "MISS"


def invalidate(*versions: str) -> None:
    if not settings.cache_enabled:
        return
    try:
        pipe = cache_client.pipeline(transaction=False)
        for v in versions:
            pipe.incr(version_key(v))
        pipe.execute()
        _count("invalidations")
        log.debug("cache INVALIDATE %s", versions)
    except redis.RedisError as exc:
        _trip(exc)


def stats() -> dict:
    with _stats_lock:
        local = dict(_stats)
    info: dict = {"enabled": settings.cache_enabled, "breaker_open": not _available()}
    try:
        s = cache_client.info("stats")
        m = cache_client.info("memory")
        info.update({
            "status": "ok",
            "server_keyspace_hits": s.get("keyspace_hits"),
            "server_keyspace_misses": s.get("keyspace_misses"),
            "server_evicted_keys": s.get("evicted_keys"),
            "used_memory": m.get("used_memory_human"),
            "maxmemory_policy": m.get("maxmemory_policy"),
            "keys": cache_client.dbsize(),
        })
    except redis.RedisError as exc:
        info["status"] = f"unavailable: {exc}"
    return {"instance": settings.instance_id, "instance_counters": local, "server": info}


def ping() -> str:
    if not settings.cache_enabled:
        return "disabled"
    try:
        cache_client.ping()
        return "ok"
    except redis.RedisError:
        return "unavailable (degraded mode: reads go to the DB)"
