"""
WorkBench pilot: 5 tasks × 3 modes = 15 runs.
Each run uses a per-task MCP server (sandbox isolation).
"""
import json, os, subprocess, sys, time, urllib.request, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
WBENCH = os.path.join(EXP, "_vendor", "WorkBench")
MCP_SERVER = os.path.join(EXP, "mcp_servers", "workbench_server.py")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
DASH = "http://127.0.0.1:7799"

sys.path.insert(0, HERE)
sys.path.insert(0, EXP)
from run_workbench_one import expected_state_for, diff_states  # noqa
from runner.fs_watcher import SwarmFsWatcher  # noqa


def make_mcp_config(task_id: str, state_out: str) -> str:
    cfg = {"mcpServers": {"workbench": {
        "command": "python3", "args": [MCP_SERVER],
        "env": {"WBENCH_REPO": WBENCH, "WBENCH_TASK_ID": task_id,
                "WBENCH_STATE_OUT": state_out, "PYTHONPATH": WBENCH},
    }}}
    p = f"/tmp/wbench_mcp_{task_id}_{uuid.uuid4().hex[:6]}.json"
    with open(p, "w") as f:
        json.dump(cfg, f)
    return p


def build_prompt_single(task: dict) -> str:
    return task["prompt"]


def build_prompt_ow(task: dict) -> tuple[str, dict]:
    """Return (prompt, agents_dict) for OW mode."""
    workers = {
        "workbench_executor": {
            "description": "Specialist that uses workbench MCP tools (calendar/email/analytics/project_management/customer_relationship_manager) to fulfill workplace tasks. Use it for any state-changing operation in the sandbox.",
            "prompt": (
                "You are WORKBENCH_EXECUTOR. You have access to MCP tools prefixed with "
                "calendar_, email_, analytics_, project_management_, customer_relationship_manager_, "
                "company_directory_. Execute the user's request by calling the appropriate tools. "
                "Do all required state changes yourself; do not delegate further. "
                "After completing, briefly confirm what you did. Always end with 'WORKER_DONE'."
            ),
        }
    }
    orch_preamble = (
        "You are an orchestrator. Delegate the workplace task to the workbench_executor "
        "subagent via the Agent tool. Then synthesize its report into the final reply. "
        "Reply with ANSWER=done after the worker finishes.\n\nTASK:\n"
    )
    return orch_preamble + task["prompt"], workers


def build_prompt_sw(task: dict, team_name: str) -> str:
    teammates = [
        ("planner", "You are PLANNER. When the lead DMs you a workplace task, decompose it "
                    "into 2-4 concrete tool calls (using names like calendar_search_events, "
                    "calendar_delete_event, email_search_emails etc.) and DM the ordered list "
                    "back to the lead. You do NOT execute, only plan. Go idle."),
        ("executor", "You are EXECUTOR. When the lead DMs you a list of MCP tool calls to make, "
                     "call them in order using the workbench MCP tools available to you. "
                     "DM the lead a one-line summary when done. Go idle."),
    ]
    teammate_lines = "\n".join(
        f"  - name={n!r}, subagent_type='general-purpose', role_prompt={p!r}"
        for n, p in teammates
    )
    return f"""You are the lead of a swarm. Set up the swarm and coordinate it to solve the task.

REQUIRED setup:
1. Call TeamCreate with team_name="{team_name}" and a one-line description.
2. For EACH teammate listed below, call the Agent tool with team_name="{team_name}",
   the given name, subagent_type='general-purpose', and the role_prompt as the prompt.

TEAMMATES:
{teammate_lines}

Once teammates are spawned, DM the planner with the task; once planner replies with the
plan, DM the executor with the plan. When executor confirms it's done, you MUST:
1. Call TaskStop on planner and executor (or SendMessage shutdown_request to each).
2. IGNORE further inbox notifications. Do not respond to teammates after shutdown.
3. Output ONE final assistant message ending with: ANSWER=done

TASK:
{task["prompt"]}
"""


def parse_stream(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except: pass
    return out


def summarize_stream(events: list) -> dict:
    s = {
        "n_events": len(events), "tool_uses": [], "team_create_calls": [],
        "agent_spawns": [], "send_messages": [], "final_text": None,
    }
    for ev in events:
        t = ev.get("type", "?")
        if t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    name = blk.get("name"); inp = blk.get("input") or {}
                    s["tool_uses"].append({"name": name, "input_keys": list(inp.keys())})
                    if name == "TeamCreate": s["team_create_calls"].append(inp)
                    elif name == "Agent":
                        s["agent_spawns"].append({
                            "name": inp.get("name"),
                            "subagent_type": inp.get("subagent_type"),
                            "team_name": inp.get("team_name"),
                            "prompt_preview": (inp.get("prompt") or "")[:160],
                        })
                    elif name == "SendMessage":
                        s["send_messages"].append({
                            "to": inp.get("to"),
                            "message_preview": str(inp.get("message", ""))[:160],
                        })
        elif t == "result":
            s["final_text"] = ev.get("result")
    return s


def invoke(args: list, timeout: int, early_stop=False, answer_grace=20.0) -> tuple[str, int, bool, float]:
    started = time.time()
    if not early_stop:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return p.stdout, p.returncode, False, time.time() - started
        except subprocess.TimeoutExpired as e:
            so = e.stdout
            if isinstance(so, bytes): so = so.decode("utf-8", "replace")
            return so or "", -2, True, time.time() - started
    # streaming early-stop
    import select, re
    ANS_RE = re.compile(r"^\s*ANSWER\s*=", re.MULTILINE)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    chunks, ans_at = [], None
    deadline = started + timeout
    while True:
        if proc.poll() is not None:
            rest = proc.stdout.read() if proc.stdout else ""
            if rest: chunks.append(rest)
            break
        now = time.time()
        if now > deadline:
            proc.terminate()
            try: proc.wait(timeout=3)
            except: proc.kill()
            return "".join(chunks), -2, True, now - started
        if ans_at and (now - ans_at) >= answer_grace:
            proc.terminate()
            try: proc.wait(timeout=3)
            except: proc.kill()
            break
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            line = proc.stdout.readline()
            if not line: continue
            chunks.append(line)
            try: ev = json.loads(line.strip())
            except: continue
            if ev.get("type") == "assistant":
                for b in (ev.get("message", {}) or {}).get("content", []) or []:
                    if b.get("type") == "text" and ANS_RE.search(b.get("text", "")):
                        ans_at = ans_at or now; break
            elif ev.get("type") == "result" and ANS_RE.search(str(ev.get("result", ""))):
                ans_at = ans_at or now
    return "".join(chunks), proc.returncode if proc.returncode is not None else -2, False, time.time() - started


def run_one(task: dict, mode: str, expected_state: dict) -> dict:
    task_id = task["id"].replace("/", "_")
    state_out = f"/tmp/wbench_state_{task_id}_{uuid.uuid4().hex[:6]}.json"
    cfg = make_mcp_config(task_id, state_out)

    fs_trace_path = None; team_name = None; watcher = None

    if mode == "single":
        prompt = build_prompt_single(task)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                "--mcp-config", cfg, "--output-format", "stream-json", "--verbose", prompt]
        early = False; timeout = 240
    elif mode == "ow":
        prompt, agents = build_prompt_ow(task)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                "--mcp-config", cfg, "--agents", json.dumps(agents),
                "--output-format", "stream-json", "--verbose", prompt]
        early = False; timeout = 300
    elif mode == "sw":
        team_name = f"sw-{uuid.uuid4().hex[:8]}"
        prompt = build_prompt_sw(task, team_name)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                "--mcp-config", cfg, "--output-format", "stream-json", "--verbose", prompt]
        early = True; timeout = 420
        # fs watcher
        fs_trace_path = f"/tmp/wbench_fs_{task_id}_{team_name}.jsonl"
        watcher = SwarmFsWatcher(team_name=team_name, out_path=fs_trace_path, poll_s=0.5)
        watcher.start()
    else:
        raise ValueError(mode)

    started = time.time()
    try:
        stdout, rc, timed_out, elapsed = invoke(args, timeout=timeout, early_stop=early)
    finally:
        if watcher: watcher.stop()
    finished = time.time()

    events = parse_stream(stdout)
    s = summarize_stream(events)

    actual_state = None
    if os.path.exists(state_out):
        try:
            with open(state_out) as f: actual_state = json.load(f)
        except: pass

    diff = diff_states(actual_state or {}, expected_state) if actual_state else {"ok": False, "per_domain": {}}

    fs_trace = []
    if fs_trace_path and os.path.exists(fs_trace_path):
        with open(fs_trace_path) as f:
            for l in f:
                l = l.strip()
                if l:
                    try: fs_trace.append(json.loads(l))
                    except: pass

    return {
        "experiment": EXPERIMENT, "benchmark": "workbench", "task_id": task["id"],
        "mode": mode, "prompt": task["prompt"], "expected_answer": task["expected_answer"],
        "final_text": s["final_text"], "elapsed_s": elapsed, "rc": rc, "timeout": timed_out,
        "n_events": s["n_events"], "tool_uses": s["tool_uses"],
        "agent_spawns": s["agent_spawns"], "send_messages": s["send_messages"],
        "team_create_calls": s["team_create_calls"],
        "verify": {
            "ok": diff["ok"],
            "score": 1.0 if diff["ok"] else 0.0,
            "per_domain": diff.get("per_domain", {}),
            "expected_actions": task["expected_answer"],
            "ground_truth_query": task["metadata"]["query"],
        },
        "raw_stream": events, "fs_trace": fs_trace, "team_name": team_name,
        "started_at": started, "finished_at": finished,
    }


def post(rec: dict):
    body = json.dumps(rec, default=str).encode()
    req = urllib.request.Request(f"{DASH}/api/runs", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ! post failed: {e}"); return None


EXPERIMENT = f"workbench_pilot_{int(time.time())}"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with open(os.path.join(HERE, "tasks", "t1_workbench.jsonl")) as f:
        all_tasks = [json.loads(l) for l in f if l.strip()]

    # take diverse tasks: prefer different domains
    by_domain = {}
    for t in all_tasks:
        by_domain.setdefault(t["metadata"]["domain"], []).append(t)
    picked = []
    for d in ("calendar", "email", "project_management", "customer_relationship_manager", "multi_domain", "analytics"):
        if d in by_domain and by_domain[d]:
            picked.append(by_domain[d][0])
        if len(picked) >= n: break
    if len(picked) < n:
        rest = [t for t in all_tasks if t not in picked][: n - len(picked)]
        picked.extend(rest)
    picked = picked[:n]

    print(f"Pilot: {len(picked)} tasks × 3 modes = {len(picked)*3} runs", flush=True)
    print(f"Experiment: {EXPERIMENT}", flush=True)

    # Pre-compute expected states (single-thread; cheap)
    print("Computing expected states...", flush=True)
    expected_states = {}
    for t in picked:
        expected_states[t["id"]] = expected_state_for(t)

    total = len(picked) * 3
    nrun = 0; t0 = time.time()
    for task in picked:
        for mode in ("single", "ow", "sw"):
            nrun += 1
            print(f"\n[{nrun}/{total}] ({time.time()-t0:.0f}s) {task['id']} [{mode}]", flush=True)
            print(f"  Q: {task['metadata']['query'][:100]}", flush=True)
            try:
                rec = run_one(task, mode, expected_states[task["id"]])
            except Exception as e:
                import traceback; traceback.print_exc()
                continue
            verdict = "PASS" if rec["verify"]["ok"] else "FAIL"
            print(f"  → {verdict} elapsed={rec['elapsed_s']:.0f}s tools={len(rec['tool_uses'])} "
                  f"spawns={len(rec['agent_spawns'])} msgs={len(rec['send_messages'])}", flush=True)
            post(rec)
    print(f"\nDone in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
