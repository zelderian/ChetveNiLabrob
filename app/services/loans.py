"""Loan business logic: borrowing and returning books.

Lab 2 (stateless): no in-process locks. Concurrency control lives in the
shared database, so it holds no matter how many instances are running:

* borrow: SELECT ... FOR UPDATE on the member row (serialises the per-member
  loan-limit check) and on the book row (serialises available_copies).
  Lock order is always member -> book to avoid deadlocks.
* return: SELECT ... FOR UPDATE on the loan row, then the book row.
* idempotency: an optional client-supplied Idempotency-Key is stored in the
  SAME transaction as the loan (unique per member). A retry - e.g. after the
  instance that handled the first attempt crashed - returns the already
  created loan instead of borrowing twice.
"""
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.errors import Conflict, Forbidden, NotFound
from app.models import Book, Loan, Member
from app.schemas import LoanOut
from app.services import reports


def _now() -> datetime:
    return datetime.now(timezone.utc)


def to_out(loan: Loan) -> LoanOut:
    return LoanOut(
        id=loan.id,
        member_id=loan.member_id,
        book_id=loan.book_id,
        book_title=loan.book.title,
        borrowed_at=loan.borrowed_at,
        due_at=loan.due_at,
        returned_at=loan.returned_at,
        fine_amount=loan.fine_amount,
        is_overdue=loan.returned_at is None and loan.due_at < _now(),
    )


def borrow_book(
    db: Session, member_id: int, book_id: int, days: int, idempotency_key: str | None = None
) -> tuple[Loan, bool]:
    """Returns (loan, replayed). replayed=True if the key was already processed."""
    member = db.scalar(select(Member).where(Member.id == member_id).with_for_update())
    if member is None:
        raise NotFound(f"Member {member_id} not found")

    if idempotency_key:
        existing = db.scalar(
            select(Loan).where(Loan.member_id == member_id, Loan.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.book_id != book_id:
                raise Conflict("Idempotency-Key was already used for a different request")
            db.rollback()
            return existing, True

    book = db.scalar(select(Book).where(Book.id == book_id).with_for_update())
    if book is None:
        raise NotFound(f"Book {book_id} not found")
    if book.available_copies <= 0:
        raise Conflict("No available copies of this book")

    active = db.scalar(
        select(func.count(Loan.id)).where(Loan.member_id == member_id, Loan.returned_at.is_(None))
    )
    if active >= member.max_active_loans:
        raise Conflict(f"Active loans limit reached ({member.max_active_loans})")

    duplicate = db.scalar(
        select(Loan.id).where(
            Loan.member_id == member_id, Loan.book_id == book_id, Loan.returned_at.is_(None)
        )
    )
    if duplicate:
        raise Conflict("Member already has an active loan of this book")

    now = _now()
    loan = Loan(
        member_id=member_id,
        book_id=book_id,
        borrowed_at=now,
        due_at=now + timedelta(days=days),
        idempotency_key=idempotency_key,
    )
    book.available_copies -= 1
    db.add(loan)
    db.commit()
    db.refresh(loan)
    reports.invalidate()
    return loan, False


def return_book(db: Session, member_id: int, loan_id: int) -> Loan:
    loan = db.scalar(select(Loan).where(Loan.id == loan_id).with_for_update())
    if loan is None:
        raise NotFound(f"Loan {loan_id} not found")
    if loan.member_id != member_id:
        raise Forbidden("This loan belongs to another member")
    if loan.returned_at is not None:
        raise Conflict("Loan is already returned")

    now = _now()
    overdue_days = max(0, math.ceil((now - loan.due_at).total_seconds() / 86400))
    loan.returned_at = now
    loan.fine_amount = settings.fine_per_day * overdue_days

    book = db.scalar(select(Book).where(Book.id == loan.book_id).with_for_update())
    book.available_copies += 1
    db.commit()
    db.refresh(loan)
    reports.invalidate()
    return loan


def list_member_loans(db: Session, member_id: int, active_only: bool) -> list[Loan]:
    stmt = (
        select(Loan)
        .options(joinedload(Loan.book))  # avoid N+1 when rendering book titles
        .where(Loan.member_id == member_id)
        .order_by(Loan.borrowed_at.desc())
    )
    if active_only:
        stmt = stmt.where(Loan.returned_at.is_(None))
    return list(db.scalars(stmt).all())
