from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import PopularBooksReport
from app.services import reports as svc

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/popular-books", response_model=PopularBooksReport)
def popular_books(
    response: Response,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    report, cached = svc.popular_books(db, days, limit)
    response.headers["X-Cache"] = "HIT" if cached else "MISS"
    return report
