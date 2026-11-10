"""Reports - the High-Load scenario of the system.

"Top-N popular books over the last D days" aggregates the `loans` table
joined with `books` (GROUP BY + ORDER BY count) - the most expensive read.

Lab 2: the result is cached in Redis, shared by all instances.
Cache keys embed a version number; every borrow/return INCRements the
version, so all instances stop using stale entries at the same moment
(old versions simply expire by TTL). If Redis is down the report is
computed directly from the DB (graceful degradation).
"""
import logging
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Book, Loan
from app.redis_client import redis_client
from app.schemas import PopularBook, PopularBooksReport

log = logging.getLogger("libra.reports")

VERSION_KEY = "report:popular:version"


def invalidate() -> None:
    try:
        redis_client.incr(VERSION_KEY)
    except redis.RedisError:
        log.warning("cannot invalidate report cache, entries will expire by TTL")


def _query(db: Session, days: int, limit: int) -> PopularBooksReport:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    loans_count = func.count(Loan.id).label("loans_count")
    rows = db.execute(
        select(Book.id, Book.title, Book.author, loans_count)
        .join(Loan, Loan.book_id == Book.id)
        .where(Loan.borrowed_at >= since)
        .group_by(Book.id)
        .order_by(desc(loans_count), Book.id)
        .limit(limit)
    ).all()
    return PopularBooksReport(
        period_days=days,
        generated_at=datetime.now(timezone.utc),
        items=[
            PopularBook(book_id=r.id, title=r.title, author=r.author, loans_count=r.loans_count)
            for r in rows
        ],
    )


def popular_books(db: Session, days: int, limit: int) -> tuple[PopularBooksReport, str]:
    """Returns (report, cache_status) where cache_status is HIT / MISS / BYPASS."""
    try:
        version = redis_client.get(VERSION_KEY) or "0"
        key = f"report:popular:v{version}:{days}:{limit}"
        cached = redis_client.get(key)
        if cached is not None:
            return PopularBooksReport.model_validate_json(cached), "HIT"
    except redis.RedisError:
        log.warning("redis unavailable, report computed without cache")
        return _query(db, days, limit), "BYPASS"

    report = _query(db, days, limit)
    try:
        redis_client.set(key, report.model_dump_json(), ex=settings.report_cache_ttl_seconds)
    except redis.RedisError:
        pass
    return report, "MISS"
