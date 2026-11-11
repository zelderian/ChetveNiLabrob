"""Distributed cache layer (Lab 4) - Cache-Aside (lazy loading) over Redis.

Read path (cache_aside):
    1. key lookup in Redis                    -> HIT: return without touching the DB
    2. MISS: load from PostgreSQL, SET key with TTL (+-10 % jitter), return
    Redis unavailable -> BYPASS: read straight from the DB (graceful degradation)
    CACHE_ENABLED=false -> DISABLED (used for Lab 5 comparisons)

Key design:  libra:<entity>:<id | params_hash>:v<version>
    * params_hash = sha256 of the canonical (sorted, normalised) query params,
      so equal requests map to one key and different ones never collide;
    * version = value of a version counter libra:ver:<name>. Writers INCR the
      counter after COMMIT; all old keys become unreachable at once on every
      instance and simply expire by TTL. This also closes the classic race
      "reader loads old row -> writer commits+deletes -> reader SETs stale
      value": the stale value lands under the OLD version key nobody reads.

Stampede (thundering herd) protection: on a miss only the request that wins
SET NX on <key>:lock queries the DB; concurrent ones wait up to ~200 ms for
the value to appear, then fall back to the DB themselves.

Avalanche protection: TTL jitter, so keys created together don't expire together.

Circuit breaker: after a Redis error the cache is skipped for
CACHE_BREAKER_SECONDS, so a dead cache costs one timeout, not one per request.
The breaker and hit/miss counters are process-local *ephemeral* data
(category "Local Safe" from Lab 2): losing them changes nothing functionally.
"""
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
    socket_timeout=0.3,          # a cache must be fast or be skipped
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
    """Returns (value, status); status is HIT | MISS | BYPASS | DISABLED."""
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
        if not have_lock:  # another request is already loading this key
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

    value = loader()  # exceptions (e.g. NotFound) propagate; nothing is cached
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
    """Called AFTER a successful COMMIT of a write: bumps version counters."""
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
        # Cache unreachable: entries are unreachable too; anything left is
        # bounded by its TTL (documented trade-off).
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
