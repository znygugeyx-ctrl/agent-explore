"""Re-run only the fanoutqa tasks across all 3 modes."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from pilot.run_pilot import run_one, post  # noqa

with open(os.path.join(HERE, "tasks", "t2_fanoutqa.jsonl")) as f:
    tasks = [json.loads(l) for l in f if l.strip()]
print(f"{len(tasks)} fanoutqa tasks × 3 modes")

experiment = f"fanout_rerun_{int(time.time())}"
n = 0; total = len(tasks)*3; t0 = time.time()
for task in tasks:
    for mode in ("single", "ow", "sw"):
        n += 1
        print(f"[{n}/{total}] ({time.time()-t0:.0f}s) {task['id']} [{mode}]", flush=True)
        try:
            rec = run_one(mode, task, experiment)
        except Exception as e:
            print(f"  ⚠ {e}"); continue
        v = rec["verify"]
        verdict = "PASS" if v.get("ok") else f"FAIL ({v.get('score',0):.2f})"
        j = (v.get("judge") or {}).get("label")
        print(f"  → {verdict} [judge={j}] elapsed={rec['elapsed_s']:.0f}s msgs={len(rec['send_messages'])}", flush=True)
        post(rec)
print(f"done in {time.time()-t0:.0f}s")
