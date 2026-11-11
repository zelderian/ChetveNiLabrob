"""Fills the system with demo data through the public API.

    python scripts/seed.py [base_url] [members] [books] [loans]
    python scripts/seed.py http://localhost:8080 20 50 60
"""
import random
import sys
import time

from _http import request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
N_MEMBERS = int(sys.argv[2]) if len(sys.argv) > 2 else 20
N_BOOKS = int(sys.argv[3]) if len(sys.argv) > 3 else 50
N_LOANS = int(sys.argv[4]) if len(sys.argv) > 4 else 60

AUTHORS = ["Robert Martin", "Martin Fowler", "Martin Kleppmann", "Eric Evans",
           "Sam Newman", "Alex Xu", "Kent Beck", "Ivan Franko", "Lesya Ukrainka"]
WORDS = ["Clean", "Distributed", "Domain", "Systems", "Patterns", "Design",
         "Data", "Scalable", "Reliable", "Microservices", "Architecture", "Code"]

run = str(int(time.time()))[-6:]
rnd = random.Random(42)

book_ids = []
for i in range(N_BOOKS):
    r = request("POST", f"{BASE}/api/v1/books", {
        "isbn": f"979{run}{i:04d}",
        "title": " ".join(rnd.sample(WORDS, 3)),
        "author": rnd.choice(AUTHORS),
        "published_year": rnd.randint(1990, 2025),
        "total_copies": rnd.randint(1, 5),
    })
    if r.status == 201:
        book_ids.append(r.json()["id"])

tokens = []
for i in range(N_MEMBERS):
    email = f"reader{run}_{i}@example.com"
    request("POST", f"{BASE}/api/v1/members",
            {"full_name": f"Reader {i}", "email": email, "password": "password123",
             "max_active_loans": 5})
    t = request("POST", f"{BASE}/api/v1/auth/login", {"email": email, "password": "password123"})
    tokens.append({"Authorization": f"Bearer {t.json()['access_token']}"})

ok = conflicts = 0
# Zipf-like skew: a few "bestsellers" are requested far more often.
weights = [1 / (i + 1) for i in range(len(book_ids))]
for _ in range(N_LOANS):
    book = rnd.choices(book_ids, weights)[0]
    r = request("POST", f"{BASE}/api/v1/loans", {"book_id": book}, rnd.choice(tokens))
    ok += r.status == 201
    conflicts += r.status == 409

print(f"books={len(book_ids)} members={len(tokens)} loans_created={ok} rejected_409={conflicts}")
