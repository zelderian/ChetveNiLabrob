"""Builds Markdown tables and PNG charts from k6 summaries.

    python load-tests/report.py            # lab3 + lab5
    python load-tests/report.py lab5

Input : load-tests/results/lab3/*.json, load-tests/results/lab5/<run>/*.json
Output: load-tests/results/<lab>/report.md and docs/lab3-*.png, docs/lab5-*.png
"""
import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "load-tests", "results")
DOCS = os.path.join(ROOT, "docs")

C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 11, "axes.titlecolor": INK, "legend.frameon": False,
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
})


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def metric(data, name, key):
    m = data["metrics"].get(name)
    return m["values"].get(key) if m else None


def overall(data):
    dur = data["state"]["testRunDurationMs"] / 1000
    return {
        "rps": metric(data, "http_reqs", "count") / dur,
        "avg": metric(data, "http_req_duration", "avg"),
        "p50": metric(data, "http_req_duration", "med"),
        "p95": metric(data, "http_req_duration", "p(95)"),
        "p99": metric(data, "http_req_duration", "p(99)"),
        "err": 100 * (metric(data, "http_req_failed", "rate") or 0),
        "count": metric(data, "http_reqs", "count"),
    }


def per_stage(data):
    """Rows per constant-VU step (sub-metrics tagged scenario:vus_NNN)."""
    meta = data.get("meta", {})
    rows = []
    for vus in meta.get("levels", []):
        tag = f"{{scenario:vus_{vus:03d}}}"
        count = metric(data, "http_reqs" + tag, "count")
        if count is None:
            continue
        rows.append({
            "vus": vus,
            "rps": count / meta["stage_seconds"],
            "avg": metric(data, "http_req_duration" + tag, "avg"),
            "p50": metric(data, "http_req_duration" + tag, "med"),
            "p95": metric(data, "http_req_duration" + tag, "p(95)"),
            "p99": metric(data, "http_req_duration" + tag, "p(99)"),
            "max": metric(data, "http_req_duration" + tag, "max"),
            "err": 100 * (metric(data, "http_req_failed" + tag, "rate") or 0),
            "count": count,
            "iter": metric(data, "iteration_duration" + tag, "avg"),
        })
    return rows


def md_table(rows, cols):
    head = "| " + " | ".join(c[0] for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(c[2](r[c[1]]) for c in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def ms(v):
    return "-" if v is None else (f"{v:.0f} ms" if v >= 10 else f"{v:.1f} ms")


STAGE_COLS = [("VUs", "vus", str), ("Throughput (RPS)", "rps", lambda v: f"{v:.0f}"),
              ("Avg", "avg", ms), ("p50", "p50", ms), ("p95", "p95", ms), ("p99 (tail)", "p99", ms),
              ("Max", "max", ms), ("Error rate", "err", lambda v: f"{v:.2f} %")]


def label_end(ax, xs, ys, text, color):
    placed = getattr(ax, "_end_labels", [])
    lo, hi = ax.get_ylim() if ax.get_yscale() == "linear" else (0, 0)
    span = (hi - lo) or max(abs(ys[-1]), 1)
    dy = 0
    for y in placed:
        if abs(y - ys[-1]) < 0.04 * span:
            dy += 11
    placed.append(ys[-1])
    ax._end_labels = placed
    ax.annotate(text, (xs[-1], ys[-1]), xytext=(6, dy), textcoords="offset points",
                va="center", fontsize=9, color=INK)
    ax.plot(xs[-1], ys[-1], "o", ms=5, color=color, mec="#fcfcfb", mew=1.5)


def fig_legend(fig, ax, ncols=3):
    """Legend below the panels, so it never covers data."""
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncols=ncols, bbox_to_anchor=(0.5, 0.0))


def log_ms(ax):
    """Latency spans 10 ms .. 30 s under saturation: log scale keeps both readable."""
    from matplotlib.ticker import FuncFormatter, NullFormatter
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_ylabel("ms (log scale)")


def save(fig, name):
    path = os.path.join(DOCS, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("chart:", os.path.relpath(path, ROOT))


def lab3():
    d = os.path.join(RES, "lab3")
    out = ["# Lab 3 - results\n"]
    scale = [(n, overall(load(p))) for n in (1, 2, 3)
             if os.path.exists(p := os.path.join(d, f"scale_{n}.json"))]
    if scale:
        base = scale[0][1]["rps"]
        rows = [{"n": n, **r, "gain": r["rps"] / base, "eff": r["rps"] / (n * base)} for n, r in scale]
        out.append("## Scale-out (50 VUs)\n")
        out.append(md_table(rows, [("Instances", "n", str), ("RPS", "rps", lambda v: f"{v:.0f}"),
                                   ("Gain", "gain", lambda v: f"{v:.2f}x"),
                                   ("Efficiency", "eff", lambda v: f"{v:.0%}"),
                                   ("Avg", "avg", ms), ("p50", "p50", ms), ("p95", "p95", ms),
                                   ("p99", "p99", ms), ("Errors", "err", lambda v: f"{v:.2f} %")]))
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
        xs = [str(r["n"]) for r in rows]
        bars = a1.bar(xs, [r["rps"] for r in rows], color=C[0], width=0.55)
        for b, r in zip(bars, rows):
            a1.annotate(f"{r['rps']:.0f}\n({r['gain']:.2f}x)", (b.get_x() + b.get_width() / 2, b.get_height()),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=9)
        a1.set(title="Throughput", xlabel="backend instances", ylabel="requests / s")
        a1.set_ylim(0, max(r["rps"] for r in rows) * 1.25)
        a1.grid(axis="x", visible=False)
        for i, (k, name) in enumerate([("p50", "p50"), ("p95", "p95"), ("p99", "p99")]):
            ys = [r[k] for r in rows]
            a2.plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=name)
            label_end(a2, xs, ys, name, C[i])
        a2.set(title="Latency percentiles", xlabel="backend instances", ylabel="ms")
        a2.set_ylim(0, max(r["p99"] for r in rows) * 1.3)
        a2.legend(loc="upper center", ncols=3)
        fig.suptitle("Lab 3 - scale-out, 50 VUs, GET /books/{id} through HAProxy (leastconn)",
                     fontsize=11, color=INK2)
        save(fig, "lab3-scaleout.png")

    for name in ("slow_roundrobin", "slow_leastconn", "failover_stop", "failover_kill", "rr_baseline"):
        p = os.path.join(d, f"{name}.json")
        if os.path.exists(p):
            data = load(p)
            r = overall(data)
            hits = {k.split("instance:")[1].rstrip("}"): v["values"]["count"]
                    for k, v in data["metrics"].items() if k.startswith("instance_hits{")}
            out.append(f"\n## {name}\nRPS {r['rps']:.0f}, avg {ms(r['avg'])}, p50 {ms(r['p50'])}, "
                       f"p95 {ms(r['p95'])}, p99 {ms(r['p99'])}, errors {r['err']:.2f} % "
                       f"({r['count']:.0f} requests); per instance: {hits}")
    write(os.path.join(d, "report.md"), out)


SCEN = {"A": "Scenario A - read-intensive", "B": "Scenario B - write-intensive",
        "C": "Scenario C - complex workflow"}


def lab5():
    base = os.path.join(RES, "lab5")
    runs = {os.path.basename(p): {os.path.basename(f)[:-5]: load(f)
                                   for f in sorted(glob.glob(os.path.join(p, "*.json")))
                                   if not f.endswith(("dbstats.json", "environment.json"))}
            for p in sorted(glob.glob(os.path.join(base, "*"))) if os.path.isdir(p)}
    if not runs:
        print("no lab5 results")
        return
    out = ["# Lab 5 - results\n"]
    for run, files in runs.items():
        for name, data in files.items():
            rows = per_stage(data)
            if rows:
                out.append(f"\n## {run} / {name}\n")
                out.append(md_table(rows, STAGE_COLS))
        dbp = os.path.join(base, run, "dbstats.json")
        if os.path.exists(dbp):
            out.append(f"\n### {run} - DB / cache counters (delta per run)\n```\n"
                       f"{json.dumps(load(dbp), indent=1)}\n```")
    write(os.path.join(base, "report.md"), out)

    bl = runs.get("baseline", {})
    names = {"A": "scenario_a_read", "B": "scenario_b_write", "C": "scenario_c_workflow"}
    if bl:
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        for i, (letter, key) in enumerate(names.items()):
            if key in bl:
                rows = per_stage(bl[key])
                xs, ys = [r["vus"] for r in rows], [r["rps"] for r in rows]
                axes[0].plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=SCEN[letter])
                label_end(axes[0], xs, ys, letter, C[i])
                ys = [r["p95"] for r in rows]
                axes[1].plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=SCEN[letter])
                label_end(axes[1], xs, ys, letter, C[i])
        axes[0].set(title="Throughput vs load", xlabel="virtual users", ylabel="requests / s")
        axes[1].set(title="p95 latency vs load", xlabel="virtual users")
        axes[0].set_ylim(bottom=0)
        log_ms(axes[1])
        fig_legend(fig, axes[0])
        fig.suptitle("Lab 5 - baseline (3 instances, cache on)", fontsize=11, color=INK2)
        save(fig, "lab5-baseline.png")

        for letter, key in names.items():
            if key not in bl:
                continue
            rows = per_stage(bl[key])
            xs = [r["vus"] for r in rows]
            fig, ax = plt.subplots(figsize=(6, 3.6))
            for i, k in enumerate(("p50", "p95", "p99")):
                ys = [r[k] for r in rows]
                ax.plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=k)
                label_end(ax, xs, ys, k, C[i])
            ax.set(title=f"{SCEN[letter]}: latency percentiles", xlabel="virtual users")
            log_ms(ax)
            fig_legend(fig, ax)
            save(fig, f"lab5-latency-{letter.lower()}.png")

    scale_runs = {n: runs.get(f"scale_{n}", {}).get("scenario_a_read") for n in (1, 2)}
    scale_runs[3] = bl.get("scenario_a_read")
    sc = [(n, d) for n, d in scale_runs.items() if d]
    if len(sc) > 1:
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        for i, (n, data) in enumerate(sc):
            rows = per_stage(data)
            xs = [r["vus"] for r in rows]
            for ax, k in zip(axes, ("rps", "p95")):
                ys = [r[k] for r in rows]
                ax.plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=f"{n} instance(s)")
                label_end(ax, xs, ys, f"{n}x", C[i])
        axes[0].set(title="Throughput", xlabel="virtual users", ylabel="requests / s")
        axes[1].set(title="p95 latency", xlabel="virtual users")
        axes[0].set_ylim(bottom=0)
        log_ms(axes[1])
        fig_legend(fig, axes[0])
        fig.suptitle("Lab 5 - scaling impact, scenario A", fontsize=11, color=INK2)
        save(fig, "lab5-scaling.png")

    if "scenario_a_read" in runs.get("no_cache", {}) and "scenario_a_read" in bl:
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        for i, (label, data) in enumerate((("cache enabled (warm)", bl["scenario_a_read"]),
                                           ("cache disabled", runs["no_cache"]["scenario_a_read"]))):
            rows = per_stage(data)
            xs = [r["vus"] for r in rows]
            for ax, k in zip(axes, ("rps", "p95")):
                ys = [r[k] for r in rows]
                ax.plot(xs, ys, "-o", color=C[i], lw=2, ms=6, label=label)
                label_end(ax, xs, ys, "on" if i == 0 else "off", C[i])
        axes[0].set(title="Throughput", xlabel="virtual users", ylabel="requests / s")
        axes[1].set(title="p95 latency", xlabel="virtual users")
        axes[0].set_ylim(bottom=0)
        log_ms(axes[1])
        fig_legend(fig, axes[0], ncols=2)
        fig.suptitle("Lab 5 - caching impact, scenario A (3 instances)", fontsize=11, color=INK2)
        save(fig, "lab5-cache.png")


def write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("report:", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"lab3", "lab5"}
    if "lab3" in which:
        lab3()
    if "lab5" in which:
        lab5()
