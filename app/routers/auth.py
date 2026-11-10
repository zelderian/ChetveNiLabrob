from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import bearer_token, current_member_id
from app.schemas import LoginRequest, MemberOut, TokenOut
from app.services import members as member_svc
from app.sessions import create_session, revoke_session

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    member = member_svc.authenticate(db, data.email, data.password)
    token, expires_at = create_session(member.id)
    return TokenOut(access_token=token, expires_at=expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(default=None)):
    revoke_session(bearer_token(authorization))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MemberOut)
def me(member_id: int = Depends(current_member_id), db: Session = Depends(get_db)):
    return member_svc.get_member(db, member_id)
