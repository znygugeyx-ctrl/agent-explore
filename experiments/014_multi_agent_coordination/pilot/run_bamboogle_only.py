"""Run only bamboogle tasks across all 3 modes."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from pilot.run_pilot import run_one, post  # noqa

with open(os.path.join(HERE, "tasks", "t2_bamboogle.jsonl")) as f:
    tasks = [json.loads(l) for l in f if l.strip()]
print(f"{len(tasks)} bamboogle tasks × 3 modes")

experiment = f"bamboogle_{int(time.time())}"
n = 0; total = len(tasks) * 3; t0 = time.time()
for task in tasks:
    for mode in ("single", "ow", "sw"):
        n += 1
        print(f"\n[{n}/{total}] ({time.time()-t0:.0f}s) {task['id']} [{mode}]", flush=True)
        print(f"  Q: {task['metadata']['question']}", flush=True)
        print(f"  expected: {task['expected_answer']!r}", flush=True)
        try:
            rec = run_one(mode, task, experiment)
        except Exception as e:
            print(f"  ⚠ {e}"); continue
        v = rec["verify"]
        verdict = "PASS" if v.get("ok") else f"FAIL (f1={v.get('f1', 0):.2f})"
        ext = (v.get("extracted") or "")[:60]
        print(f"  → {verdict}  extracted={ext!r}", flush=True)
        print(f"  elapsed={rec['elapsed_s']:.0f}s tools={len(rec['tool_uses'])} msgs={len(rec['send_messages'])}", flush=True)
        post(rec)
print(f"\nDone in {time.time()-t0:.0f}s")
