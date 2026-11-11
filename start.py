"""One-click start of the whole Libra stack (open in VS Code and press Run).

    python start.py            # build + start + wait until healthy + seed + demo
    python start.py --no-demo  # only build + start
    python start.py --down     # stop everything

Needs Docker Desktop (it is started automatically on Windows if installed).
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.realpath(__file__))
if os.name == "nt" and len(ROOT) > 1 and ROOT[1] == ":":
    ROOT = ROOT[0].upper() + ROOT[1:]
ENV = {**os.environ, "COMPOSE_BAKE": "false"}
BASE = "http://localhost:8080"
DOCKER_DESKTOP = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"


def step(title):
    print(f"\n{'=' * 70}\n>>> {title}\n{'=' * 70}", flush=True)


def run(*cmd, check=True):
    print("$ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=ENV)
    if check and r.returncode != 0:
        sys.exit(f"\nFAILED: {' '.join(cmd)} (exit code {r.returncode})")
    return r.returncode


def docker_ready():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_docker():
    step("1/5 Checking Docker")
    if not shutil.which("docker"):
        sys.exit("Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
    if not docker_ready():
        if os.name == "nt" and os.path.exists(DOCKER_DESKTOP):
            print("Docker engine is not running - starting Docker Desktop ...", flush=True)
            subprocess.Popen([DOCKER_DESKTOP])
        for i in range(90):
            if docker_ready():
                break
            if i % 5 == 0:
                print(f"  waiting for Docker engine ... {i * 2}s", flush=True)
            time.sleep(2)
        else:
            sys.exit("Docker engine did not start in 3 minutes. Start Docker Desktop manually and re-run.")
    run("docker", "version", "--format", "Docker client {{.Client.Version}}, server {{.Server.Version}}")
    run("docker", "compose", "version")


def wait_healthy(timeout=240):
    step("3/5 Waiting until the API answers through the load balancer")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
                if r.status == 200:
                    print(f"  {BASE}/health -> {r.read().decode()}")
                    return
        except Exception:  # noqa: BLE001
            pass
        print("  not ready yet ...", flush=True)
        time.sleep(4)
    run("docker", "compose", "ps", check=False)
    run("docker", "compose", "logs", "--tail", "40", check=False)
    sys.exit("The API did not become healthy - see logs above.")


def main():
    if "--down" in sys.argv:
        run("docker", "compose", "down")
        return
    ensure_docker()
    step("2/5 Building images and starting the stack (first run takes a few minutes)")
    run("docker", "compose", "up", "--build", "-d")
    run("docker", "compose", "ps")
    wait_healthy()
    if "--no-demo" not in sys.argv:
        step("4/5 Seeding demo data")
        run(sys.executable, "scripts/seed.py", check=False)
        step("5/5 API demo + load-balancer distribution")
        run(sys.executable, "scripts/demo.py", check=False)
        run(sys.executable, "scripts/lb_distribution.py", "-n", "90", check=False)
    print(f"""
{'=' * 70}
Libra is running:
  API / Swagger UI     {BASE}/docs
  HAProxy dashboard    http://localhost:8404
  Health               {BASE}/health
Stop with:  python start.py --down   (or docker compose down)
{'=' * 70}""")


if __name__ == "__main__":
    main()
