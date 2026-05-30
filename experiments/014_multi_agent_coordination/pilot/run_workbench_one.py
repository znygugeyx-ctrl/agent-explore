"""
End-to-end smoke test: run ONE Workbench task through CC `--print` with the
WorkBench MCP server attached, then verify final sandbox state vs expected.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP_ROOT = os.path.dirname(HERE)
WBENCH_REPO = os.path.join(EXP_ROOT, "_vendor", "WorkBench")
MCP_SERVER = os.path.join(EXP_ROOT, "mcp_servers", "workbench_server.py")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

sys.path.insert(0, EXP_ROOT)
sys.path.insert(0, WBENCH_REPO)


def expected_state_for(task: dict) -> dict:
    """Apply expected_actions to a fresh sandbox; return resulting state dict."""
    cwd = os.getcwd()
    try:
        os.chdir(WBENCH_REPO)
        # need fresh import each call
        import importlib
        from src.tools import calendar, email as email_mod, analytics, project_management, customer_relationship_manager as crm
        for m in (calendar, email_mod, analytics, project_management, crm):
            importlib.reload(m)
        from src.evals import utils as eu
        importlib.reload(eu)
        # function returns (success, cal, email, analytics, pm, crm) — pre-reset states
        success, cal, eml, ana, pm, crm_state = eu.execute_actions_and_reset_state(task["expected_answer"])
        out = {
            "calendar": cal.to_dict(orient="records"),
            "email": eml.to_dict(orient="records") if eml is not None else None,
            "project_management": pm.to_dict(orient="records") if pm is not None else None,
            "customer_relationship_manager": crm_state.to_dict(orient="records") if crm_state is not None else None,
        }
        return {k: v for k, v in out.items() if v is not None}
    finally:
        os.chdir(cwd)


def run_one(task: dict, mode: str = "single", timeout: int = 300):
    task_id = task["id"].replace("/", "_")
    state_out = f"/tmp/wbench_state_{task_id}_{uuid.uuid4().hex[:6]}.json"

    # MCP config file
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

    print(f"==> running task={task['id']} mode={mode}", flush=True)
    print(f"    expected_actions={task['expected_answer']}", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        print(f"  TIMEOUT after {elapsed:.0f}s")
        return None
    print(f"    done rc={proc.returncode} elapsed={elapsed:.0f}s", flush=True)

    # Parse stream and extract tool calls
    tool_uses = []
    final_text = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line: continue
        try:
            ev = json.loads(line)
        except: continue
        if ev.get("type") == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    tool_uses.append({"name": blk.get("name"), "input": blk.get("input")})
        elif ev.get("type") == "result":
            final_text = ev.get("result")

    print(f"    final_text: {(final_text or '')[:120]!r}")
    print(f"    {len(tool_uses)} tool calls:", flush=True)
    for tu in tool_uses[:10]:
        if (tu.get("name") or "").startswith(("calendar", "email", "analytics", "project_", "customer_", "company_")):
            print(f"      - {tu['name']}({tu['input']})")

    # Read final sandbox state
    if not os.path.exists(state_out):
        print(f"    ⚠ state dump missing at {state_out}")
        return None
    with open(state_out) as f:
        actual_state = json.load(f)
    return {
        "actual_state": actual_state,
        "tool_uses": tool_uses,
        "final_text": final_text,
        "elapsed": elapsed,
        "rc": proc.returncode,
        "raw_stdout_path": None,
    }


def diff_states(actual: dict, expected: dict) -> dict:
    """Return per-domain diff. ok=True iff every changed-row matches."""
    summary = {}
    for dom in expected:
        a = actual.get(dom, [])
        e = expected.get(dom, [])
        a_set = {json.dumps(r, sort_keys=True, default=str) for r in a}
        e_set = {json.dumps(r, sort_keys=True, default=str) for r in e}
        match = a_set == e_set
        summary[dom] = {
            "ok": match,
            "actual_n": len(a),
            "expected_n": len(e),
            "missing_from_actual": list(e_set - a_set)[:3],
            "extra_in_actual": list(a_set - e_set)[:3],
        }
    overall_ok = all(s["ok"] for s in summary.values())
    return {"ok": overall_ok, "per_domain": summary}


def main():
    with open(os.path.join(HERE, "tasks", "t1_workbench.jsonl")) as f:
        tasks = [json.loads(l) for l in f if l.strip()]
    # pick first calendar task
    task = next(t for t in tasks if t["metadata"]["domain"] == "calendar")
    print(f"\n=== Computing expected state ===")
    expected = expected_state_for(task)
    print(f"  expected calendar rows: {len(expected.get('calendar', []))}")

    print(f"\n=== Running CC with WorkBench MCP ===")
    result = run_one(task)
    if not result:
        print("RUN FAILED"); return

    print(f"\n=== Diff ===")
    diff = diff_states(result["actual_state"], expected)
    print(json.dumps(diff, indent=2)[:800])
    print(f"\nVERDICT: {'PASS' if diff['ok'] else 'FAIL'}")


if __name__ == "__main__":
    main()
