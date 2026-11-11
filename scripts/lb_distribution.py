"""Lab 3 - shows how the load balancer spreads requests over instances.

    python scripts/lb_distribution.py                       # 300 requests, 10 parallel
    python scripts/lb_distribution.py -n 600 -c 20 --path /api/v1/books?limit=5

Counts the X-Instance-ID header of every response, plus errors.
"""
import argparse
import threading
import time
from collections import Counter

from _http import request

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:8080")
p.add_argument("--path", default="/api/v1/books?limit=1")
p.add_argument("-n", "--requests", type=int, default=300)
p.add_argument("-c", "--concurrency", type=int, default=10)
args = p.parse_args()

hits, statuses, lock = Counter(), Counter(), threading.Lock()
algorithm = ["?"]
remaining = iter(range(args.requests))


def worker():
    for _ in remaining:
        try:
            r = request("GET", args.url.rstrip("/") + args.path, timeout=30)
            with lock:
                hits[r.instance] += 1
                statuses[r.status] += 1
                algorithm[0] = r.headers.get("X-LB-Algorithm", "?")
        except Exception as exc:  # noqa: BLE001
            with lock:
                statuses[type(exc).__name__] += 1


t0 = time.perf_counter()
threads = [threading.Thread(target=worker) for _ in range(args.concurrency)]
for t in threads:
    t.start()
for t in threads:
    t.join()
elapsed = time.perf_counter() - t0

total = sum(hits.values()) or 1
print(f"LB algorithm: {algorithm[0]}   requests: {args.requests}   "
      f"concurrency: {args.concurrency}   time: {elapsed:.1f}s")
for inst, n in sorted(hits.items()):
    print(f"  {inst:<8} {n:>5}  {n / total:6.1%}  {'#' * round(40 * n / total)}")
print(f"status codes: {dict(statuses)}")
