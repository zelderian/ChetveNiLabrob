from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import cache
from app.config import settings
from app.db import engine
from app.redis_client import redis_client

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness():
    """Process is up (no dependency checks)."""
    return {"status": "ok", "instance": settings.instance_id}


@router.get("/health")
def readiness():
    """Ready to serve traffic: the DB and the session store are reachable."""
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["db"] = f"error: {str(exc)[:120]}"
    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {str(exc)[:120]}"

    healthy = all(v == "ok" for v in checks.values())
    # The cache is optional: without it the node still serves (from the DB),
    # so it is reported but does NOT make the node unready.
    body = {"status": "ok" if healthy else "degraded", "instance": settings.instance_id, **checks,
            "cache": cache.ping()}
    return JSONResponse(status_code=200 if healthy else 503, content=body)
