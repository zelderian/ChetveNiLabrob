"""Lab 4 - distributed cache demo (run against the load balancer).

    python scripts/cache_demo.py                 # HIT/MISS, cold vs hot, invalidation
    python scripts/cache_demo.py --fallback      # + stops the cache container and back

Steps:
  1. MISS -> HIT on the book card, catalogue page and report (+ X-Instance-ID:
     the HIT is often served by a DIFFERENT instance - the cache is shared);
  2. latency: cold (MISS, right after an invalidation) vs hot (HIT), N rounds;
  3. invalidation: PATCH a book -> next GET is a MISS with fresh data;
  4. fallback (--fallback): `docker compose stop cache` -> responses are
     X-Cache: BYPASS and still 200; `docker compose start cache` -> HIT again.
"""
import argparse
import os
import statistics
import subprocess
import time

from _http import request

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:8080")
p.add_argument("--rounds", type=int, default=30)
p.add_argument("--fallback", action="store_true")
args = p.parse_args()
BASE = args.url.rstrip("/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get(path):
    t0 = time.perf_counter()
    r = request("GET", BASE + path)
    return r, (time.perf_counter() - t0) * 1000


def show(label, r, ms):
    print(f"  {label:<38} HTTP {r.status}  X-Cache: {r.headers.get('X-Cache', '-'):<8} "
          f"instance: {r.instance:<6} {ms:7.1f} ms")


# a dedicated book for the demo
isbn = f"978{int(time.time() * 1000) % 10**10:010d}"
book = request("POST", BASE + "/api/v1/books", {"isbn": isbn, "title": "Cache Demo Book",
                                               "author": "Redis", "total_copies": 3}).json()
bid = book["id"]
paths = {
    "book card    GET /books/{id}": f"/api/v1/books/{bid}",
    "catalogue    GET /books?q=demo": "/api/v1/books?q=cache%20demo&limit=20",
    "report       GET /reports/popular-books": "/api/v1/reports/popular-books?days=365&limit=10",
}

print("\n1) Cache-Aside: first request MISS (DB), repeated request HIT (Redis)")
for label, path in paths.items():
    show(label + " #1", *get(path))
    show(label + " #2", *get(path))

print(f"\n2) Cold (MISS) vs hot (HIT) latency, {args.rounds} rounds each, client-side through LB")
print(f"  {'endpoint':<38} {'cold p50':>9} {'cold p95':>9} {'hot p50':>9} {'hot p95':>9} {'speed-up':>9}")
rows = {}
for label, path in paths.items():
    cold, hot = [], []
    for i in range(args.rounds):
        # PATCH invalidates the book card, every catalogue page and the report
        request("PATCH", f"{BASE}/api/v1/books/{bid}", {"published_year": 2000 + i % 20})
        r, ms = get(path)
        if r.headers.get("X-Cache") == "MISS":
            cold.append(ms)
        for _ in range(3):
            r, ms = get(path)
            if r.headers.get("X-Cache") == "HIT":
                hot.append(ms)

    def pct(xs, q):
        return statistics.quantiles(xs, n=100)[q - 1] if len(xs) > 2 else float("nan")

    c50, h50 = statistics.median(cold), statistics.median(hot)
    rows[label] = (c50, pct(cold, 95), h50, pct(hot, 95))
    print(f"  {label:<38} {c50:8.1f}ms {pct(cold, 95):8.1f}ms {h50:8.1f}ms {pct(hot, 95):8.1f}ms "
          f"{c50 / h50:8.1f}x")

print("\n3) Invalidation: PATCH -> next read is a MISS with fresh data")
path = paths["book card    GET /books/{id}"]
show("GET (warm)", *get(path))
request("PATCH", f"{BASE}/api/v1/books/{bid}", {"title": "Cache Demo Book (edited)"})
print("  PATCH /books/{id} {title: 'Cache Demo Book (edited)'}")
r, ms = get(path)
show("GET after PATCH", r, ms)
print(f"  title now: {r.json()['title']!r}")
show("GET again", *get(path))

if args.fallback:
    print("\n4) Fallback: stopping the cache container")
    subprocess.run(["docker", "compose", "stop", "cache"], cwd=ROOT, check=False)
    time.sleep(1)
    for label, p_ in paths.items():
        show(label, *get(p_))
    r = request("PATCH", f"{BASE}/api/v1/books/{bid}", {"title": "Edited while cache is down"})
    print(f"  PATCH while cache is down -> HTTP {r.status}")
    show("GET book card", *get(path))
    h = request("GET", BASE + "/health").json()
    print(f"  /health -> status={h['status']} cache={h['cache']!r}")
    print("  starting the cache container again")
    subprocess.run(["docker", "compose", "start", "cache"], cwd=ROOT, check=False)
    time.sleep(7)  # circuit breaker cooldown (5 s) + container start
    show("GET book card (cache back, cold)", *get(path))
    show("GET book card (cache back, hot)", *get(path))
