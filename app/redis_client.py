"""Shared Redis connection (centralised store for sessions, cache, counters).

The client object only holds a connection pool - a per-process *resource*,
not application state: every instance talks to the same Redis server.
"""
import redis

from app.config import settings

redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=2,
    socket_connect_timeout=2,
    health_check_interval=30,
)
