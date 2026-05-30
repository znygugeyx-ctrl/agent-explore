"""Re-score existing dashboard runs with updated verifiers (no rerun)."""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verifiers import verify

DASH = "http://127.0.0.1:7799"
JSONL = os.path.join(HERE, "dashboard", "data", "runs.jsonl")

# Load all runs
runs = []
with open(JSONL) as f:
    for line in f:
        line = line.strip()
        if line:
            runs.append(json.loads(line))

print(f"loaded {len(runs)} runs")

# Need to load original tasks to get humaneval test code (it's stripped from rec)
import json as _json
tasks_by_id = {}
for fname in ("t1_math.jsonl", "t2_fanoutqa.jsonl", "t3_humanevalplus.jsonl"):
    p = os.path.join(HERE, "tasks", fname)
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    t = _json.loads(line)
                    tasks_by_id[t["id"]] = t

# Re-verify each
for r in runs:
    t = tasks_by_id.get(r["task_id"])
    if not t:
        continue
    new_v = verify(t, r.get("final_text") or "")
    r["verify"] = new_v

# Wipe dashboard's persistent log, then POST fresh
os.remove(JSONL)
open(JSONL, "w").close()
# Restart dashboard - need to do externally; here just POST and rely on
# the user having restarted it. We'll tell uvicorn workers to reload from the
# fresh file by writing it ourselves and then POSTing.
with open(JSONL, "w") as f:
    for r in runs:
        f.write(_json.dumps(r, default=str) + "\n")
print(f"wrote {len(runs)} runs back to {JSONL}")
print("Now restart the dashboard for in-memory state to refresh.")
