from fastapi import APIRouter

from app import cache

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


@router.get("/stats")
def cache_stats():
    """Hit / miss / invalidation counters of THIS instance + Redis server stats."""
    return cache.stats()
