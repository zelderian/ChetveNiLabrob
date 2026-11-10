"""Application settings, read once from environment variables.

Configuration is immutable and identical for every instance, so it is not
"state" in the stateless-architecture sense.
"""
import os
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
    session_ttl_seconds: int = _int("SESSION_TTL_SECONDS", 3600)
    report_cache_ttl_seconds: int = _int("REPORT_CACHE_TTL_SECONDS", 60)
    fine_per_day: Decimal = Decimal(os.getenv("FINE_PER_DAY", "5.00"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
