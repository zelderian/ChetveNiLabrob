import os
import socket
from dataclasses import dataclass
from decimal import Decimal


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://libra:libra@localhost:5432/libra"
    )
    db_pool_size: int = _int("DB_POOL_SIZE", 10)
    db_max_overflow: int = _int("DB_MAX_OVERFLOW", 5)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    session_ttl_seconds: int = _int("SESSION_TTL_SECONDS", 3600)
    cache_url: str = os.getenv("CACHE_URL", "redis://localhost:6379/1")
    cache_enabled: bool = os.getenv("CACHE_ENABLED", "true").lower() in ("1", "true", "yes")
    cache_ttl_book: int = _int("CACHE_TTL_BOOK", 300)
    cache_ttl_list: int = _int("CACHE_TTL_LIST", 60)
    cache_ttl_report: int = _int("CACHE_TTL_REPORT", 120)
    cache_breaker_seconds: int = _int("CACHE_BREAKER_SECONDS", 5)
    cache_lock_ms: int = _int("CACHE_LOCK_MS", 2000)
    login_max_failures: int = _int("LOGIN_MAX_FAILURES", 5)
    login_lockout_seconds: int = _int("LOGIN_LOCKOUT_SECONDS", 300)
    fine_per_day: Decimal = Decimal(os.getenv("FINE_PER_DAY", "5.00"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    instance_id: str = os.getenv("INSTANCE_ID") or socket.gethostname()
    chaos_delay_ms: int = _int("CHAOS_DELAY_MS", 0)


settings = Settings()
