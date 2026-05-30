"""End-to-end smoke test: run ONE FinanceBench task."""
import json, os, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
FB_DATA = os.path.join(EXP, "_vendor", "financebench", "financebench_open_source.jsonl")
MCP_SERVER = os.path.join(EXP, "mcp_servers", "financebench_server.py")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")

sys.path.insert(0, HERE)
from verify_financebench import verify  # noqa


def run_one(task: dict, timeout: int = 240) -> dict:
    cfg = {"mcpServers": {"financebench": {
        "command": "python3", "args": [MCP_SERVER],
        "env": {"FB_DATA": FB_DATA},
    }}}
    cfg_path = f"/tmp/fb_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(cfg_path, "w") as f: json.dump(cfg, f)

    args = [CLAUDE, "--print", "--dangerously-skip-permissions",
            "--mcp-config", cfg_path, "--output-format", "stream-json", "--verbose",
            task["prompt"]]
    print(f"==> {task['id']}", flush=True)
    print(f"   doc={task['metadata']['doc_name']}", flush=True)
    print(f"   expected={task['expected_answer'][:80]!r}", flush=True)
    t0 = time.time()
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
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
    for tu in tool_uses[:8]:
        if "financebench" in (tu.get("name") or ""):
            print(f"     - {tu['name']}({tu['input']})")
    print(f"   final_text: {(final_text or '')[:200]!r}")
    return {"final_text": final_text, "tool_uses": tool_uses, "elapsed": elapsed}


def main():
    with open(os.path.join(HERE, "tasks", "t2_financebench.jsonl")) as f:
        tasks = [json.loads(l) for l in f if l.strip()]
    # pick first numeric-answer task
    task = next((t for t in tasks if t["metadata"]["question_type"] == "metrics-generated"), tasks[0])
    res = run_one(task)
    v = verify(res["final_text"] or "", task["expected_answer"], question=task["metadata"]["question"])
    print(f"\n=== Verify ===")
    print(json.dumps(v, indent=2, default=str))
    print(f"\nVERDICT: {'PASS' if v['ok'] else 'FAIL'}")


if __name__ == "__main__":
    main()
