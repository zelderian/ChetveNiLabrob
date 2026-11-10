"""Walks through the main API endpoints (for the Lab 1 defence).

    python scripts/demo.py                 # against http://localhost:8000
    python scripts/demo.py http://host:port
"""
import json
import sys
import time

from _http import request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
suffix = str(int(time.time()))


def show(title, r):
    print(f"\n=== {title}  ->  HTTP {r.status}")
    if r.text:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:800])


show("GET /health", request("GET", f"{BASE}/health"))

m = request("POST", f"{BASE}/api/v1/members", {
    "full_name": "Taras Shevchenko", "email": f"taras{suffix}@example.com",
    "password": "kobzar1840", "max_active_loans": 2,
})
show("POST /api/v1/members (create member)", m)

b = request("POST", f"{BASE}/api/v1/books", {
    "isbn": f"978{suffix[-10:]}", "title": "Designing Data-Intensive Applications",
    "author": "Martin Kleppmann", "published_year": 2017, "total_copies": 1,
})
show("POST /api/v1/books (create book)", b)
book_id = b.json()["id"]

show("GET /api/v1/books?q=data", request("GET", f"{BASE}/api/v1/books?q=data&limit=5"))
show("POST /api/v1/books (invalid -> 422)", request("POST", f"{BASE}/api/v1/books", {"isbn": "x"}))

t = request("POST", f"{BASE}/api/v1/auth/login",
            {"email": f"taras{suffix}@example.com", "password": "kobzar1840"})
show("POST /api/v1/auth/login", t)
auth = {"Authorization": f"Bearer {t.json()['access_token']}"}

loan = request("POST", f"{BASE}/api/v1/loans", {"book_id": book_id, "days": 14}, auth)
show("POST /api/v1/loans (borrow)", loan)
show("POST /api/v1/loans (same book again -> 409)",
     request("POST", f"{BASE}/api/v1/loans", {"book_id": book_id}, auth))
show("GET /api/v1/me/loans?active=true", request("GET", f"{BASE}/api/v1/me/loans?active=true", headers=auth))
show("POST /api/v1/loans/{id}/return",
     request("POST", f"{BASE}/api/v1/loans/{loan.json()['id']}/return", headers=auth))
show("GET /api/v1/reports/popular-books (high-load)",
     request("GET", f"{BASE}/api/v1/reports/popular-books?days=30&limit=5"))
show("GET /api/v1/books/999999 (-> 404)", request("GET", f"{BASE}/api/v1/books/999999"))
