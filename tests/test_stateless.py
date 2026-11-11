import importlib
import threading

from app import sessions
from app.config import settings
from app.redis_client import redis_client


def test_instance_header(client):
    r = client.get("/api/v1/books")
    assert r.headers["X-Instance-ID"] == settings.instance_id


def test_health_reports_dependencies(client):
    body = client.get("/health").json()
    assert body["db"] == "ok" and body["redis"] == "ok"
    assert client.get("/health/live").status_code == 200


def test_session_lives_in_redis_not_in_process(client, auth):
    importlib.reload(sessions)
    assert client.get("/api/v1/me", headers=auth).status_code == 200
    assert any(k.startswith("session:") for k in redis_client.scan_iter("session:*"))
    token = auth["Authorization"].split()[1]
    assert redis_client.get(f"session:{token}") is None


def test_idempotent_borrow(client, auth, make_book):
    book = make_book(copies=3)
    headers = {**auth, "Idempotency-Key": "req-42"}
    first = client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=headers)
    retry = client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=headers)
    assert first.status_code == retry.status_code == 201
    assert retry.headers.get("Idempotent-Replayed") == "true"
    assert first.json()["id"] == retry.json()["id"]
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 2

    other = make_book()
    misuse = client.post("/api/v1/loans", json={"book_id": other["id"]}, headers=headers)
    assert misuse.status_code == 409


def test_concurrent_borrows_never_oversell(client, make_book):
    book = make_book(copies=5)
    tokens = []
    for i in range(20):
        email = f"racer{i}@example.com"
        client.post("/api/v1/members", json={"full_name": f"R{i}", "email": email,
                                             "password": "password123"})
        t = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
        tokens.append(t.json()["access_token"])

    results = []
    barrier = threading.Barrier(len(tokens))

    def worker(tok):
        barrier.wait()
        r = client.post("/api/v1/loans", json={"book_id": book["id"]},
                        headers={"Authorization": f"Bearer {tok}"})
        results.append(r.status_code)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(201) == 5
    assert results.count(409) == 15
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 0


def test_report_cache_is_shared_and_invalidated(client, auth, make_book):
    b1, b2 = make_book(), make_book()
    client.post("/api/v1/loans", json={"book_id": b1["id"]}, headers=auth)

    r1 = client.get("/api/v1/reports/popular-books?days=7")
    r2 = client.get("/api/v1/reports/popular-books?days=7")
    assert (r1.headers["X-Cache"], r2.headers["X-Cache"]) == ("MISS", "HIT")

    client.post("/api/v1/loans", json={"book_id": b2["id"]}, headers=auth)
    r3 = client.get("/api/v1/reports/popular-books?days=7")
    assert r3.headers["X-Cache"] == "MISS"
    assert {i["book_id"] for i in r3.json()["items"]} == {b1["id"], b2["id"]}


def test_login_lockout_is_shared(client, member):
    for _ in range(settings.login_max_failures):
        r = client.post("/api/v1/auth/login", json={"email": "ivan@example.com", "password": "bad"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "ivan@example.com", "password": "secret123"})
    assert r.status_code == 429
    assert redis_client.get("login_fail:ivan@example.com") == str(settings.login_max_failures)
