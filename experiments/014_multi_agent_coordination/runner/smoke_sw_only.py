"""Smoke test SW alone with longer timeout."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runner import run_sw

LOG_DIR = os.path.join(os.path.dirname(__file__), "_logs")

teammates = [
    {
        "name": "multiplier",
        "subagent_type": "general-purpose",
        "prompt": (
            "You are MULTIPLIER. When the lead DMs you with two numbers, "
            "reply to the lead with just the integer product, then go idle."
        ),
    },
    {
        "name": "adder",
        "subagent_type": "general-purpose",
        "prompt": (
            "You are ADDER. When the lead DMs you with two numbers, "
            "reply to the lead with just the integer sum, then go idle."
        ),
    },
]
task = (
    "Step 1: SendMessage to multiplier asking for 17*23. "
    "Step 2: When multiplier replies, SendMessage to adder asking it to add 5 to that result. "
    "Step 3: When adder replies, shutdown both teammates and return: ANSWER=<final number>"
)

r = run_sw(task, teammates=teammates, log_dir=LOG_DIR, timeout=420)
print(json.dumps(r.short(), indent=2, ensure_ascii=False))
print("timeout?", r.timeout, "rc=", r.rc)
print("TeamCreate:", r.team_create_calls)
print("Spawns:")
for a in r.agent_spawns:
    print(f"  - {a['name']} ({a['subagent_type']}) team={a['team_name']}")
print("SendMessage:")
for m in r.send_messages:
    print(f"  - to={m['to']!r} msg={m['message_preview']!r}")
print(f"final_text: {r.final_text!r}")
got = "396" in (r.final_text or "")
print(f"answer correct: {got}")
print(f"raw stream: {r.raw_stdout_path}")
