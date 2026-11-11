import asyncio
import logging
import time

from fastapi import FastAPI, Request

from app.config import settings
from app.errors import register_error_handlers
from app.routers import auth, books, cache, health, loans, members, reports

logging.basicConfig(
    level=settings.log_level,
    format=f"%(asctime)s %(levelname)s [{settings.instance_id}] %(name)s %(message)s",
)
access_log = logging.getLogger("libra.access")

app = FastAPI(
    title="Libra - Library Lending API",
    version="4.0.0",
    description="Stateless API behind a load balancer, with a distributed cache (labs 1-5).",
)
register_error_handlers(app)


@app.middleware("http")
async def instance_and_logging(request: Request, call_next):
    started = time.perf_counter()
    if settings.chaos_delay_ms and request.url.path.startswith("/api/"):
        await asyncio.sleep(settings.chaos_delay_ms / 1000)
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Instance-ID"] = settings.instance_id
    access_log.info(
        "%s %s -> %s (%.1f ms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


for r in (health.router, auth.router, members.router, books.router, loans.router, reports.router,
          cache.router):
    app.include_router(r)
