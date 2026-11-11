from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import cache
from app.config import settings
from app.errors import Conflict, NotFound
from app.models import Book, Loan
from app.schemas import BookCreate, BookOut, BookUpdate, Page

LIST_VERSION = "books:list"
REPORT_VERSION = "report:popular"


def book_version(book_id: int) -> str:
    return f"book:{book_id}"


def invalidate_book(book_id: int) -> None:
    cache.invalidate(book_version(book_id), LIST_VERSION, REPORT_VERSION)


def get_book(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise NotFound(f"Book {book_id} not found")
    return book


def get_book_cached(db: Session, book_id: int) -> tuple[BookOut, str]:
    return cache.cache_aside(
        key=f"{cache.PREFIX}:book:{book_id}",
        versions=(book_version(book_id),),
        ttl=settings.cache_ttl_book,
        loader=lambda: BookOut.model_validate(get_book(db, book_id)),
        dump=lambda b: b.model_dump_json(),
        load=BookOut.model_validate_json,
    )


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


def list_books_cached(
    db: Session, q: str | None, author: str | None, available_only: bool, limit: int, offset: int
) -> tuple[Page[BookOut], str]:
    q_norm = (q or "").strip().lower() or None
    author_norm = (author or "").strip() or None
    h = cache.params_hash(q=q_norm, author=author_norm, available_only=available_only,
                          limit=limit, offset=offset)

    def load_page() -> Page[BookOut]:
        items, total = list_books(db, q_norm, author_norm, available_only, limit, offset)
        return Page[BookOut](items=[BookOut.model_validate(b) for b in items],
                             total=total, limit=limit, offset=offset)

    return cache.cache_aside(
        key=f"{cache.PREFIX}:books:list:{h}",
        versions=(LIST_VERSION,),
        ttl=settings.cache_ttl_list,
        loader=load_page,
        dump=lambda p: p.model_dump_json(),
        load=Page[BookOut].model_validate_json,
    )


def create_book(db: Session, data: BookCreate) -> Book:
    if db.scalar(select(Book.id).where(Book.isbn == data.isbn)):
        raise Conflict(f"Book with ISBN {data.isbn} already exists")
    book = Book(**data.model_dump(), available_copies=data.total_copies)
    db.add(book)
    db.commit()
    db.refresh(book)
    cache.invalidate(LIST_VERSION)
    return book


def update_book(db: Session, book_id: int, data: BookUpdate) -> Book:
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
    invalidate_book(book_id)
    return book


def delete_book(db: Session, book_id: int) -> None:
    book = get_book(db, book_id)
    if db.scalar(select(Loan.id).where(Loan.book_id == book_id).limit(1)):
        raise Conflict("Cannot delete a book that has loan history")
    db.delete(book)
    db.commit()
    invalidate_book(book_id)
