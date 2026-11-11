from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    published_year: int | None = Field(default=None, ge=1450)

    @field_validator("published_year")
    @classmethod
    def _not_future(cls, v: int | None) -> int | None:
        if v is not None and v > date.today().year:
            raise ValueError("published_year cannot be in the future")
        return v


class BookCreate(BookBase):
    isbn: str = Field(min_length=10, max_length=17, examples=["978-0-13-468599-1"])
    total_copies: int = Field(ge=1, le=1000)

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v: str) -> str:
        digits = v.replace("-", "")
        if not (digits.isdigit() and len(digits) in (10, 13)) and not (
            len(digits) == 10 and digits[:9].isdigit() and digits[9] in "Xx"
        ):
            raise ValueError("ISBN must contain 10 or 13 digits (hyphens allowed)")
        return digits.upper()


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    published_year: int | None = Field(default=None, ge=1450)
    total_copies: int | None = Field(default=None, ge=1, le=1000)


class BookOut(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    isbn: str
    total_copies: int
    available_copies: int
    created_at: datetime


class MemberCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    max_active_loans: int = Field(default=3, ge=1, le=10)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class MemberUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    max_active_loans: int | None = Field(default=None, ge=1, le=10)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    max_active_loans: int
    created_at: datetime


class LoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class LoanCreate(BaseModel):
    book_id: int = Field(ge=1)
    days: int = Field(default=14, ge=1, le=60)


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    book_id: int
    book_title: str
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None
    fine_amount: Decimal
    is_overdue: bool


class PopularBook(BaseModel):
    book_id: int
    title: str
    author: str
    loans_count: int


class PopularBooksReport(BaseModel):
    period_days: int
    generated_at: datetime
    items: list[PopularBook]
