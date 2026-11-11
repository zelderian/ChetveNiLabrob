"""Lab 4: Cache-Aside, key design, invalidation and fallback."""
import dataclasses

import pytest
import redis

from app import cache
from app.cache import cache_client


@pytest.fixture
def cache_down(monkeypatch):
    """Points the cache client at a port where nothing listens."""
    dead = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, socket_connect_timeout=0.2,
                       decode_responses=True)
    monkeypatch.setattr(cache, "cache_client", dead)
    monkeypatch.setattr(cache, "_breaker_open_until", 0.0)
    yield
    monkeypatch.setattr(cache, "_breaker_open_until", 0.0)


def test_book_hit_miss(client, make_book):
    book = make_book()
    r1 = client.get(f"/api/v1/books/{book['id']}")
    r2 = client.get(f"/api/v1/books/{book['id']}")
    assert (r1.headers["X-Cache"], r2.headers["X-Cache"]) == ("MISS", "HIT")
    assert r1.json() == r2.json()
    assert cache_client.get(f"libra:book:{book['id']}:v0") is not None


def test_key_design_no_collisions_and_normalisation(client, make_book):
    make_book()
    a = client.get("/api/v1/books?q=Clean&limit=5")
    b = client.get("/api/v1/books?q=clean%20&limit=5")       # same after normalisation
    c = client.get("/api/v1/books?q=clean&limit=6")           # different params -> other key
    assert (a.headers["X-Cache"], b.headers["X-Cache"], c.headers["X-Cache"]) == ("MISS", "HIT", "MISS")
    keys = sorted(k for k in cache_client.scan_iter("libra:books:list:*"))
    assert len(keys) == 2
    assert all(len(k.split(":")[3]) == 16 for k in keys)  # libra:books:list:<hash16>:v<ver>


def test_update_invalidates_entity_and_lists(client, make_book):
    book = make_book()
    client.get(f"/api/v1/books/{book['id']}")
    client.get("/api/v1/books?limit=5")
    client.patch(f"/api/v1/books/{book['id']}", json={"title": "Fresh Title"})

    r = client.get(f"/api/v1/books/{book['id']}")
    assert r.headers["X-Cache"] == "MISS" and r.json()["title"] == "Fresh Title"
    r = client.get("/api/v1/books?limit=5")
    assert r.headers["X-Cache"] == "MISS" and r.json()["items"][0]["title"] == "Fresh Title"


def test_create_and_delete_invalidate_lists(client, make_book):
    make_book()
    assert client.get("/api/v1/books").json()["total"] == 1
    b2 = make_book()
    r = client.get("/api/v1/books")
    assert r.headers["X-Cache"] == "MISS" and r.json()["total"] == 2
    client.delete(f"/api/v1/books/{b2['id']}")
    assert client.get("/api/v1/books").json()["total"] == 1
    assert client.get(f"/api/v1/books/{b2['id']}").status_code == 404  # no stale entity


def test_borrow_and_return_invalidate_availability(client, auth, make_book):
    book = make_book(copies=2)
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 2
    loan = client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=auth).json()
    r = client.get(f"/api/v1/books/{book['id']}")
    assert r.headers["X-Cache"] == "MISS" and r.json()["available_copies"] == 1
    client.post(f"/api/v1/loans/{loan['id']}/return", headers=auth)
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 2


def test_stale_writer_race_is_harmless(client, make_book):
    """A reader that stores an old value AFTER the writer's invalidation writes
    it under the old version key - nobody reads it any more."""
    book = make_book()
    client.get(f"/api/v1/books/{book['id']}")                       # cached as v0
    client.patch(f"/api/v1/books/{book['id']}", json={"title": "New"})
    cache_client.set(f"libra:book:{book['id']}:v0", '{"stale": true}')  # late stale write
    assert client.get(f"/api/v1/books/{book['id']}").json()["title"] == "New"


def test_ttl_is_set_with_jitter(client, make_book):
    book = make_book()
    client.get(f"/api/v1/books/{book['id']}")
    ttl = cache_client.ttl(f"libra:book:{book['id']}:v0")
    assert 270 <= ttl <= 330


def test_fallback_when_cache_is_down(client, make_book, cache_down):
    book = make_book()
    r = client.get(f"/api/v1/books/{book['id']}")
    assert r.status_code == 200 and r.headers["X-Cache"] == "BYPASS"
    assert r.json()["id"] == book["id"]
    assert client.get("/api/v1/books").headers["X-Cache"] == "BYPASS"
    assert client.get("/api/v1/reports/popular-books").headers["X-Cache"] == "BYPASS"
    # writes still work (invalidation failures are tolerated)
    assert client.patch(f"/api/v1/books/{book['id']}", json={"title": "X"}).status_code == 200
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["cache"].startswith("unavailable")


def test_cache_disabled_mode(client, make_book, monkeypatch):
    monkeypatch.setattr(cache, "settings", dataclasses.replace(cache.settings, cache_enabled=False))
    book = make_book()
    assert client.get(f"/api/v1/books/{book['id']}").headers["X-Cache"] == "DISABLED"


def test_stats_endpoint(client, make_book):
    book = make_book()
    client.get(f"/api/v1/books/{book['id']}")
    client.get(f"/api/v1/books/{book['id']}")
    s = client.get("/api/v1/cache/stats").json()
    assert s["instance_counters"]["hit"] >= 1 and s["instance_counters"]["miss"] >= 1
    assert s["server"]["status"] == "ok"
