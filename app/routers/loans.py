from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member_id
from app.schemas import LoanCreate, LoanOut
from app.services import loans as svc

router = APIRouter(prefix="/api/v1", tags=["loans"])


@router.post("/loans", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def borrow(
    data: LoanCreate,
    member_id: int = Depends(current_member_id),
    db: Session = Depends(get_db),
):
    """Borrow a book: checks availability, loan limit and duplicates."""
    return svc.to_out(svc.borrow_book(db, member_id, data.book_id, data.days))


@router.post("/loans/{loan_id}/return", response_model=LoanOut)
def return_loan(
    loan_id: int,
    member_id: int = Depends(current_member_id),
    db: Session = Depends(get_db),
):
    """Return a book; a fine is charged for every overdue day."""
    return svc.to_out(svc.return_book(db, member_id, loan_id))


@router.get("/me/loans", response_model=list[LoanOut])
def my_loans(
    active: bool = False,
    member_id: int = Depends(current_member_id),
    db: Session = Depends(get_db),
):
    return [svc.to_out(l) for l in svc.list_member_loans(db, member_id, active)]
