"""
Workflow-mode feasibility probe.

Goal: confirm that `claude -p "<solve via dynamic workflow>"` (1) triggers the
Workflow tool and writes a .js script, and (2) the workflow's spawned subagents
can actually call the per-task MCP benchmark tools (mcp__financebench__*, etc).

We do NOT score answers here — only verify orchestration + tool reachability.
Runs each benchmark's first task once in wf mode.
"""
import json, os, subprocess, sys, time, uuid, glob

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, EXP)

from run_full_pilot import (  # reuse 014's exact MCP config builders + task loader
    mcp_config_workbench, mcp_config_financebench, mcp_config_plancraft,
    load_tasks, parse_stream, summarize_stream, _verifier_prompt_for,
)

CLAUDE = os.environ.get("CLAUDE_BIN", "/Users/zny/.local/bin/claude")
PROJECTS = os.path.expanduser("~/.claude/projects")


def session_root_for(cwd: str) -> str:
    # CC maps cwd -> project dir: every '/' and '_' becomes '-'
    slug = cwd.replace("/", "-").replace("_", "-")
    return os.path.join(PROJECTS, slug)


def build_prompt_wf(task: dict) -> str:
    bm = task["benchmark"]
    answer_format = "ANSWER=done" if bm in ("plancraft", "workbench") else "ANSWER=<value>"
    # The verifier criteria are IDENTICAL to 014's owv mode — only the enforcement
    # differs: owv asks the lead (via prompt) to loop; here the WORKFLOW SCRIPT
    # enforces the solve→verify→retry loop deterministically in code.
    verifier_criteria = _verifier_prompt_for(bm)
    return (
        "Solve the following task using a DYNAMIC WORKFLOW. Use the Workflow tool: "
        "write a JavaScript workflow script that orchestrates subagents to do the work.\n\n"
        "IMPORTANT: the task requires MCP tools connected to this session (names start "
        "with `mcp__`). The subagents you spawn inside the workflow MUST call those MCP "
        "tools to actually do the work — discover them via ToolSearch if needed. Do not "
        "answer from prior knowledge.\n\n"
        "=== MANDATORY VERIFY LOOP (must be enforced BY THE SCRIPT) ===\n"
        "Your workflow script MUST implement a solve→verify→retry loop in code (e.g. a "
        "while/for loop over up to 3 rounds):\n"
        "1. SOLVE: spawn a solver agent that uses the MCP tools to complete the task.\n"
        "2. VERIFY: spawn a SEPARATE, independent verifier agent that re-checks the work "
        "by calling the MCP tools ITSELF (it must NOT trust the solver). The verifier "
        "follows exactly these criteria:\n"
        "-----\n" + verifier_criteria + "\n-----\n"
        "3. GATE: parse the verifier's reply. If its first line is 'VERIFY_OK', exit the "
        "loop immediately and return the answer. If 'VERIFY_FAIL', feed the verifier's "
        "feedback back to a solver agent for another attempt, then verify AGAIN.\n"
        "4. HARD STOP after AT MOST 3 rounds: if round 3's verifier still says FAIL, the "
        "loop MUST end anyway and the script MUST return the best/last candidate answer "
        "(do NOT loop further, do NOT keep retrying, do NOT spawn more agents). Cap the "
        "loop at 3 rounds in the control flow (e.g. `for (round = 1; round <= 3; round++)`).\n"
        "The loop and the gate decision MUST live in the script's control flow, not be "
        "left to a single agent's discretion.\n\n"
        "Once the Workflow tool returns its result, do NOT do any further work, do NOT "
        "re-verify, do NOT call more tools — IMMEDIATELY emit ONE final message ending "
        f"with a line that literally starts with `{answer_format[:7]}` ({answer_format}).\n\n"
        "TASK:\n" + task["prompt"]
    )


def run_wf_probe(task: dict) -> dict:
    bm = task["benchmark"]
    task_id = task["id"].replace("/", "_")

    # isolated, predictable cwd so we can locate the session artifact dir
    cwd = f"/private/tmp/wfprobe_{bm}_{uuid.uuid4().hex[:6]}"
    os.makedirs(cwd, exist_ok=True)

    # per-task MCP config (reuse 014 builders)
    state_out = None
    if bm == "workbench":
        state_out = f"/tmp/wbench_state_{task_id}_{uuid.uuid4().hex[:6]}.json"
        cfg = mcp_config_workbench(task_id, state_out)
    elif bm == "financebench":
        cfg = mcp_config_financebench(task_id)
    elif bm == "plancraft":
        state_out = f"/tmp/pc_state_{task_id}_{uuid.uuid4().hex[:6]}.json"
        cfg = mcp_config_plancraft(task, state_out)
    else:
        raise ValueError(bm)

    prompt = build_prompt_wf(task)
    args = [CLAUDE, "--print", "--dangerously-skip-permissions",
            "--mcp-config", cfg, "--output-format", "stream-json", "--verbose", prompt]

    # match owv's timeout budget exactly: owv = single*2 + 60.
    # single defaults: 240s, plancraft 360s.
    base = 360 if bm == "plancraft" else 240
    wf_timeout = base * 2 + 60

    print(f"\n=== {bm} :: {task['id']} ===", flush=True)
    print(f"cwd={cwd}  timeout={wf_timeout}s", flush=True)
    t0 = time.time()
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=wf_timeout, stdin=subprocess.DEVNULL)
        stdout, rc, timed_out = p.stdout, p.returncode, False
    except subprocess.TimeoutExpired as e:
        so = e.stdout
        if isinstance(so, bytes): so = so.decode("utf-8", "replace")
        stdout, rc, timed_out = (so or ""), -2, True
    elapsed = time.time() - t0

    events = parse_stream(stdout)
    s = summarize_stream(events)

    # did the main loop call the Workflow tool?
    used_workflow = any(tu.get("name") == "Workflow" for tu in s["tool_uses"])

    # locate session artifacts
    sroot = session_root_for(cwd)
    js_files = glob.glob(os.path.join(sroot, "*", "workflows", "scripts", "*.js"))

    # inspect the generated script for an actual verify LOOP in control flow
    script_has_loop = False
    script_has_verify = False
    script_text = ""
    for jp in js_files:
        with open(jp) as f:
            script_text = f.read()
        if any(kw in script_text for kw in ("while", "for (", "for(", ".map(", "VOTES", "round")):
            script_has_loop = True
        if "VERIFY" in script_text or "verif" in script_text.lower():
            script_has_verify = True
    wf_agent_dirs = glob.glob(os.path.join(sroot, "*", "subagents", "workflows", "wf_*"))
    wf_agent_jsonl = []
    for d in wf_agent_dirs:
        wf_agent_jsonl += glob.glob(os.path.join(d, "agent-*.jsonl"))

    # THE KEY CHECK: did any workflow subagent actually invoke an mcp__<bm> tool?
    # ALSO: count distinct verifier agents (those that emitted VERIFY_OK/FAIL) to
    # confirm the verify loop actually ran inside the workflow.
    mcp_tool_calls = []
    verifier_verdicts = []  # (agent_file, verdict)
    for jf in wf_agent_jsonl:
        saw_verdict = None
        with open(jf) as f:
            for line in f:
                if "mcp__" in line:
                    try:
                        ev = json.loads(line)
                    except Exception:
                        ev = None
                    if ev:
                        msg = ev.get("message", {}) or {}
                        content = msg.get("content")
                        for blk in (content if isinstance(content, list) else []):
                            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                                nm = blk.get("name") or ""
                                if nm.startswith("mcp__"):
                                    mcp_tool_calls.append({"agent": os.path.basename(jf), "tool": nm})
                if "VERIFY_OK" in line:
                    saw_verdict = "OK"
                elif "VERIFY_FAIL" in line and saw_verdict != "OK":
                    saw_verdict = "FAIL"
        if saw_verdict:
            verifier_verdicts.append({"agent": os.path.basename(jf), "verdict": saw_verdict})

    result = {
        "benchmark": bm, "task_id": task["id"], "elapsed_s": round(elapsed, 1),
        "rc": rc, "timeout": timed_out, "cwd": cwd, "session_root": sroot,
        "final_text": (s["final_text"] or "")[:300],
        "main_used_workflow_tool": used_workflow,
        "n_js_scripts": len(js_files),
        "js_scripts": [os.path.basename(p) for p in js_files],
        "script_has_loop": script_has_loop,
        "script_has_verify": script_has_verify,
        "n_wf_subagents": len(wf_agent_jsonl),
        "n_mcp_tool_calls_by_wf_subagents": len(mcp_tool_calls),
        "n_verifier_verdicts": len(verifier_verdicts),
        "verifier_verdicts": verifier_verdicts,
        "mcp_tool_calls_sample": mcp_tool_calls[:10],
    }
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("mcp_tool_calls_sample",)}, indent=2), flush=True)
    if mcp_tool_calls:
        print("  MCP calls by wf subagents:", flush=True)
        for c in mcp_tool_calls[:10]:
            print(f"    {c['tool']}  ({c['agent']})", flush=True)
    return result


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    bench_files = [
        ("workbench", "t1_workbench.jsonl"),
        ("financebench", "t2_financebench.jsonl"),
        ("plancraft", "t3_plancraft.jsonl"),
    ]
    out = []
    for bm, fn in bench_files:
        if only and bm != only:
            continue
        task = load_tasks(fn, 1)[0]
        out.append(run_wf_probe(task))
    os.makedirs(os.path.join(HERE, "wf_probe_out"), exist_ok=True)
    op = os.path.join(HERE, "wf_probe_out", f"probe_{int(time.time())}.json")
    with open(op, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved -> {op}", flush=True)


if __name__ == "__main__":
    main()
