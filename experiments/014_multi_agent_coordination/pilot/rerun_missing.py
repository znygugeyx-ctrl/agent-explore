"""Re-run the 3 workbench SW tasks that crashed due to race condition."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from run_full_pilot import run_one, post  # noqa
import time

MISSING = [
    ("workbench/calendar/81", "sw"),
    ("workbench/email/35", "sw"),
    ("workbench/analytics/31", "sw"),
]

with open(os.path.join(HERE, "tasks", "t1_workbench.jsonl")) as f:
    all_t = [json.loads(l) for l in f if l.strip()]
by_id = {t["id"]: t for t in all_t}

import run_full_pilot as rfp
# Use same experiment id so they group together in dashboard
prev_exp = None
with open(os.path.join(HERE, "dashboard", "data", "runs.jsonl")) as f:
    for line in f:
        l = line.strip()
        if l:
            r = json.loads(l)
            if 'full_pilot' in (r.get('experiment') or ''):
                prev_exp = r['experiment']
                break
if prev_exp:
    rfp.EXPERIMENT = prev_exp
    print(f"reusing experiment: {prev_exp}")

for tid, mode in MISSING:
    t = by_id.get(tid)
    if not t:
        print(f"task {tid} not found, skip"); continue
    print(f"\n>>> {tid} [{mode}]")
    try:
        rec = rfp.run_one(t, mode)
    except Exception as e:
        import traceback; traceback.print_exc(); continue
    v = rec["verify"]
    verdict = "PASS" if v.get("ok") else "FAIL"
    print(f"   → {verdict} elapsed={rec['elapsed_s']:.0f}s tools={len(rec['tool_uses'])} msgs={len(rec['send_messages'])}")
    rfp.post(rec)
