"""
Probe 2: subagent dispatch via --agents flag.

Goal: verify we can programmatically spawn a subagent and capture its output.

Strategy: use `claude --print` (non-interactive) with --agents to inject
a custom 'mathbot' agent, then ask the main agent to delegate to it.

If --print works, we don't need pty for the orchestrator-worker mode at all.
"""

import json
import subprocess
import time
import os
import sys

CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
LOG_DIR = os.path.dirname(__file__)


def banner(s):
    print(f"\n{'=' * 60}\n{s}\n{'=' * 60}", flush=True)


def run_print(prompt: str, agents: dict | None = None, timeout: int = 180) -> dict:
    args = [
        CLAUDE,
        "--print",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if agents:
        args += ["--agents", json.dumps(agents)]
    args.append(prompt)

    print(f"$ {' '.join(args[:6])} ... [+agents={'yes' if agents else 'no'}]", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "reason": "timeout", "stdout": e.stdout or "", "stderr": e.stderr or ""}
    return {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        "elapsed": time.time() - t0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def parse_stream(stdout: str) -> list:
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def summarize_events(events: list) -> dict:
    summary = {
        "total_events": len(events),
        "types": {},
        "tool_uses": [],
        "subagent_calls": [],
        "final_text": None,
    }
    for ev in events:
        t = ev.get("type", "?")
        summary["types"][t] = summary["types"].get(t, 0) + 1
        if t == "assistant":
            msg = ev.get("message", {})
            for blk in msg.get("content", []) or []:
                if blk.get("type") == "tool_use":
                    summary["tool_uses"].append(
                        {
                            "name": blk.get("name"),
                            "input_keys": list((blk.get("input") or {}).keys()),
                        }
                    )
                    if blk.get("name") == "Agent":
                        summary["subagent_calls"].append(blk.get("input", {}))
        if t == "result":
            summary["final_text"] = ev.get("result")
    return summary


def main():
    # ---- L1: --print works at all ----
    banner("L1: --print baseline (no agents)")
    r = run_print("Reply with exactly: PROBE2_OK")
    if not r["ok"]:
        print(f"FAIL rc={r.get('rc')} reason={r.get('reason','')}", flush=True)
        print("stderr:", r.get("stderr", "")[-1000:], flush=True)
        return
    events = parse_stream(r["stdout"])
    s = summarize_events(events)
    print(f"elapsed={r['elapsed']:.1f}s events={s['total_events']} types={s['types']}", flush=True)
    print(f"final: {s['final_text']!r}", flush=True)
    l1_ok = "PROBE2_OK" in (s["final_text"] or "")
    print(f"L1: {'PASS' if l1_ok else 'FAIL'}", flush=True)

    # ---- L2: --agents injection + delegation via Agent tool ----
    banner("L2: inject custom subagent + delegate")
    agents = {
        "mathbot": {
            "description": "Specialist for arithmetic. Always invoke for math problems.",
            "prompt": (
                "You are MATHBOT. For any arithmetic question, reply with the format:\n"
                "MATHBOT_ANSWER=<number>\n"
                "Nothing else. No explanation."
            ),
        }
    }
    delegate_prompt = (
        "Delegate this task to the mathbot agent and return its answer verbatim:\n"
        "What is 17 * 23?\n"
        "Use the Agent tool with subagent_type='mathbot'."
    )
    r = run_print(delegate_prompt, agents=agents, timeout=240)
    if not r["ok"]:
        print(f"FAIL rc={r.get('rc')} reason={r.get('reason','')}", flush=True)
        print("stderr:", r.get("stderr", "")[-1500:], flush=True)
        with open(os.path.join(LOG_DIR, "probe2_l2_stdout.txt"), "w") as f:
            f.write(r.get("stdout", ""))
        return

    events = parse_stream(r["stdout"])
    s = summarize_events(events)
    print(f"elapsed={r['elapsed']:.1f}s events={s['total_events']} types={s['types']}", flush=True)
    print(f"tool_uses: {s['tool_uses']}", flush=True)
    print(f"subagent_calls: {s['subagent_calls']}", flush=True)
    print(f"final: {(s['final_text'] or '')[:300]!r}", flush=True)

    # save raw stream
    with open(os.path.join(LOG_DIR, "probe2_l2_stdout.txt"), "w") as f:
        f.write(r["stdout"])

    delegated = any(
        tu.get("name") == "Agent" and "mathbot" in str(tu.get("input_keys"))
        for tu in s["tool_uses"]
    ) or len(s["subagent_calls"]) > 0
    answer_correct = "391" in (s["final_text"] or "")
    print(f"L2_delegated_to_mathbot: {'PASS' if delegated else 'FAIL'}", flush=True)
    print(f"L2_answer_17x23=391:    {'PASS' if answer_correct else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
