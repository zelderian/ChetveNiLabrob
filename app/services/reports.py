"""Reports - the High-Load scenario of the system.

"Top-N popular books over the last D days" aggregates the whole `loans`
table joined with `books` (GROUP BY + ORDER BY count). It is the most
expensive read in the API.

Lab 1 baseline: the result is cached in a process-local dict.
NOTE: local cache - every instance has its own copy, copies diverge and are
not invalidated by writes on other instances. Removed in Lab 2.
"""
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Book, Loan
from app.schemas import PopularBook, PopularBooksReport

_cache: dict[tuple[int, int], tuple[float, PopularBooksReport]] = {}


def popular_books(db: Session, days: int, limit: int) -> tuple[PopularBooksReport, bool]:
    key = (days, limit)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1], True

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
    report = PopularBooksReport(
        period_days=days,
        generated_at=datetime.now(timezone.utc),
        items=[
            PopularBook(book_id=r.id, title=r.title, author=r.author, loans_count=r.loans_count)
            for r in rows
        ],
    )
    _cache[key] = (time.time() + settings.report_cache_ttl_seconds, report)
    return report, False
