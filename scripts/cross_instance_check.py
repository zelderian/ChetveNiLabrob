"""Lab 2 - Cross-Instance Consistency check (no sticky sessions).

Every step is deliberately sent to a specific instance and the
X-Instance-ID response header proves which node handled it.

    python scripts/cross_instance_check.py
    python scripts/cross_instance_check.py http://localhost:8001 http://localhost:8002
"""
import sys
import time

from _http import request

I1 = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001").rstrip("/")
I2 = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8002").rstrip("/")
NODES = {"I1": I1, "I2": I2}

run = str(int(time.time()))
failures = 0
step_no = 0


def step(node, method, path, expect, body=None, headers=None, check=None, label=""):
    global failures, step_no
    step_no += 1
    r = request(method, NODES[node] + path, body, headers)
    ok = r.status == expect and (check is None or check(r))
    failures += not ok
    print(f"{step_no:>2}. [{'OK ' if ok else 'FAIL'}] {node} ({r.instance:<6}) "
          f"{method:<5} {path:<42} -> {r.status}  {label}")
    if not ok:
        print("     response:", r.text[:300])
    return r


print(f"I1 = {I1}\nI2 = {I2}\n")
print("-- Scenario A: POST -> I1, GET -> I2, PUT(PATCH) -> I2, GET -> I1 --")
b = step("I1", "POST", "/api/v1/books", 201, {
    "isbn": f"978{run[-10:]}", "title": "Release It!", "author": "Michael Nygard",
    "published_year": 2018, "total_copies": 2}, label="create book")
book_id = b.json()["id"]
step("I2", "GET", f"/api/v1/books/{book_id}", 200,
     check=lambda r: r.json()["title"] == "Release It!", label="I2 sees the book created on I1")
step("I2", "PATCH", f"/api/v1/books/{book_id}", 200, {"title": "Release It! 2nd ed."},
     label="update on I2")
step("I1", "GET", f"/api/v1/books/{book_id}", 200,
     check=lambda r: r.json()["title"] == "Release It! 2nd ed.", label="I1 sees the update from I2")

print("\n-- Scenario B: session created on I1 is valid on I2 --")
email = f"nygard{run}@example.com"
step("I2", "POST", "/api/v1/members", 201,
     {"full_name": "Stateless Reader", "email": email, "password": "password123"},
     label="register on I2")
t = step("I1", "POST", "/api/v1/auth/login", 200,
         {"email": email, "password": "password123"}, label="login on I1")
auth = {"Authorization": f"Bearer {t.json()['access_token']}"}
step("I2", "GET", "/api/v1/me", 200, headers=auth, label="token from I1 accepted by I2")

print("\n-- Scenario C: business flow alternates between instances --")
loan = step("I2", "POST", "/api/v1/loans", 201, {"book_id": book_id},
            {**auth, "Idempotency-Key": f"k-{run}"}, label="borrow on I2")
if loan.status != 201:
    print(f"\nRESULT: FAILED ({failures} step(s)) - cannot continue without a loan")
    sys.exit(1)
loan_id = loan.json()["id"]
step("I1", "POST", "/api/v1/loans", 201, {"book_id": book_id},
     {**auth, "Idempotency-Key": f"k-{run}"},
     check=lambda r: r.json()["id"] == loan_id and r.headers.get("Idempotent-Replayed") == "true",
     label="retry with same key on I1 -> same loan")
step("I1", "GET", f"/api/v1/books/{book_id}", 200,
     check=lambda r: r.json()["available_copies"] == 1, label="available_copies = 1 (not 0)")
step("I1", "GET", "/api/v1/me/loans?active=true", 200, headers=auth,
     check=lambda r: [x["id"] for x in r.json()] == [loan_id], label="I1 lists the loan made on I2")
step("I1", "GET", "/api/v1/reports/popular-books?days=1&limit=50", 200,
     check=lambda r: any(i["book_id"] == book_id for i in r.json()["items"]),
     label="report on I1 includes the loan")
step("I1", "POST", f"/api/v1/loans/{loan_id}/return", 200, headers=auth, label="return on I1")
step("I2", "POST", f"/api/v1/loans/{loan_id}/return", 409, headers=auth,
     label="second return on I2 is rejected")
step("I2", "GET", f"/api/v1/books/{book_id}", 200,
     check=lambda r: r.json()["available_copies"] == 2, label="available_copies back to 2")

print("\n-- Scenario D: logout on I2 invalidates the token on I1 --")
step("I2", "POST", "/api/v1/auth/logout", 204, headers=auth, label="logout on I2")
step("I1", "GET", "/api/v1/me", 401, headers=auth, label="I1 rejects the revoked token")

print(f"\nRESULT: {'PASSED' if failures == 0 else f'FAILED ({failures} step(s))'}")
sys.exit(1 if failures else 0)
