"""Lab 3 - runs all load-balancing experiments against the docker-compose stack.

    docker compose up -d --build
    python scripts/seed.py
    python load-tests/run_lab3.py              # everything (~6 min)
    python load-tests/run_lab3.py scale        # only one part: dist | slow | failover | scale

Results: load-tests/results/lab3/*.json, chart: python load-tests/report.py
"""
import sys
import threading
import time

from runner import compose, k6, log, python, wait_pool

ALL = {"app1", "app2", "app3"}
parts = set(sys.argv[1:]) or {"dist", "slow", "failover", "scale"}


def lb(algo="roundrobin", weights=(1, 1, 1), up=ALL):
    env = {"LB_ALGO": algo, **{f"APP{i}_WEIGHT": str(w) for i, w in enumerate(weights, 1)}}
    compose("up", "-d", "--no-deps", "lb", env=env)
    time.sleep(3)
    wait_pool(up)


if "dist" in parts:
    for algo, weights in [("roundrobin", (1, 1, 1)), ("roundrobin", (3, 2, 1)),
                          ("source", (1, 1, 1)), ("leastconn", (1, 1, 1))]:
        lb(algo, weights)
        log(f"distribution: {algo} weights={weights}")
        python("scripts/lb_distribution.py", "-n", "300" if weights == (1, 1, 1) else "600")

if "slow" in parts:
    compose("up", "-d", "--no-deps", "app3", env={"APP3_DELAY_MS": "200"})
    for algo in ("roundrobin", "leastconn"):
        lb(algo)
        time.sleep(12)  # let slowstart finish for app3
        k6("lb_experiment.js", f"lab3/slow_{algo}.json",
           {"VUS": 30, "DURATION": "30s", "LABEL": f"slow app-3 +200ms, {algo}"})
    compose("up", "-d", "--no-deps", "app3", env={"APP3_DELAY_MS": "0"})

if "failover" in parts:
    lb("roundrobin")
    time.sleep(12)

    def chaos():
        time.sleep(7)
        compose("stop", "app2")
        time.sleep(8)
        compose("start", "app2")

    t = threading.Thread(target=chaos)
    t.start()
    k6("lb_experiment.js", "lab3/failover_stop.json",
       {"VUS": 30, "DURATION": "25s", "LABEL": "failover: stop app2 at 7s, start at 15s"})
    t.join()

if "scale" in parts:
    compose("stop", "app2", "app3")
    for n in (1, 2, 3):
        if n > 1:
            compose("start", f"app{n}")
        lb("leastconn", up={f"app{i}" for i in range(1, n + 1)})
        time.sleep(10)
        k6("lb_experiment.js", f"lab3/scale_{n}.json",
           {"VUS": 50, "DURATION": "20s", "LABEL": f"scale-out: {n} instance(s)"})

lb("leastconn")
log("done - build tables/charts with: python load-tests/report.py")
