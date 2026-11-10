import logging
import time

from fastapi import FastAPI, Request

from app.config import settings
from app.errors import register_error_handlers
from app.routers import auth, books, health, loans, members, reports

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
access_log = logging.getLogger("libra.access")

app = FastAPI(
    title="Libra - Library Lending API",
    version="1.0.0",
    description="Lab 1: System Design baseline (members, books, loans).",
)
register_error_handlers(app)


@app.middleware("http")
async def access_logging(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    access_log.info(
        "%s %s -> %s (%.1f ms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


for r in (health.router, auth.router, members.router, books.router, loans.router, reports.router):
    app.include_router(r)
