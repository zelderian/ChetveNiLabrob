from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import LoanOut, MemberCreate, MemberOut, MemberUpdate, Page
from app.services import loans as loan_svc
from app.services import members as svc

router = APIRouter(prefix="/api/v1/members", tags=["members"])


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(data: MemberCreate, db: Session = Depends(get_db)):
    return svc.create_member(db, data)


@router.get("", response_model=Page[MemberOut])
def list_members(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = svc.list_members(db, q, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: int, db: Session = Depends(get_db)):
    return svc.get_member(db, member_id)


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(member_id: int, data: MemberUpdate, db: Session = Depends(get_db)):
    return svc.update_member(db, member_id, data)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: int, db: Session = Depends(get_db)):
    svc.delete_member(db, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{member_id}/loans", response_model=list[LoanOut])
def member_loans(member_id: int, active: bool = False, db: Session = Depends(get_db)):
    svc.get_member(db, member_id)
    return [loan_svc.to_out(l) for l in loan_svc.list_member_loans(db, member_id, active)]
