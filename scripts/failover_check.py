"""Lab 2 - Restart / Instance Loss scenario.

Several clients run borrow -> return cycles against BOTH instances in
parallel. In the middle of the run one instance is killed (SIGKILL).
Clients that hit the dead node retry the same request on the other node
(with the same Idempotency-Key). At the end the script verifies against
the server that no business state was lost or duplicated.

    # docker-compose setup (kills app1 at ~1/3 of the run, starts it at ~2/3):
    python scripts/failover_check.py --kill app1 --restart

    # any other setup: provide the commands yourself
    python scripts/failover_check.py --kill-cmd "kill -9 1234"
"""
import argparse
import http.client
import random
import subprocess
import threading
import time
import uuid
from collections import Counter

from _http import request

p = argparse.ArgumentParser()
p.add_argument("--nodes", nargs="+", default=["http://localhost:8001", "http://localhost:8002"])
p.add_argument("--clients", type=int, default=6)
p.add_argument("--duration", type=float, default=15.0, help="seconds")
p.add_argument("--kill", metavar="SERVICE", help="docker compose service to SIGKILL, e.g. app1")
p.add_argument("--restart", action="store_true", help="start the killed service again at 2/3")
p.add_argument("--kill-cmd", help="custom shell command that kills a node")
p.add_argument("--restart-cmd", help="custom shell command that brings it back")
args = p.parse_args()

if args.kill:
    args.kill_cmd = args.kill_cmd or f"docker compose kill -s SIGKILL {args.kill}"
    if args.restart:
        args.restart_cmd = args.restart_cmd or f"docker compose start {args.kill}"

lock = threading.Lock()
handled_by = Counter()
stats = Counter()


def call(method, path, body=None, headers=None, start=0):
    """Try nodes starting from `start`; fail over on network errors / 5xx."""
    nodes = args.nodes[start:] + args.nodes[:start]
    for attempt, base in enumerate(nodes * 2):  # two rounds over all nodes
        try:
            r = request(method, base + path, body, headers, timeout=5)
            if r.status < 500:
                with lock:
                    handled_by[r.instance] += 1
                    if attempt:
                        stats["failovers"] += 1
                return r, attempt > 0
        except (OSError, http.client.HTTPException):  # refused / reset / cut-off response
            pass
        time.sleep(0.2)
    raise RuntimeError(f"all nodes failed for {method} {path}")


def any_node(method, path, body=None, headers=None):
    return call(method, path, body, headers)[0]


# ---------- setup ----------
run = uuid.uuid4().hex[:8]
book = any_node("POST", "/api/v1/books", {
    "isbn": f"979{int(time.time()) % 10**10:010d}", "title": f"Failover book {run}",
    "author": "Chaos Monkey", "total_copies": 1000}).json()
clients = []
for i in range(args.clients):
    email = f"fo{run}_{i}@example.com"
    any_node("POST", "/api/v1/members", {"full_name": f"Client {i}", "email": email,
                                         "password": "password123", "max_active_loans": 3})
    tok = any_node("POST", "/api/v1/auth/login", {"email": email, "password": "password123"}).json()
    clients.append({"auth": {"Authorization": f"Bearer {tok['access_token']}"},
                    "borrowed": 0, "returned": 0, "active": None})

stop = threading.Event()


def worker(c):
    rnd = random.Random()
    while not stop.is_set():
        try:
            key = uuid.uuid4().hex
            r, _ = call("POST", "/api/v1/loans", {"book_id": book["id"]},
                        {**c["auth"], "Idempotency-Key": key}, start=rnd.randrange(len(args.nodes)))
            if r.status != 201:
                stats[f"unexpected borrow {r.status}"] += 1
                continue
            if r.headers.get("Idempotent-Replayed"):
                stats["idempotent replays"] += 1
            c["borrowed"] += 1
            c["active"] = r.json()["id"]

            r, retried = call("POST", f"/api/v1/loans/{c['active']}/return", headers=c["auth"],
                              start=rnd.randrange(len(args.nodes)))
            # 409 after a failover = the first attempt was committed before the node died.
            if r.status == 200 or (retried and r.status == 409):
                c["returned"] += 1
                c["active"] = None
            else:
                stats[f"unexpected return {r.status}"] += 1
        except RuntimeError:
            stats["unrecoverable"] += 1
            time.sleep(0.5)


threads = [threading.Thread(target=worker, args=(c,), daemon=True) for c in clients]
print(f"nodes={args.nodes} clients={args.clients} duration={args.duration}s")
t0 = time.time()
for t in threads:
    t.start()

if args.kill_cmd:
    time.sleep(args.duration / 3)
    print(f"[{time.time() - t0:5.1f}s] KILL   -> {args.kill_cmd}")
    subprocess.run(args.kill_cmd, shell=True, check=False)
    if args.restart_cmd:
        time.sleep(args.duration / 3)
        print(f"[{time.time() - t0:5.1f}s] START  -> {args.restart_cmd}")
        subprocess.run(args.restart_cmd, shell=True, check=False)
time.sleep(max(0.0, args.duration - (time.time() - t0)))
stop.set()
for t in threads:
    t.join(timeout=15)

# ---------- verification against the server ----------
print(f"\nrequests handled per instance: {dict(handled_by)}")
print(f"client stats: {dict(stats) or 'no errors'}")
problems = 0
total_borrowed = total_active = 0
for i, c in enumerate(clients):
    loans = any_node("GET", "/api/v1/me/loans", headers=c["auth"]).json()
    active = [l for l in loans if l["returned_at"] is None]
    total_borrowed += len(loans)
    total_active += len(active)
    ok = len(loans) == c["borrowed"] and len(active) == (1 if c["active"] else 0)
    problems += not ok
    print(f"client {i}: borrowed(client)={c['borrowed']:<4} loans(server)={len(loans):<4} "
          f"active(server)={len(active)}  {'OK' if ok else 'MISMATCH'}")

final = any_node("GET", f"/api/v1/books/{book['id']}").json()
inv_ok = final["available_copies"] == final["total_copies"] - total_active
problems += not inv_ok
print(f"\nbook: total={final['total_copies']} available={final['available_copies']} "
      f"active_loans={total_active} -> invariant available = total - active: "
      f"{'OK' if inv_ok else 'BROKEN'}")
print(f"business operations completed: {total_borrowed} borrows")
print(f"\nRESULT: {'PASSED - no state lost or duplicated' if problems == 0 and not stats['unrecoverable'] else 'FAILED'}")
