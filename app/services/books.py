from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound
from app.models import Book, Loan
from app.schemas import BookCreate, BookUpdate


def get_book(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise NotFound(f"Book {book_id} not found")
    return book


def list_books(
    db: Session,
    q: str | None,
    author: str | None,
    available_only: bool,
    limit: int,
    offset: int,
) -> tuple[list[Book], int]:
    stmt = select(Book)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Book.title.ilike(like), Book.author.ilike(like)))
    if author:
        stmt = stmt.where(Book.author == author)
    if available_only:
        stmt = stmt.where(Book.available_copies > 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Book.id).limit(limit).offset(offset)).all()
    return list(items), total or 0


def create_book(db: Session, data: BookCreate) -> Book:
    if db.scalar(select(Book.id).where(Book.isbn == data.isbn)):
        raise Conflict(f"Book with ISBN {data.isbn} already exists")
    book = Book(**data.model_dump(), available_copies=data.total_copies)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def update_book(db: Session, book_id: int, data: BookUpdate) -> Book:
    # Row lock: total/available copies must change atomically with loans.
    book = db.scalar(select(Book).where(Book.id == book_id).with_for_update())
    if book is None:
        raise NotFound(f"Book {book_id} not found")
    changes = data.model_dump(exclude_unset=True)
    if "total_copies" in changes:
        on_loan = book.total_copies - book.available_copies
        if changes["total_copies"] < on_loan:
            raise Conflict(
                f"Cannot set total_copies below {on_loan}: copies currently on loan"
            )
        book.available_copies = changes["total_copies"] - on_loan
    for field, value in changes.items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book_id: int) -> None:
    book = get_book(db, book_id)
    if db.scalar(select(Loan.id).where(Loan.book_id == book_id).limit(1)):
        raise Conflict("Cannot delete a book that has loan history")
    db.delete(book)
    db.commit()
