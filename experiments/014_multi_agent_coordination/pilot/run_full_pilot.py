"""
Full pilot: 3 benchmarks × 5 tasks × 3 modes = 45 runs.
Each task gets a fresh per-task MCP server (sandbox isolation).
Results POSTed to dashboard at http://127.0.0.1:7799.
"""
import json, os, subprocess, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
WBENCH = os.path.join(EXP, "_vendor", "WorkBench")
FB_DATA = os.path.join(EXP, "_vendor", "financebench", "financebench_open_source.jsonl")
WBENCH_MCP = os.path.join(EXP, "mcp_servers", "workbench_server.py")
FB_MCP = os.path.join(EXP, "mcp_servers", "financebench_server.py")
PC_MCP = os.path.join(EXP, "mcp_servers", "plancraft_server.py")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
DASH = "http://127.0.0.1:7799"

sys.path.insert(0, HERE)
sys.path.insert(0, EXP)
from run_workbench_one import expected_state_for, diff_states  # noqa
from verify_financebench import verify as verify_fb  # noqa
from runner.fs_watcher import SwarmFsWatcher  # noqa


# ---------- Per-benchmark MCP config builders ----------

def mcp_config_workbench(task_id: str, state_out: str) -> str:
    cfg = {"mcpServers": {"workbench": {
        "command": "python3", "args": [WBENCH_MCP],
        "env": {"WBENCH_REPO": WBENCH, "WBENCH_TASK_ID": task_id,
                "WBENCH_STATE_OUT": state_out, "PYTHONPATH": WBENCH},
    }}}
    p = f"/tmp/wbench_mcp_{task_id}_{uuid.uuid4().hex[:6]}.json"
    with open(p, "w") as f: json.dump(cfg, f)
    return p


def mcp_config_financebench(task_id: str) -> str:
    cfg = {"mcpServers": {"financebench": {
        "command": "python3", "args": [FB_MCP],
        "env": {"FB_DATA": FB_DATA},
    }}}
    p = f"/tmp/fb_mcp_{task_id}_{uuid.uuid4().hex[:6]}.json"
    with open(p, "w") as f: json.dump(cfg, f)
    return p


def mcp_config_plancraft(task: dict, state_out: str) -> str:
    cfg = {"mcpServers": {"plancraft": {
        "command": "python3", "args": [PC_MCP],
        "env": {"PC_TASK_FILE": task["metadata"]["state_file"],
                "PC_STATE_OUT": state_out},
    }}}
    p = f"/tmp/pc_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(p, "w") as f: json.dump(cfg, f)
    return p


# ---------- Per-mode prompt builders ----------

def build_prompt_single(task: dict) -> str:
    return task["prompt"]


def _ow_workers_for(bm: str) -> dict:
    if bm == "workbench":
        return {"workbench_executor": {
            "description": "ALWAYS delegate workplace/sandbox tasks to this worker. It owns calendar/email/analytics/project/CRM tools and MUST execute the entire task end-to-end including all state-changing operations.",
            "prompt": (
                "You are WORKBENCH_EXECUTOR. You have full access to MCP tools prefixed with "
                "calendar_, email_, analytics_, project_management_, customer_relationship_manager_, "
                "company_directory_.\n\n"
                "Execute the user's request COMPLETELY in this single turn:\n"
                "1. Read the request carefully.\n"
                "2. Use search/read tools to find any IDs you need.\n"
                "3. Make ALL required state-changing tool calls (delete/create/update events, emails, etc.).\n"
                "4. Verify the result with a final search/read.\n"
                "5. Report a one-line summary ending with: WORKER_DONE\n\n"
                "Do NOT defer to anyone. Do not return early asking for guidance. "
                "Finish the whole task yourself."
            ),
        }}
    if bm == "financebench":
        return {"finance_analyst": {
            "description": "ALWAYS delegate financial/SEC-filing questions to this worker. It owns the financebench MCP tools and MUST find the filing, extract data, do all calculations, and return the final answer.",
            "prompt": (
                "You are FINANCE_ANALYST. Tools: mcp__financebench__list_filings/"
                "search_filings/open_filing/search_in_filing/read_page.\n\n"
                "Answer the user's question COMPLETELY in this single turn:\n"
                "1. Use search_filings/open_filing to identify the right document.\n"
                "2. Use search_in_filing/read_page to read all relevant pages.\n"
                "3. Extract the necessary numbers and perform any required calculations yourself.\n"
                "4. Choose your own formulas — the user has not prescribed a method.\n"
                "5. Reply ending with: ANSWER=<value>\n\n"
                "Do NOT defer. Do NOT ask the user for confirmation. Compute and answer."
            ),
        }}
    if bm == "plancraft":
        return {"crafter": {
            "description": "ALWAYS delegate Minecraft crafting puzzles to this worker. It owns the plancraft MCP tools and MUST plan and execute the full crafting recipe until the target item is in the inventory.",
            "prompt": (
                "You are CRAFTER. Tools: mcp__plancraft__get_target/get_inventory/move/smelt/stop.\n\n"
                "Solve the puzzle COMPLETELY in this single turn:\n"
                "1. Call get_target then get_inventory.\n"
                "2. Plan the recipe chain mentally; you may need multiple craft steps.\n"
                "3. Execute moves/smelts. After each, observe the new inventory if needed.\n"
                "4. Once the target item appears in the inventory, call stop(reason='done').\n"
                "5. Reply ending with: ANSWER=done\n\n"
                "Do NOT give up early. Do NOT return asking for help. Try multiple strategies if needed."
            ),
        }}
    return {}


def build_prompt_ow(task: dict) -> tuple[str, dict]:
    bm = task["benchmark"]
    workers = _ow_workers_for(bm)
    names = ", ".join(workers.keys())
    preamble = (
        f"=== STRICT ORCHESTRATOR PROTOCOL ===\n"
        f"You are STRICTLY a router/orchestrator. Available worker subagent: {names}.\n\n"
        f"HARD RULES (violating any of these invalidates the run):\n"
        f"1. You MUST NOT call any benchmark tool yourself. Specifically, do NOT call any "
        f"   tool whose name starts with `mcp__`. If you find yourself wanting to call one, "
        f"   stop and delegate to the worker instead.\n"
        f"2. Your ONLY allowed actions are: (a) Agent (to delegate), (b) emit final ANSWER text.\n"
        f"3. Pass the user's task to the worker VERBATIM. Do NOT summarize, paraphrase, "
        f"   pre-decide a method, or split the task into multiple Agent calls. ONE Agent call.\n"
        f"4. The worker is fully capable; trust its result. After it returns, copy its answer "
        f"   into your final reply: 'ANSWER=...' (or 'ANSWER=done' for action tasks).\n\n"
        f"DO NOT call mcp__ tools. DO NOT do the work yourself. DELEGATE.\n\n"
    )
    return preamble + "TASK:\n" + task["prompt"], workers


def _verifier_prompt_for(bm: str) -> str:
    """Returns a benchmark-specific verifier subagent prompt."""
    if bm == "plancraft":
        return (
            "You are VERIFIER. The lead has just attempted to solve a Minecraft "
            "crafting puzzle. INDEPENDENTLY verify whether the target item is in "
            "the inventory by calling tools yourself — do NOT trust the lead's claim.\n\n"
            "Procedure:\n"
            "1. Call mcp__plancraft__get_target.\n"
            "2. Call mcp__plancraft__get_inventory.\n"
            "3. Check whether that item is present with quantity >= 1 in any slot.\n"
            "4. Reply with first line:\n"
            '     - "VERIFY_OK" if target present.\n'
            '     - "VERIFY_FAIL" otherwise.\n'
            "   Then add 1-2 short sentences explaining what you saw and (on FAIL) "
            "what step is likely missing.\n"
            "Be objective."
        )
    if bm == "financebench":
        return (
            "You are VERIFIER. The lead has just attempted to answer a financial "
            "question by reading SEC filings. INDEPENDENTLY re-check using the same "
            "MCP tools — do NOT trust the lead's stated numbers.\n\n"
            "Procedure:\n"
            "1. Read the lead's claimed answer + which doc/page.\n"
            "2. Call mcp__financebench__open_filing/read_page/search_in_filing to "
            "RE-FETCH the data yourself.\n"
            "3. If the question requires calculation, do the calc YOURSELF from the "
            "raw figures.\n"
            "4. Compare your independently-derived value with the lead's candidate.\n"
            "5. Reply with first line:\n"
            '     - "VERIFY_OK" if values match within reasonable tolerance '
            "(ratio ±0.01, dollar ±0.5%).\n"
            '     - "VERIFY_FAIL" if there is a real numerical discrepancy.\n'
            "   Then 2-3 sentences citing the value you found and which page.\n"
            "Floating-point or rounding differences are NOT failures."
        )
    if bm == "workbench":
        return (
            "You are VERIFIER. The lead has just attempted to fulfill a workplace "
            "request by making MCP tool calls (calendar/email/CRM/etc). "
            "INDEPENDENTLY check whether the sandbox state now reflects what the user asked.\n\n"
            "Procedure:\n"
            "1. Read the user's original request and the lead's claim.\n"
            "2. Use mcp__workbench__*_search_* tools to inspect the actual current state.\n"
            "3. Verify all user-requested changes happened correctly: right items "
            "created/deleted/modified, no collateral changes, full intent honored.\n"
            "4. Reply with first line:\n"
            '     - "VERIFY_OK" if state correctly reflects user intent.\n'
            '     - "VERIFY_FAIL" otherwise.\n'
            "   Then 2-3 sentences naming specific items checked, and (on FAIL) "
            "what specifically is wrong/missing/extra.\n"
            "Be thorough — the user's request may have multiple parts."
        )
    return ""


def build_prompt_owv(task: dict) -> tuple[str, dict]:
    """OW-V: lead solves freely (with or without delegating to worker), then
    MUST spawn `verifier` subagent before emitting ANSWER. Verifier independently
    re-checks via the same MCP tools. Up to 3 verification rounds.
    """
    bm = task["benchmark"]
    answer_format = "ANSWER=done" if bm in ("plancraft", "workbench") else "ANSWER=<value>"
    preamble = (
        "=== MANDATORY VERIFICATION PROTOCOL ===\n"
        "Solve the task using whatever approach you prefer (use MCP tools directly, "
        "or delegate to a subagent). But before emitting your final ANSWER, you MUST "
        "follow the verification protocol below.\n\n"
        "1. SOLVE: do whatever is needed to complete the task.\n"
        "2. VERIFY (mandatory): once you believe you are done, you MUST call the Agent "
        "tool with subagent_type='verifier'. In the verifier's prompt, include:\n"
        "     - the original task / user question\n"
        "     - your candidate answer or what you claim to have done\n"
        "     - key facts/tool calls you relied on\n"
        "   The verifier will INDEPENDENTLY re-check using the same MCP tools.\n"
        "3. READ verifier reply (it arrives as a tool_result):\n"
        '     - First line "VERIFY_OK"   → proceed to step 4.\n'
        '     - First line "VERIFY_FAIL" → read the suggested fix, apply additional '
        "MCP tool calls to address it, then GO BACK to step 2 and spawn verifier AGAIN.\n"
        "     - Up to 3 verification rounds. After 3 rounds, emit ANSWER regardless.\n"
        f"4. FINISH: emit your final reply ending with: {answer_format}\n\n"
        "HARD CONSTRAINT: At least ONE Agent(verifier) call MUST happen before ANSWER. "
        "Skipping verification invalidates the run.\n\n"
    )
    agents_def = {"verifier": {
        "description": (
            "MANDATORY verifier subagent. Use it to independently re-check the answer "
            "before emitting the final ANSWER. Spawn it after every solving attempt."
        ),
        "prompt": _verifier_prompt_for(bm),
    }}
    return preamble + "TASK:\n" + task["prompt"], agents_def


def _sw_teammates_for(bm: str) -> list[dict]:
    if bm == "workbench":
        return [
            {"name": "planner", "subagent_type": "general-purpose",
             "prompt": "You are PLANNER. When the lead DMs you a workplace task, decompose it into 2-4 concrete tool calls (using names like calendar_search_events, email_delete_email etc.) and DM the ordered list back to the lead. Go idle."},
            {"name": "executor", "subagent_type": "general-purpose",
             "prompt": "You are EXECUTOR. When the lead DMs you a list of MCP tool calls, execute them in order using workbench MCP tools and DM a one-line summary back. Go idle."},
        ]
    if bm == "financebench":
        return [
            {"name": "doc_finder", "subagent_type": "general-purpose",
             "prompt": (
                 "You are DOC_FINDER. When the lead DMs you the user's financial question verbatim, "
                 "use mcp__financebench__search_filings/open_filing to identify the right filing(s) "
                 "and DM the lead back the doc_name plus a few candidate page numbers. Do NOT attempt "
                 "to answer the question yourself. Go idle."
             )},
            {"name": "extractor", "subagent_type": "general-purpose",
             "prompt": (
                 "You are EXTRACTOR. When the lead DMs you a doc_name + page hint + the original "
                 "verbatim question, use mcp__financebench__read_page/search_in_filing to read the "
                 "relevant pages, then answer the question yourself by choosing your own formula / "
                 "method (do not assume the user prescribed one). DM the lead back a concise answer "
                 "with the key numbers and your reasoning. Go idle."
             )},
        ]
    if bm == "plancraft":
        return [
            {"name": "planner", "subagent_type": "general-purpose",
             "prompt": "You are PLANNER. When the lead DMs you the target + inventory, plan the crafting steps (recipe sequence). DM the ordered list of (slot_from, slot_to, quantity) actions back to the lead. Go idle."},
            {"name": "executor", "subagent_type": "general-purpose",
             "prompt": "You are EXECUTOR. When the lead DMs you a list of crafting actions, call them via mcp__plancraft__move/smelt, observe inventory after each action, and DM a result summary back. Call mcp__plancraft__stop when target is achieved. Go idle."},
        ]
    return []


def build_prompt_sw(task: dict, team_name: str) -> str:
    bm = task["benchmark"]
    teammates = _sw_teammates_for(bm)
    teammate_lines = "\n".join(
        f"  - name={t['name']!r}, subagent_type='general-purpose', role_prompt={t['prompt']!r}"
        for t in teammates
    )
    teammate_names = ", ".join(repr(t["name"]) for t in teammates)
    return f"""You are the lead of a swarm. Set up the swarm and coordinate it to solve the task.

REQUIRED setup:
1. Call TeamCreate with team_name="{team_name}" and a one-line description.
2. For EACH teammate listed below, call the Agent tool with team_name="{team_name}",
   the given name, subagent_type='general-purpose', and the role_prompt.

TEAMMATES:
{teammate_lines}

After spawn, coordinate: DM teammates as needed. Once you have the answer:
1. Call TaskStop on each teammate ({teammate_names}), or SendMessage shutdown_request.
2. IGNORE further inbox notifications. Do not call further tools.
3. Output ONE final assistant message ending with: ANSWER=<answer>  (or ANSWER=done for action tasks)

TASK:
{task["prompt"]}
"""


# ---------- Stream parsing ----------

def parse_stream(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except: pass
    return out


def summarize_stream(events: list) -> dict:
    s = {"n_events": len(events), "tool_uses": [], "team_create_calls": [],
         "agent_spawns": [], "send_messages": [], "final_text": None,
         "verifier_rounds": []}  # list of {prompt_preview, response, verdict}
    pending_verifier_id = None
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
                            "name": inp.get("name"), "subagent_type": inp.get("subagent_type"),
                            "team_name": inp.get("team_name"),
                            "prompt_preview": (inp.get("prompt") or "")[:160],
                        })
                        if inp.get("subagent_type") == "verifier":
                            s["verifier_rounds"].append({
                                "prompt_preview": (inp.get("prompt") or "")[:300],
                                "response": None,
                                "verdict": None,
                            })
                            pending_verifier_id = blk.get("id")
                    elif name == "SendMessage":
                        s["send_messages"].append({
                            "to": inp.get("to"),
                            "message_preview": str(inp.get("message", ""))[:160],
                        })
        elif t == "user" and pending_verifier_id:
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    if blk.get("tool_use_id") == pending_verifier_id:
                        c = blk.get("content")
                        if isinstance(c, list):
                            text = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                        else:
                            text = c or ""
                        if s["verifier_rounds"]:
                            first_line = (text or "").strip().split("\n")[0]
                            verdict = "OK" if first_line.startswith("VERIFY_OK") else (
                                "FAIL" if first_line.startswith("VERIFY_FAIL") else "?"
                            )
                            s["verifier_rounds"][-1]["response"] = (text or "")[:600]
                            s["verifier_rounds"][-1]["verdict"] = verdict
                        pending_verifier_id = None
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
    import select, re
    ANS_RE = re.compile(r"^\s*ANSWER\s*=", re.MULTILINE)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    chunks, ans_at = [], None
    deadline = started + timeout
    while True:
        if proc.poll() is not None:
            rest = proc.stdout.read() if proc.stdout else ""
            if rest: chunks.append(rest); break
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


# ---------- Per-benchmark verify ----------

def verify_workbench(task: dict, state_out: str) -> dict:
    if not os.path.exists(state_out):
        return {"ok": False, "score": 0.0, "reason": "no state dumped"}
    with open(state_out) as f:
        actual = json.load(f)
    expected = expected_state_for(task)
    diff = diff_states(actual, expected)
    return {
        "ok": diff["ok"], "score": 1.0 if diff["ok"] else 0.0,
        "per_domain": diff.get("per_domain", {}),
        "expected_actions": task["expected_answer"],
        "ground_truth_query": task["metadata"]["query"],
    }


def verify_financebench_run(task: dict, final_text: str) -> dict:
    return verify_fb(final_text or "", task["expected_answer"], question=task["metadata"]["question"])


def verify_plancraft(task: dict, state_out: str) -> dict:
    if not os.path.exists(state_out):
        return {"ok": False, "score": 0.0, "reason": "no state dumped"}
    with open(state_out) as f:
        state = json.load(f)
    return {
        "ok": state.get("has_target", False),
        "score": 1.0 if state.get("has_target") else 0.0,
        "steps_taken": state.get("steps_taken"),
        "max_steps": state.get("max_steps"),
        "stopped": state.get("stopped"),
        "stop_reason": state.get("stop_reason"),
        "target": state.get("target"),
        "optimal_path_length": task["metadata"].get("optimal_path_length"),
    }


# ---------- Run one task ----------

def run_one(task: dict, mode: str) -> dict:
    bm = task["benchmark"]
    task_id = task["id"].replace("/", "_")
    state_out = None
    extra_args = []
    timeout_default = 240
    early = False

    # MCP config per benchmark
    if bm == "workbench":
        state_out = f"/tmp/wbench_state_{task_id}_{uuid.uuid4().hex[:6]}.json"
        cfg_path = mcp_config_workbench(task_id, state_out)
        extra_args = ["--mcp-config", cfg_path]
    elif bm == "financebench":
        cfg_path = mcp_config_financebench(task_id)
        extra_args = ["--mcp-config", cfg_path]
    elif bm == "plancraft":
        state_out = f"/tmp/pc_state_{task_id}_{uuid.uuid4().hex[:6]}.json"
        cfg_path = mcp_config_plancraft(task, state_out)
        extra_args = ["--mcp-config", cfg_path]
        timeout_default = 360  # plancraft can be slow
    else:
        raise ValueError(bm)

    fs_trace_path = None; team_name = None; watcher = None

    # Mode-specific prompt + args
    if mode == "single":
        prompt = build_prompt_single(task)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                *extra_args, "--output-format", "stream-json", "--verbose", prompt]
        timeout = timeout_default
    elif mode == "ow":
        prompt, agents = build_prompt_ow(task)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                *extra_args, "--agents", json.dumps(agents),
                "--output-format", "stream-json", "--verbose", prompt]
        timeout = timeout_default + 60
    elif mode == "owv":
        prompt, agents = build_prompt_owv(task)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                *extra_args, "--agents", json.dumps(agents),
                "--output-format", "stream-json", "--verbose", prompt]
        # OW-V is solve + verify (+ optional fix loop). Give 2× single budget.
        timeout = timeout_default * 2 + 60
    elif mode == "sw":
        team_name = f"sw-{uuid.uuid4().hex[:8]}"
        prompt = build_prompt_sw(task, team_name)
        args = [CLAUDE, "--print", "--dangerously-skip-permissions",
                *extra_args, "--output-format", "stream-json", "--verbose", prompt]
        timeout = timeout_default + 180
        early = True
        fs_trace_path = f"/tmp/sw_fs_{task_id}_{team_name}.jsonl"
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

    if bm == "workbench":
        v = verify_workbench(task, state_out)
    elif bm == "financebench":
        v = verify_financebench_run(task, s["final_text"])
    elif bm == "plancraft":
        v = verify_plancraft(task, state_out)

    fs_trace = []
    if fs_trace_path and os.path.exists(fs_trace_path):
        with open(fs_trace_path) as f:
            for l in f:
                l = l.strip()
                if l:
                    try: fs_trace.append(json.loads(l))
                    except: pass

    # Detect orchestrator protocol violations: in OW/SW mode, the LEAD should
    # not be calling benchmark MCP tools directly. Count how many it did.
    lead_mcp_calls = 0
    if mode in ("ow", "sw"):
        for tu in s["tool_uses"]:
            tn = tu.get("name") or ""
            if tn.startswith("mcp__") and bm in tn:
                lead_mcp_calls += 1
    v["lead_violated_protocol"] = lead_mcp_calls > 0
    v["lead_mcp_calls"] = lead_mcp_calls

    return {
        "experiment": EXPERIMENT, "benchmark": bm, "task_id": task["id"], "mode": mode,
        "prompt": task["prompt"], "expected_answer": task["expected_answer"],
        "final_text": s["final_text"], "elapsed_s": elapsed, "rc": rc, "timeout": timed_out,
        "n_events": s["n_events"], "tool_uses": s["tool_uses"],
        "agent_spawns": s["agent_spawns"], "send_messages": s["send_messages"],
        "team_create_calls": s["team_create_calls"],
        "verifier_rounds": s.get("verifier_rounds", []),
        "verify": v,
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


EXPERIMENT = f"full_pilot_{int(time.time())}"


def load_tasks(filename: str, n: int) -> list:
    p = os.path.join(HERE, "tasks", filename)
    with open(p) as f:
        all_t = [json.loads(l) for l in f if l.strip()]
    return all_t[:n]


def main():
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    bench_files = [
        ("workbench", "t1_workbench.jsonl"),
        ("financebench", "t2_financebench.jsonl"),
        ("plancraft", "t3_plancraft.jsonl"),
    ]
    all_tasks = []
    for bm, fn in bench_files:
        ts = load_tasks(fn, n_per)
        print(f"Loaded {len(ts)} {bm} tasks")
        all_tasks.extend(ts)

    # Modes via env: PILOT_MODES=single,sw to skip OW (which currently degenerates
    # — lead bypasses the worker and calls MCP tools itself).
    modes = tuple((os.environ.get("PILOT_MODES") or "single,sw").split(","))
    total = len(all_tasks) * len(modes)
    print(f"\nTotal: {len(all_tasks)} tasks × {len(modes)} modes = {total} runs")
    print(f"Experiment: {EXPERIMENT}\n")

    n_run = 0; t0 = time.time()
    for task in all_tasks:
        for mode in modes:
            n_run += 1
            print(f"[{n_run}/{total}] ({time.time()-t0:.0f}s) {task['benchmark']:13s} {task['id']:48s} [{mode}]", flush=True)
            try:
                rec = run_one(task, mode)
            except Exception as e:
                import traceback; traceback.print_exc(); continue
            v = rec["verify"]
            verdict = "PASS" if v.get("ok") else "FAIL"
            to = " TIMEOUT" if rec["timeout"] else ""
            print(f"   → {verdict}{to} elapsed={rec['elapsed_s']:.0f}s tools={len(rec['tool_uses'])} "
                  f"spawns={len(rec['agent_spawns'])} msgs={len(rec['send_messages'])}", flush=True)
            post(rec)
    print(f"\nDone in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
