"""Lab 5 - runs the full load-testing programme against the docker-compose stack.

    docker compose up -d --build
    docker compose exec -T db psql -U libra -d libra < scripts/bulk_seed.sql   # realistic volume
    python load-tests/run_lab5.py                    # everything (~20 min)
    python load-tests/run_lab5.py baseline           # only some runs: baseline scale no_cache
    python load-tests/report.py lab5                 # tables + charts

Runs (each = warm-up + steps 10/25/50/100/200 VUs, 30 s per step):
  baseline   3 instances, cache ON : scenarios A, B, C
  scale      scenario A with 1 and 2 instances (3 = baseline)    -> Scaling Impact
  no_cache   scenario A, 3 instances, CACHE_ENABLED=false        -> Caching Impact

For every run the script also records how much work PostgreSQL and the cache
did (pg_stat_database / Redis INFO deltas) -> results/lab5/<run>/dbstats.json.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

from runner import BASE_URL, RESULTS, compose, k6, log, wait_pool

runs = set(sys.argv[1:]) or {"baseline", "scale", "no_cache"}
ALL = {"app1", "app2", "app3"}
STEP_ENV = {k: os.environ[k] for k in ("LEVELS", "STAGE", "WARMUP") if k in os.environ}

PG_SQL = ("SELECT json_build_object('xact_commit', xact_commit, 'xact_rollback', xact_rollback, "
          "'tup_returned', tup_returned, 'tup_fetched', tup_fetched, "
          "'tup_inserted', tup_inserted, 'tup_updated', tup_updated, "
          "'blks_read', blks_read, 'blks_hit', blks_hit) "
          "FROM pg_stat_database WHERE datname = current_database()")


def pg_stats() -> dict:
    try:
        out = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "libra", "-d",
                              "libra", "-tAc", PG_SQL], capture_output=True, text=True, timeout=20)
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        log(f"pg stats unavailable: {exc}")
        return {}


def cache_stats() -> dict:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/v1/cache/stats", timeout=5) as r:
            s = json.load(r)["server"]
        return {"cache_server_hits": s.get("server_keyspace_hits") or 0,
                "cache_server_misses": s.get("server_keyspace_misses") or 0}
    except Exception:  # noqa: BLE001
        return {}


def measured(run: str, scenario: str, label: str, extra_env: dict | None = None) -> None:
    before, cbefore, t0 = pg_stats(), cache_stats(), time.time()
    k6(f"{scenario}.js", f"lab5/{run}/{scenario}.json",
       {**STEP_ENV, "LABEL": label, **(extra_env or {})})
    after, cafter = pg_stats(), cache_stats()
    delta = {k: after[k] - before[k] for k in after if k in before}
    delta.update({k: cafter[k] - cbefore[k] for k in cafter if k in cbefore})
    delta["wall_seconds"] = round(time.time() - t0, 1)
    path = os.path.join(RESULTS, "lab5", run, "dbstats.json")
    data = json.load(open(path)) if os.path.exists(path) else {}
    data[scenario] = delta
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    log(f"{run}/{scenario}: DB/cache deltas {delta}")


def set_pool(n: int, cache: bool = True) -> None:
    env = {"CACHE_ENABLED": "true" if cache else "false"}
    compose("up", "-d", "--no-deps", "app1", "app2", "app3", env=env)  # recreate if env changed
    if n < 3:
        compose("stop", *[f"app{i}" for i in range(n + 1, 4)])
    compose("up", "-d", "--no-deps", "lb", env={"LB_ALGO": "leastconn"})
    time.sleep(3)
    wait_pool({f"app{i}" for i in range(1, n + 1)})
    time.sleep(10)  # slowstart


def environment_spec() -> None:
    spec = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        out = subprocess.run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        spec["docker_host_cpus"], spec["docker_host_mem_gb"] = int(out[0]), round(int(out[1]) / 2**30, 1)
    except Exception:  # noqa: BLE001
        spec["docker_host_cpus"] = os.cpu_count()
    spec.update({"backend_instances": 3, "instance_limits": "cpus=1.0, mem=512m, 1 uvicorn process",
                 "db_pool_per_instance": "pool_size=10 + max_overflow=5",
                 "postgres": "16-alpine, default config (max_connections=100)",
                 "cache": "redis 7, maxmemory 128mb, volatile-lfu",
                 "load_balancer": "HAProxy 2.8, leastconn",
                 "load_generator": "k6 (local binary)" if not os.getenv("K6_DOCKER") else "k6 in Docker"})
    os.makedirs(os.path.join(RESULTS, "lab5"), exist_ok=True)
    with open(os.path.join(RESULTS, "lab5", "environment.json"), "w") as f:
        json.dump(spec, f, indent=1)
    log(f"environment: {spec}")


environment_spec()

if "baseline" in runs:
    set_pool(3)
    for sc, label in (("scenario_a_read", "baseline A"), ("scenario_b_write", "baseline B"),
                      ("scenario_c_workflow", "baseline C")):
        measured("baseline", sc, label)

if "scale" in runs:
    for n in (1, 2):
        set_pool(n)
        measured(f"scale_{n}", "scenario_a_read", f"scale {n} instance(s)")
    set_pool(3)

if "no_cache" in runs:
    set_pool(3, cache=False)
    measured("no_cache", "scenario_a_read", "cache disabled")
    set_pool(3, cache=True)

log("done - python load-tests/report.py lab5")
