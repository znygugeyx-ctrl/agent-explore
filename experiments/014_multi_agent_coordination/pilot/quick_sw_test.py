"""Single SW math run to verify fs watcher + shutdown work."""
import os, sys, json, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from runner import run_sw  # noqa
from pilot.verifiers import verify  # noqa
from pilot.run_pilot import make_teammates_for_sw, parse_jsonl_stream, post  # noqa

with open(os.path.join(HERE, "tasks", "t1_math.jsonl")) as f:
    task = json.loads(f.readline())

print("Task:", task["id"])
log_dir = os.path.join(HERE, "_runlogs", "quick_sw_test")
teammates = make_teammates_for_sw(task)
t0 = time.time()
r = run_sw(task["prompt"], teammates=teammates, log_dir=log_dir, tag="quick", timeout=300)
elapsed = time.time() - t0
print(f"Done in {elapsed:.1f}s, rc={r.rc}, timeout={r.timeout}")
print(f"  team_name={r.team_name}")
print(f"  spawns={len(r.agent_spawns)}, send_messages={len(r.send_messages)}")
print(f"  fs_trace_path={r.fs_trace_path}")
fs = parse_jsonl_stream(r.fs_trace_path or "")
print(f"  fs events captured: {len(fs)}")
kinds = {}
for e in fs:
    k = e.get("kind", "?")
    kinds[k] = kinds.get(k, 0) + 1
print(f"  fs kinds: {kinds}")
inbox_changes = [e for e in fs if e.get("path", "").find("inboxes") >= 0]
print(f"  inbox changes: {len(inbox_changes)}")
for ic in inbox_changes[:5]:
    print(f"    - {ic.get('path')} kind={ic.get('kind')} content_len={len(ic.get('content','') or '')}")
print(f"  final_text: {(r.final_text or '')[:120]!r}")

raw = parse_jsonl_stream(r.raw_stdout_path or "")
v = verify(task, r.final_text or "")
rec = {
    "experiment": "quick_sw_test",
    "benchmark": task["benchmark"], "task_id": task["id"], "mode": "sw",
    "prompt": task["prompt"], "expected_answer": task["expected_answer"],
    "final_text": r.final_text, "elapsed_s": r.elapsed_s, "rc": r.rc, "timeout": r.timeout,
    "n_events": r.n_events, "tool_uses": r.tool_uses,
    "agent_spawns": r.agent_spawns, "send_messages": r.send_messages,
    "team_create_calls": r.team_create_calls, "verify": v,
    "raw_stream": raw, "fs_trace": fs, "team_name": r.team_name,
    "started_at": t0, "finished_at": time.time(),
}
post(rec)
print("Posted to dashboard.")
