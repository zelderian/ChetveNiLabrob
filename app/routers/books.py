from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BookCreate, BookOut, BookUpdate, Page
from app.services import books as svc

router = APIRouter(prefix="/api/v1/books", tags=["books"])


@router.post("", response_model=BookOut, status_code=status.HTTP_201_CREATED)
def create_book(data: BookCreate, db: Session = Depends(get_db)):
    return svc.create_book(db, data)


@router.get("", response_model=Page[BookOut])
def list_books(
    q: str | None = Query(default=None, max_length=100, description="Search in title/author"),
    author: str | None = None,
    available_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = svc.list_books(db, q, author, available_only, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)):
    return svc.get_book(db, book_id)


@router.patch("/{book_id}", response_model=BookOut)
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    return svc.update_book(db, book_id, data)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    svc.delete_book(db, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
