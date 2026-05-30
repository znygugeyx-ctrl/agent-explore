"""End-to-end smoke test for one PlanCraft task."""
import json, os, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
MCP_SERVER = os.path.join(EXP, "mcp_servers", "plancraft_server.py")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")


def run_one(task: dict, timeout: int = 360) -> dict:
    state_out = f"/tmp/plancraft_state_{uuid.uuid4().hex[:8]}.json"
    cfg = {"mcpServers": {"plancraft": {
        "command": "python3", "args": [MCP_SERVER],
        "env": {
            "PC_TASK_FILE": task["metadata"]["state_file"],
            "PC_STATE_OUT": state_out,
        },
    }}}
    cfg_path = f"/tmp/pc_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(cfg_path, "w") as f: json.dump(cfg, f)

    args = [CLAUDE, "--print", "--dangerously-skip-permissions",
            "--mcp-config", cfg_path, "--output-format", "stream-json", "--verbose",
            task["prompt"]]
    print(f"==> {task['id']}", flush=True)
    print(f"   target={task['expected_answer']} optimal_steps={task['metadata']['optimal_path_length']}", flush=True)
    t0 = time.time()
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        print(f"   TIMEOUT ({timeout}s)")
        return None
    elapsed = time.time() - t0
    print(f"   rc={p.returncode} elapsed={elapsed:.0f}s", flush=True)

    tool_uses = []; final_text = None
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line: continue
        try: ev = json.loads(line)
        except: continue
        if ev.get("type") == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    tool_uses.append({"name": blk.get("name"), "input": blk.get("input")})
        elif ev.get("type") == "result":
            final_text = ev.get("result")
    print(f"   tool calls: {len(tool_uses)}")
    for tu in tool_uses[:12]:
        if "plancraft" in (tu.get("name") or ""):
            print(f"     - {tu['name']}({tu['input']})")
    print(f"   final_text: {(final_text or '')[:200]!r}")

    final_state = None
    if os.path.exists(state_out):
        with open(state_out) as f:
            final_state = json.load(f)
    return {"final_text": final_text, "tool_uses": tool_uses, "elapsed": elapsed, "state": final_state}


def main():
    with open(os.path.join(HERE, "tasks", "t3_plancraft.jsonl")) as f:
        tasks = [json.loads(l) for l in f if l.strip()]
    # pick the simplest task (1-step) first to verify infra
    task = next(t for t in tasks if t["metadata"]["optimal_path_length"] == 1)
    res = run_one(task)
    if not res:
        print("FAILED to run"); return
    state = res.get("state")
    if not state:
        print("NO STATE DUMPED"); return
    print(f"\n=== Final state ===")
    print(f"  has_target: {state['has_target']}")
    print(f"  steps_taken: {state['steps_taken']}")
    print(f"  stopped: {state['stopped']} reason={state.get('stop_reason')}")
    print(f"\nVERDICT: {'PASS' if state['has_target'] else 'FAIL'}")


if __name__ == "__main__":
    main()
