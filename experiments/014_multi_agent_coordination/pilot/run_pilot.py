"""
Pilot runner: 6 tasks (2 per benchmark) × 3 modes = 18 runs.

For each completed run, POST a record to the dashboard at http://127.0.0.1:7799.
Also write run records locally.

Usage:
    python3 -m uvicorn dashboard.server:app --host 127.0.0.1 --port 7799 &
    python3 run_pilot.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # so `runner` is importable

from runner import run_single, run_ow, run_sw  # noqa: E402
from pilot.verifiers import verify  # noqa: E402

DASHBOARD = "http://127.0.0.1:7799"
LOG_DIR = os.path.join(HERE, "_runlogs")
os.makedirs(LOG_DIR, exist_ok=True)


def load_tasks():
    tasks = []
    for fname in ("t1_math.jsonl", "t2_bamboogle.jsonl", "t3_humanevalplus.jsonl"):
        p = os.path.join(HERE, "tasks", fname)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    tasks.append(json.loads(line))
    return tasks


def parse_jsonl_stream(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def post(rec: dict):
    body = json.dumps(rec, default=str).encode()
    req = urllib.request.Request(
        f"{DASHBOARD}/api/runs",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"  ⚠ dashboard POST failed: {e}", flush=True)
        return None


def make_workers_for_ow(task):
    bm = task["benchmark"]
    if bm == "math500":
        return {
            "math_solver": {
                "description": "Specialist for solving math competition problems with detailed reasoning.",
                "prompt": (
                    "You are MATH_SOLVER. Solve the given math problem step by step. "
                    "On the final line, write exactly: ANSWER=<your answer in LaTeX>. "
                    "Be precise; the answer is checked by exact match after normalization."
                ),
            }
        }
    if bm == "bamboogle":
        return {
            "researcher": {
                "description": "Multi-hop fact lookup specialist. Use for any question requiring 2-3 chained web lookups.",
                "prompt": (
                    "You are RESEARCHER. You have WebSearch and WebFetch available. "
                    "Decompose the question into sub-queries, perform the lookups in order "
                    "(use the result of an earlier lookup as input to the next), and answer concisely. "
                    "Always end your reply with: ANSWER=<short answer — just the key fact>"
                ),
            }
        }
    if bm == "humanevalplus":
        return {
            "coder": {
                "description": "Specialist for implementing Python functions from a docstring.",
                "prompt": (
                    "You are CODER. Implement the requested Python function. "
                    "Reply with the complete function definition only, including the def line."
                ),
            }
        }
    return {}


def make_teammates_for_sw(task):
    bm = task["benchmark"]
    if bm == "math500":
        return [
            {
                "name": "solver",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are SOLVER. When the lead DMs you a math problem, work through it "
                    "step by step and DM the lead with: ANSWER=<latex>. Then go idle."
                ),
            },
            {
                "name": "checker",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are CHECKER. When the lead DMs you a problem and a candidate answer, "
                    "verify it by independent reasoning and DM the lead with: VERDICT=correct or "
                    "VERDICT=wrong, plus your suggested ANSWER. Then go idle."
                ),
            },
        ]
    if bm == "bamboogle":
        return [
            {
                "name": "decomposer",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are DECOMPOSER. When the lead DMs you a multi-hop question, "
                    "split it into 2-3 atomic sub-queries (each answerable with one Wikipedia lookup) "
                    "and DM the ordered list back to the lead. Go idle."
                ),
            },
            {
                "name": "lookup",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are LOOKUP. You have WebSearch and WebFetch. "
                    "When the lead DMs you a sub-query, look it up and DM back a one-line factual answer. "
                    "Go idle between turns. The lead may DM you several queries in sequence."
                ),
            },
        ]
    if bm == "humanevalplus":
        return [
            {
                "name": "coder",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are CODER. When the lead DMs you a function spec, write a Python "
                    "implementation and DM it back to the lead. If the lead later DMs you "
                    "with feedback, revise and DM the new version. Go idle between turns."
                ),
            },
            {
                "name": "tester",
                "subagent_type": "general-purpose",
                "prompt": (
                    "You are TESTER. When the lead DMs you a Python implementation and "
                    "its docstring, devise edge-case test inputs (do not execute them), "
                    "predict expected outputs, and DM the lead with any concerns. Go idle."
                ),
            },
        ]
    return []


def run_one(mode: str, task: dict, experiment: str) -> dict:
    log_dir = os.path.join(LOG_DIR, experiment, mode)
    os.makedirs(log_dir, exist_ok=True)
    started = time.time()
    if mode == "single":
        r = run_single(task["prompt"], log_dir=log_dir, tag=f"{task['benchmark']}_{task['id'].replace('/','_')}", timeout=240)
    elif mode == "ow":
        workers = make_workers_for_ow(task)
        r = run_ow(task["prompt"], workers=workers, log_dir=log_dir, tag=f"{task['benchmark']}_{task['id'].replace('/','_')}", timeout=300)
    elif mode == "sw":
        teammates = make_teammates_for_sw(task)
        r = run_sw(task["prompt"], teammates=teammates, log_dir=log_dir, tag=f"{task['benchmark']}_{task['id'].replace('/','_')}", timeout=420)
    else:
        raise ValueError(mode)
    finished = time.time()

    raw_stream = parse_jsonl_stream(r.raw_stdout_path)
    v = verify(task, r.final_text or "")
    fs_trace = parse_jsonl_stream(getattr(r, "fs_trace_path", None) or "")

    rec = {
        "experiment": experiment,
        "benchmark": task["benchmark"],
        "task_id": task["id"],
        "mode": mode,
        "prompt": task["prompt"],
        "expected_answer": task["expected_answer"],
        "final_text": r.final_text,
        "elapsed_s": r.elapsed_s,
        "rc": r.rc,
        "timeout": r.timeout,
        "n_events": r.n_events,
        "tool_uses": r.tool_uses,
        "agent_spawns": r.agent_spawns,
        "send_messages": r.send_messages,
        "team_create_calls": r.team_create_calls,
        "verify": v,
        "raw_stream": raw_stream,
        "fs_trace": fs_trace,
        "team_name": getattr(r, "team_name", None),
        "started_at": started,
        "finished_at": finished,
    }
    return rec


def main():
    experiment = f"pilot_{int(time.time())}"
    tasks = load_tasks()
    if not tasks:
        print("No tasks; run sample_tasks.py first.")
        return
    print(f"Pilot: {len(tasks)} tasks × 3 modes = {len(tasks)*3} runs", flush=True)
    print(f"Experiment ID: {experiment}", flush=True)

    modes = ["single", "ow", "sw"]
    total = len(tasks) * len(modes)
    n = 0
    t0 = time.time()
    for task in tasks:
        for mode in modes:
            n += 1
            elapsed = time.time() - t0
            print(f"\n[{n}/{total}] ({elapsed:.0f}s elapsed) {task['benchmark']}/{task['id']} [{mode}]", flush=True)
            try:
                rec = run_one(mode, task, experiment)
            except Exception as e:
                print(f"  ⚠ run failed: {e}", flush=True)
                continue
            v = rec["verify"]
            verdict = "PASS" if v.get("ok") else f"FAIL ({v.get('score',0):.2f})"
            print(f"  → {verdict} elapsed={rec['elapsed_s']:.1f}s tools={len(rec['tool_uses'])} spawns={len(rec['agent_spawns'])} msgs={len(rec['send_messages'])}", flush=True)
            post(rec)
    print(f"\nDone in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
