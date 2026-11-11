"""Shared helpers for the experiment runners (run_lab3.py, run_lab5.py).

* k6 is taken from PATH; if it is not installed the official Docker image is
  used instead (`docker compose --profile loadtest run --rm k6 ...`), so only
  Docker is required.
* The system under test is controlled with plain `docker compose` commands.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LT = os.path.join(ROOT, "load-tests")
RESULTS = os.path.join(LT, "results")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
STATS_URL = os.getenv("LB_STATS_URL", "http://localhost:8404/;csv")
USE_LOCAL_K6 = shutil.which("k6") is not None and os.getenv("K6_DOCKER") != "1"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def compose(*args: str, env: dict | None = None, check: bool = True) -> None:
    cmd = ["docker", "compose", *args]
    log("$ " + " ".join(cmd) + (f"   env={env}" if env else ""))
    subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})}, check=check)


def k6(script: str, out: str, env: dict | None = None, background: bool = False):
    """Runs a k6 script from load-tests/. `out` is relative to load-tests/results/."""
    env = {k: str(v) for k, v in (env or {}).items()}
    os.makedirs(os.path.dirname(os.path.join(RESULTS, out)), exist_ok=True)
    if USE_LOCAL_K6:
        cmd = ["k6", "run", "-q", "-e", f"BASE_URL={BASE_URL}",
               "-e", f"OUT={os.path.join(RESULTS, out)}"]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(os.path.join(LT, script))
        cwd = ROOT
    else:
        cmd = ["docker", "compose", "--profile", "loadtest", "run", "--rm", "k6", "run", "-q",
               "-e", "BASE_URL=http://lb:8080", "-e", f"OUT=/load-tests/results/{out}"]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(f"/load-tests/{script}")
        cwd = ROOT
    log(f"k6 {script} -> results/{out} {env}")
    if background:
        return subprocess.Popen(cmd, cwd=cwd)
    subprocess.run(cmd, cwd=cwd, check=False)
    return None


def pool_state() -> dict[str, str]:
    """{server: status} of the libra_pool backend from the HAProxy stats CSV."""
    with urllib.request.urlopen(STATS_URL, timeout=3) as r:
        text = r.read().decode().lstrip("# ")
    rows = csv.DictReader(io.StringIO(text))
    return {row["svname"]: row["status"] for row in rows
            if row["pxname"] == "libra_pool" and row["svname"] not in ("FRONTEND", "BACKEND")}


def wait_pool(up: set[str], timeout: float = 90) -> None:
    """Waits until exactly the servers in `up` are UP (others DOWN/MAINT)."""
    deadline = time.time() + timeout
    state = {}
    while time.time() < deadline:
        try:
            state = pool_state()
            now_up = {s for s, st in state.items() if st.startswith("UP")}
            if now_up == up and all(st == "UP" for s, st in state.items() if s in up):
                log(f"pool ready: {state}")
                return
        except OSError:
            pass
        time.sleep(1)
    log(f"WARNING: pool not in expected state {up}, current: {state}")


def load_summary(out: str) -> dict:
    with open(os.path.join(RESULTS, out), encoding="utf-8") as f:
        return json.load(f)


def python(script: str, *args: str) -> None:
    subprocess.run([sys.executable, os.path.join(ROOT, script), *args], cwd=ROOT, check=False)
