from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound, Unauthorized
from app.models import Loan, Member
from app.schemas import MemberCreate, MemberUpdate
from app.security import hash_password, verify_password


def get_member(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise NotFound(f"Member {member_id} not found")
    return member


def list_members(db: Session, q: str | None, limit: int, offset: int) -> tuple[list[Member], int]:
    stmt = select(Member)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Member.full_name.ilike(like), Member.email.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Member.id).limit(limit).offset(offset)).all()
    return list(items), total or 0


def create_member(db: Session, data: MemberCreate) -> Member:
    if db.scalar(select(Member.id).where(Member.email == data.email)):
        raise Conflict(f"Member with e-mail {data.email} already exists")
    member = Member(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        max_active_loans=data.max_active_loans,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def update_member(db: Session, member_id: int, data: MemberUpdate) -> Member:
    member = get_member(db, member_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    db.commit()
    db.refresh(member)
    return member


def delete_member(db: Session, member_id: int) -> None:
    member = get_member(db, member_id)
    if db.scalar(select(Loan.id).where(Loan.member_id == member_id).limit(1)):
        raise Conflict("Cannot delete a member that has loan history")
    db.delete(member)
    db.commit()


def authenticate(db: Session, email: str, password: str) -> Member:
    member = db.scalar(select(Member).where(Member.email == email.lower()))
    if member is None or not verify_password(password, member.password_hash):
        raise Unauthorized("Invalid e-mail or password")
    return member
