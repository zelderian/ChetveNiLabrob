from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db import engine


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- books ----------

def test_book_crud(client, make_book):
    book = make_book(copies=3)
    assert book["available_copies"] == 3

    r = client.get(f"/api/v1/books/{book['id']}")
    assert r.status_code == 200

    r = client.patch(f"/api/v1/books/{book['id']}", json={"title": "Refactoring"})
    assert r.json()["title"] == "Refactoring"

    r = client.get("/api/v1/books", params={"q": "refactor"})
    assert r.json()["total"] == 1

    assert client.delete(f"/api/v1/books/{book['id']}").status_code == 204
    assert client.get(f"/api/v1/books/{book['id']}").status_code == 404


def test_book_validation_and_duplicates(client, make_book):
    r = client.post("/api/v1/books", json={"isbn": "abc", "title": "", "author": "x", "total_copies": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"

    book = make_book()
    r = client.post("/api/v1/books", json={"isbn": book["isbn"], "title": "t", "author": "a",
                                           "total_copies": 1})
    assert r.status_code == 409


# ---------- members & auth ----------

def test_member_and_login(client, member, auth):
    assert "password" not in member and "password_hash" not in member
    r = client.post("/api/v1/members", json={"full_name": "x", "email": "IVAN@example.com",
                                             "password": "12345678"})
    assert r.status_code == 409  # e-mails are case-insensitive

    r = client.get("/api/v1/me", headers=auth)
    assert r.status_code == 200 and r.json()["id"] == member["id"]

    bad = client.post("/api/v1/auth/login", json={"email": "ivan@example.com", "password": "nope"})
    assert bad.status_code == 401

    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204
    assert client.get("/api/v1/me", headers=auth).status_code == 401


def test_requires_auth(client):
    assert client.post("/api/v1/loans", json={"book_id": 1}).status_code == 401


# ---------- loans (business logic) ----------

def test_borrow_and_return(client, auth, make_book):
    book = make_book(copies=1)
    r = client.post("/api/v1/loans", json={"book_id": book["id"], "days": 7}, headers=auth)
    assert r.status_code == 201, r.text
    loan = r.json()
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 0

    # no copies left
    r = client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=auth)
    assert r.status_code == 409

    r = client.post(f"/api/v1/loans/{loan['id']}/return", headers=auth)
    assert r.status_code == 200
    assert r.json()["fine_amount"] == "0.00"
    assert client.get(f"/api/v1/books/{book['id']}").json()["available_copies"] == 1

    # double return
    assert client.post(f"/api/v1/loans/{loan['id']}/return", headers=auth).status_code == 409


def test_loan_limit_and_duplicate(client, auth, make_book):
    b1, b2, b3 = make_book(2), make_book(), make_book()
    assert client.post("/api/v1/loans", json={"book_id": b1["id"]}, headers=auth).status_code == 201
    r = client.post("/api/v1/loans", json={"book_id": b1["id"]}, headers=auth)
    assert r.status_code == 409 and "already" in r.json()["error"]["message"]
    assert client.post("/api/v1/loans", json={"book_id": b2["id"]}, headers=auth).status_code == 201
    r = client.post("/api/v1/loans", json={"book_id": b3["id"]}, headers=auth)
    assert r.status_code == 409 and "limit" in r.json()["error"]["message"]

    r = client.get("/api/v1/me/loans", params={"active": True}, headers=auth)
    assert len(r.json()) == 2


def test_overdue_fine(client, auth, make_book):
    book = make_book()
    loan = client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=auth).json()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE loans SET due_at = :d WHERE id = :id"),
            {"d": datetime.now(timezone.utc) - timedelta(days=3, hours=1), "id": loan["id"]},
        )
    r = client.post(f"/api/v1/loans/{loan['id']}/return", headers=auth)
    assert r.json()["fine_amount"] == "20.00"  # 4 started days * 5.00


def test_cannot_delete_with_history(client, member, auth, make_book):
    book = make_book()
    client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=auth)
    assert client.delete(f"/api/v1/books/{book['id']}").status_code == 409
    assert client.delete(f"/api/v1/members/{member['id']}").status_code == 409


def test_cannot_shrink_below_on_loan(client, auth, make_book):
    book = make_book(copies=2)
    client.post("/api/v1/loans", json={"book_id": book["id"]}, headers=auth)
    assert client.patch(f"/api/v1/books/{book['id']}", json={"total_copies": 0}).status_code == 422
    r = client.patch(f"/api/v1/books/{book['id']}", json={"total_copies": 5})
    assert r.json()["available_copies"] == 4


# ---------- reports ----------

def test_popular_books_report(client, auth, make_book):
    b1, b2 = make_book(), make_book()
    client.post("/api/v1/loans", json={"book_id": b2["id"]}, headers=auth)
    r = client.get("/api/v1/reports/popular-books", params={"days": 7, "limit": 5})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and items[0]["book_id"] == b2["id"]
