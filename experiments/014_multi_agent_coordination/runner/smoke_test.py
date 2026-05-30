"""
Smoke test the unified runner: same arithmetic question, three modes.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runner import run_single, run_ow, run_sw  # noqa: E402

LOG_DIR = os.path.join(os.path.dirname(__file__), "_logs")
QUESTION = "Compute 17 * 23 + 5. Reply with exactly: ANSWER=<number>"


def show(r):
    print(json.dumps(r.short(), indent=2, ensure_ascii=False), flush=True)
    if r.team_create_calls:
        print("  TeamCreate:", r.team_create_calls, flush=True)
    if r.agent_spawns:
        print("  Spawns:", flush=True)
        for a in r.agent_spawns:
            print(f"    - {a['name']} ({a['subagent_type']}) team={a['team_name']}", flush=True)
    if r.send_messages:
        print("  SendMessage:", flush=True)
        for m in r.send_messages:
            print(f"    - to={m['to']!r} msg={m['message_preview']!r}", flush=True)


def main():
    print("\n=== SINGLE ===", flush=True)
    r1 = run_single(QUESTION, log_dir=LOG_DIR, timeout=120)
    show(r1)

    print("\n=== OW ===", flush=True)
    workers = {
        "calculator": {
            "description": "Specialist for arithmetic. Always invoke for math.",
            "prompt": "You are CALCULATOR. Reply with exactly: ANSWER=<number>",
        }
    }
    r2 = run_ow(QUESTION, workers=workers, log_dir=LOG_DIR, timeout=180)
    show(r2)

    print("\n=== SW ===", flush=True)
    teammates = [
        {
            "name": "multiplier",
            "subagent_type": "general-purpose",
            "prompt": (
                "You are MULTIPLIER. When the lead asks you to multiply two numbers, "
                "compute the product and reply with the integer result. Then go idle."
            ),
        },
        {
            "name": "adder",
            "subagent_type": "general-purpose",
            "prompt": (
                "You are ADDER. When the lead asks you to add two numbers, "
                "compute the sum and reply with the integer result. Then go idle."
            ),
        },
    ]
    sw_task = (
        "Use multiplier to compute 17*23, then use adder to add 5 to the result. "
        "Return the final answer as: ANSWER=<number>"
    )
    r3 = run_sw(sw_task, teammates=teammates, log_dir=LOG_DIR, timeout=300)
    show(r3)

    print("\n=== EXPECTED ANSWER: 396 ===", flush=True)
    for label, r in [("single", r1), ("ow", r2), ("sw", r3)]:
        got = "396" in (r.final_text or "")
        mark = "PASS" if got else "FAIL"
        print(f"  {mark}  {label}  -> {(r.final_text or '')[:80]!r}", flush=True)


if __name__ == "__main__":
    main()
