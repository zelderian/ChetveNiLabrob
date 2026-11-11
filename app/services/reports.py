"""Reports - the High-Load scenario of the system.

"Top-N popular books over the last D days" aggregates the `loans` table
joined with `books` (GROUP BY + ORDER BY count) - the most expensive read.

Lab 4: Cache-Aside through app.cache, shared by all instances.
  key  libra:report:popular:<params_hash>:v<report_ver>   TTL 120 s (+-10 %)
  every borrow / return / book edit bumps report_ver after COMMIT.
If the cache is down the report is computed from the DB (X-Cache: BYPASS).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app import cache
from app.config import settings
from app.models import Book, Loan
from app.schemas import PopularBook, PopularBooksReport

REPORT_VERSION = "report:popular"


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
    """Returns (report, cache_status) where cache_status is HIT / MISS / BYPASS / DISABLED."""
    return cache.cache_aside(
        key=f"{cache.PREFIX}:report:popular:{cache.params_hash(days=days, limit=limit)}",
        versions=(REPORT_VERSION,),
        ttl=settings.cache_ttl_report,
        loader=lambda: _query(db, days, limit),
        dump=lambda r: r.model_dump_json(),
        load=PopularBooksReport.model_validate_json,
    )
