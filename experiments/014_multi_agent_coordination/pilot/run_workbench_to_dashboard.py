"""
Run a single WorkBench task (single-agent mode) and push the result to the
dashboard so the trace can be inspected like other runs.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP_ROOT = os.path.dirname(HERE)
WBENCH_REPO = os.path.join(EXP_ROOT, "_vendor", "WorkBench")
MCP_SERVER = os.path.join(EXP_ROOT, "mcp_servers", "workbench_server.py")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DASHBOARD = "http://127.0.0.1:7799"

sys.path.insert(0, HERE)  # for importing run_workbench_one helpers
from run_workbench_one import expected_state_for, diff_states  # noqa


def run_one(task: dict, mode: str = "single", timeout: int = 300):
    task_id = task["id"].replace("/", "_")
    state_out = f"/tmp/wbench_state_{task_id}_{uuid.uuid4().hex[:6]}.json"

    mcp_config = {
        "mcpServers": {
            "workbench": {
                "command": "python3",
                "args": [MCP_SERVER],
                "env": {
                    "WBENCH_REPO": WBENCH_REPO,
                    "WBENCH_TASK_ID": task_id,
                    "WBENCH_STATE_OUT": state_out,
                    "PYTHONPATH": WBENCH_REPO,
                },
            }
        }
    }
    cfg_path = f"/tmp/wbench_mcp_{task_id}.json"
    with open(cfg_path, "w") as f:
        json.dump(mcp_config, f)

    args = [
        CLAUDE_BIN,
        "--print",
        "--dangerously-skip-permissions",
        "--mcp-config", cfg_path,
        "--output-format", "stream-json",
        "--verbose",
        task["prompt"],
    ]

    print(f"==> {task['id']} [{mode}]", flush=True)
    started = time.time()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - started
        rc = proc.returncode
        timed_out = False
        stdout = proc.stdout
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - started
        rc = -2
        timed_out = True
        stdout = (e.stdout or "").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")

    print(f"   rc={rc} elapsed={elapsed:.0f}s timeout={timed_out}", flush=True)

    raw_stream = []
    tool_uses = []
    final_text = None
    n_events = 0
    event_types = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line: continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        raw_stream.append(ev)
        n_events += 1
        t = ev.get("type", "?")
        event_types[t] = event_types.get(t, 0) + 1
        if t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    tool_uses.append({
                        "name": blk.get("name"),
                        "input_keys": list((blk.get("input") or {}).keys()),
                    })
        elif t == "result":
            final_text = ev.get("result")

    actual_state = None
    if os.path.exists(state_out):
        with open(state_out) as f:
            actual_state = json.load(f)

    finished = time.time()
    return {
        "started_at": started,
        "finished_at": finished,
        "elapsed_s": elapsed,
        "rc": rc,
        "timeout": timed_out,
        "n_events": n_events,
        "event_types": event_types,
        "tool_uses": tool_uses,
        "final_text": final_text,
        "raw_stream": raw_stream,
        "actual_state": actual_state,
    }


def post(rec: dict):
    body = json.dumps(rec, default=str).encode()
    req = urllib.request.Request(
        f"{DASHBOARD}/api/runs",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    tasks_path = os.path.join(HERE, "tasks", "t1_workbench.jsonl")
    with open(tasks_path) as f:
        tasks = [json.loads(l) for l in f if l.strip()]
    task = next(t for t in tasks if t["metadata"]["domain"] == "calendar")

    print(f"Computing expected state for {task['id']} ...")
    expected = expected_state_for(task)

    res = run_one(task, mode="single", timeout=300)
    diff = diff_states(res["actual_state"] or {}, expected) if res["actual_state"] else {"ok": False, "per_domain": {}}

    print(f"   verdict: {'PASS' if diff['ok'] else 'FAIL'}")

    rec = {
        "experiment": f"workbench_demo_{int(time.time())}",
        "benchmark": "workbench",
        "task_id": task["id"],
        "mode": "single",
        "prompt": task["prompt"],
        "expected_answer": task["expected_answer"],
        "final_text": res["final_text"],
        "elapsed_s": res["elapsed_s"],
        "rc": res["rc"],
        "timeout": res["timeout"],
        "n_events": res["n_events"],
        "tool_uses": res["tool_uses"],
        "agent_spawns": [],
        "send_messages": [],
        "team_create_calls": [],
        "verify": {
            "ok": diff["ok"],
            "score": 1.0 if diff["ok"] else 0.0,
            "per_domain": diff.get("per_domain", {}),
            "expected_actions": task["expected_answer"],
            "ground_truth_query": task["metadata"]["query"],
        },
        "raw_stream": res["raw_stream"],
        "fs_trace": [],
        "team_name": None,
        "started_at": res["started_at"],
        "finished_at": res["finished_at"],
    }
    resp = post(rec)
    print(f"   posted: {resp}")
    print(f"   view:   {DASHBOARD}/run/{resp.get('run_id')}")


if __name__ == "__main__":
    main()
