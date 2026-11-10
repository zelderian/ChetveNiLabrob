from fastapi import Header

from app.errors import Unauthorized
from app.sessions import resolve_session


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing bearer token")
    return authorization[7:].strip()


def current_member_id(authorization: str | None = Header(default=None)) -> int:
    token = bearer_token(authorization)
    member_id = resolve_session(token)
    if member_id is None:
        raise Unauthorized("Invalid or expired token")
    return member_id
