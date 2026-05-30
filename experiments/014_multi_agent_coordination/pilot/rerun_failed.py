"""Rerun the runs flagged as network failures or true timeouts.

Replaces (benchmark, task_id, mode) tuples in dashboard/data/runs.jsonl
with fresh runs. Same experiment_id so they group together.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import run_full_pilot as rfp  # noqa
from run_full_pilot import run_one, post  # noqa

EXP_PREFIX = "full_pilot_1779637990"
JSONL = os.path.join(HERE, "dashboard", "data", "runs.jsonl")


def load_runs():
    out = []
    with open(JSONL) as f:
        for l in f:
            l = l.strip()
            if l: out.append(json.loads(l))
    return out


def write_runs(runs):
    with open(JSONL, "w") as f:
        for r in runs:
            f.write(json.dumps(r, default=str) + "\n")


def main():
    with open(os.path.join(HERE, "_to_rerun.json")) as f:
        targets = json.load(f)
    print(f"will rerun {len(targets)} runs")

    # Find experiment id from existing runs to reuse
    existing = load_runs()
    exp_ids = set(r.get("experiment") for r in existing if r.get("experiment", "").startswith(EXP_PREFIX))
    if exp_ids:
        rfp.EXPERIMENT = list(exp_ids)[0]
        print(f"reusing experiment: {rfp.EXPERIMENT}")

    # Load tasks for each benchmark
    tasks = {}
    for fname, key in [("t1_workbench.jsonl", "workbench"),
                       ("t2_financebench.jsonl", "financebench"),
                       ("t3_plancraft.jsonl", "plancraft")]:
        p = os.path.join(HERE, "tasks", fname)
        with open(p) as f:
            for l in f:
                l = l.strip()
                if l:
                    t = json.loads(l)
                    tasks[(t["benchmark"], t["id"])] = t

    # Build set of keys to remove from jsonl
    rerun_keys = {(t["benchmark"], t["task_id"], t["mode"]) for t in targets}

    # Remove failed runs from runs.jsonl
    kept = [r for r in existing if (r["benchmark"], r["task_id"], r["mode"]) not in rerun_keys
            or not r.get("experiment", "").startswith(EXP_PREFIX)]
    print(f"removed {len(existing) - len(kept)} stale runs from jsonl, kept {len(kept)}")
    write_runs(kept)

    # Restart dashboard so it reloads runs.jsonl
    pid_file = os.path.join(HERE, "_dashboard.pid")
    if os.path.exists(pid_file):
        with open(pid_file) as f:
            pid = int(f.read().strip())
        try: os.kill(pid, 9)
        except Exception: pass
    import subprocess
    p = subprocess.Popen(
        ["python3", "-m", "uvicorn", "dashboard.server:app",
         "--host", "127.0.0.1", "--port", "7799", "--log-level", "warning"],
        stdout=open(os.path.join(HERE, "_dashboard.log"), "w"),
        stderr=subprocess.STDOUT, cwd=HERE)
    with open(pid_file, "w") as f:
        f.write(str(p.pid))
    time.sleep(2)
    print(f"dashboard restarted pid={p.pid}")

    # Now re-run each
    n = 0
    t0 = time.time()
    for entry in targets:
        n += 1
        bm = entry["benchmark"]
        tid = entry["task_id"]
        mode = entry["mode"]
        task = tasks.get((bm, tid))
        if not task:
            print(f"[{n}/{len(targets)}] task {bm}/{tid} NOT FOUND, skip")
            continue
        print(f"[{n}/{len(targets)}] ({time.time()-t0:.0f}s) {bm:13s} {tid:50s} {mode}", flush=True)
        try:
            rec = run_one(task, mode)
        except Exception as e:
            import traceback; traceback.print_exc(); continue
        v = rec["verify"]
        verdict = "PASS" if v.get("ok") else "FAIL"
        to = " TIMEOUT" if rec["timeout"] else ""
        print(f"   → {verdict}{to} elapsed={rec['elapsed_s']:.0f}s tools={len(rec['tool_uses'])}",
              flush=True)
        post(rec)
    print(f"\nDone in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
