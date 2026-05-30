"""
Manual demo: OW-with-Verifier (OWV) on a single task from each benchmark.

Usage:
    python3 run_owv_demo.py plancraft       # run plancraft demo
    python3 run_owv_demo.py financebench    # run financebench demo
    python3 run_owv_demo.py workbench       # run workbench demo
    python3 run_owv_demo.py all             # run all three

Design:
- Lead solves the task itself using MCP tools.
- BEFORE emitting ANSWER, lead MUST spawn `verifier` subagent at least once.
- Verifier independently re-checks via the same MCP tools.
- If verifier replies VERIFY_FAIL, lead reads the suggested fix and tries
  again, then re-spawns verifier. Up to 3 verification rounds.
- This keeps the lead as the locus of action (single chain of reasoning),
  while the verifier provides an independent validation bottleneck — the
  paper's "Centralized" architecture in its purest form.
"""
import json
import os
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
WBENCH_REPO = os.path.join(EXP, "_vendor", "WorkBench")
FB_DATA = os.path.join(EXP, "_vendor", "financebench", "financebench_open_source.jsonl")
WBENCH_MCP = os.path.join(EXP, "mcp_servers", "workbench_server.py")
FB_MCP = os.path.join(EXP, "mcp_servers", "financebench_server.py")
PC_MCP = os.path.join(EXP, "mcp_servers", "plancraft_server.py")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")


# =============================================================================
# Verifier prompts (per benchmark — verification logic differs by domain)
# =============================================================================

VERIFIER_PROMPT_PLANCRAFT = """You are VERIFIER. The lead has just attempted to solve a Minecraft
crafting puzzle. Your job: INDEPENDENTLY verify whether the target item is in
the inventory. DO NOT TRUST what the lead claims — call the tools yourself.

Procedure:
1. Call mcp__plancraft__get_target to confirm what item is needed.
2. Call mcp__plancraft__get_inventory to see the actual current state.
3. Check whether that item is present with quantity >= 1 in any slot.
4. Reply with first line:
     - "VERIFY_OK" if the target is in the inventory.
     - "VERIFY_FAIL" if it is not.
   Then add 1-2 short sentences:
     - On OK: state which slot has the target.
     - On FAIL: list which ingredients ARE in the inventory and what step the
       lead likely missed (e.g., "you have jungle_planks in slot 11 but never
       arranged them in the crafting grid as a horizontal row to make jungle_slab").

Be objective. Do not reject for cosmetic issues — only check has_target.
"""


VERIFIER_PROMPT_FINANCEBENCH = """You are VERIFIER. The lead has just attempted to answer a financial
question by reading SEC filings. Your job: INDEPENDENTLY re-check the lead's
numerical/factual answer using the same MCP tools.

Procedure:
1. Read the lead's claim (target answer + which doc/page they used).
2. Use mcp__financebench__open_filing / read_page / search_in_filing to RE-FETCH
   the same data yourself. Do NOT trust the lead's stated numbers.
3. If the question requires calculation (ratio, change, etc.), do the calc
   YOURSELF from the raw figures you just read.
4. Compare your independently-derived answer with the lead's candidate.
5. Reply with first line:
     - "VERIFY_OK" if the lead's answer matches yours within reasonable tolerance
       (e.g., for ratios within 0.01, for dollars within 0.5%).
     - "VERIFY_FAIL" if there is a real numerical discrepancy.
   Then add 2-3 sentences:
     - On OK: state the value you computed and where you read it.
     - On FAIL: state the correct value from your own check, and which page
       contains the right numbers.

Be precise. Floating-point or rounding differences are NOT failures.
"""


VERIFIER_PROMPT_WORKBENCH = """You are VERIFIER. The lead has just attempted to fulfill a workplace
sandbox request by making tool calls (calendar/email/CRM/etc). Your job:
INDEPENDENTLY check whether the sandbox state now reflects what the user asked.

Procedure:
1. Read the user's original request and what the lead claims to have done.
2. Use the appropriate MCP tools (calendar_search_events, email_search_emails,
   project_management_search_tasks, customer_relationship_manager_search_customers,
   etc) to inspect the actual current state.
3. Verify all the user-requested changes happened correctly:
     - Right items were created/deleted/modified.
     - No collateral changes (lead didn't accidentally delete extra).
     - The user's intent (e.g., "all future meetings with X") was fully honored.
4. Reply with first line:
     - "VERIFY_OK" if state correctly reflects user intent.
     - "VERIFY_FAIL" otherwise.
   Then add 2-3 sentences:
     - On OK: list what you checked and what you saw.
     - On FAIL: state which specific item is wrong/missing/extra and what the
       lead must do to fix it (specific tool call + parameters).

Be thorough. The user's request may have multiple parts.
"""


# =============================================================================
# Lead prompt template (benchmark-agnostic protocol; task-specific body inserted)
# =============================================================================

LEAD_PROMPT_TEMPLATE = """You are the LEAD agent. Solve the task using the available MCP tools.

=== MANDATORY VERIFICATION PROTOCOL ===
This protocol is a HARD requirement. You MUST follow it.

1. SOLVE: Use the MCP tools to perform the task as best you can.

2. VERIFY (mandatory before ANSWER): Once you believe you are done, you MUST call
   the Agent tool with subagent_type='verifier'. In the verifier's prompt, include:
     - the original user task / question
     - your candidate answer or what you claim to have done
     - the key facts / tool calls you relied on
   The verifier will INDEPENDENTLY re-check using the same MCP tools.

3. READ verifier reply (it is a tool_result):
     - First line "VERIFY_OK"   → proceed to step 4.
     - First line "VERIFY_FAIL" → read the suggested fix carefully. Apply
       additional MCP tool calls to address it. Then GO BACK to step 2 and
       spawn the verifier AGAIN with the corrected state.
     - Up to 3 verification rounds total. After 3, output ANSWER regardless.

4. FINISH: Output your final reply ending with the appropriate ANSWER line:
     - {answer_format}

HARD CONSTRAINT: At least ONE Agent(verifier) call MUST happen before ANSWER.
The run is invalid if you skip verification.

=== TASK ===
{task_body}
"""


# =============================================================================
# Per-benchmark task setup
# =============================================================================

def setup_plancraft():
    task_id = "plancraft/VAL0114"
    with open(os.path.join(HERE, "tasks", "t3_plancraft.jsonl")) as f:
        for l in f:
            t = json.loads(l)
            if t["id"] == task_id:
                task = t; break
    state_out = f"/tmp/owv_pc_state_{uuid.uuid4().hex[:6]}.json"
    cfg = {"mcpServers": {"plancraft": {
        "command": "python3", "args": [PC_MCP],
        "env": {"PC_TASK_FILE": task["metadata"]["state_file"],
                "PC_STATE_OUT": state_out},
    }}}
    cfg_path = f"/tmp/owv_pc_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(cfg_path, "w") as f: json.dump(cfg, f)

    body = (
        f"You are playing a Minecraft crafting puzzle. Tools (mcp__plancraft__*):\n"
        f"  get_target, get_inventory, move(slot_from, slot_to, quantity), smelt(...), stop(reason).\n\n"
        f"Slot layout:\n"
        f"  - slot 0: crafting output (auto-populated when 1-9 form a recipe)\n"
        f"  - slots 1-9: 3x3 crafting grid (top row 1-3, mid 4-6, bot 7-9)\n"
        f"  - slots 10-45: main inventory storage\n"
        f"  - slots 44/45: furnace input/output\n\n"
        f"Target: {task['expected_answer']}\n"
        f"Optimal path length: {task['metadata']['optimal_path_length']} step(s).\n"
    )
    answer_format = "ANSWER=done"
    verifier_prompt = VERIFIER_PROMPT_PLANCRAFT
    return {
        "task": task,
        "cfg_path": cfg_path,
        "state_out": state_out,
        "body": body,
        "answer_format": answer_format,
        "verifier_prompt": verifier_prompt,
        "ground_truth": "plancraft_state",
    }


def setup_financebench():
    target_id = "financebench/financebench_id_10499"
    with open(os.path.join(HERE, "tasks", "t2_financebench.jsonl")) as f:
        for l in f:
            t = json.loads(l)
            if t["id"] == target_id:
                task = t; break
    cfg = {"mcpServers": {"financebench": {
        "command": "python3", "args": [FB_MCP],
        "env": {"FB_DATA": FB_DATA},
    }}}
    cfg_path = f"/tmp/owv_fb_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(cfg_path, "w") as f: json.dump(cfg, f)
    body = (
        f"You are a financial analyst. Tools (mcp__financebench__*):\n"
        f"  list_filings, search_filings, open_filing, search_in_filing, read_page.\n\n"
        f"Question: {task['metadata']['question']}\n\n"
        f"(Hint: relevant filing is {task['metadata']['company']}'s "
        f"{task['metadata'].get('doc_period') or '?'} {task['metadata'].get('question_type','?')} — "
        f"doc_name='{task['metadata']['doc_name']}'.)"
    )
    answer_format = "ANSWER=<your number / value / short phrase>"
    verifier_prompt = VERIFIER_PROMPT_FINANCEBENCH
    return {
        "task": task,
        "cfg_path": cfg_path,
        "state_out": None,
        "body": body,
        "answer_format": answer_format,
        "verifier_prompt": verifier_prompt,
        "ground_truth": f"expected={task['expected_answer']!r}",
    }


def setup_workbench():
    target_id = "workbench/multi_domain/205"
    with open(os.path.join(HERE, "tasks", "t1_workbench.jsonl")) as f:
        for l in f:
            t = json.loads(l)
            if t["id"] == target_id:
                task = t; break
    task_id_safe = task["id"].replace("/", "_")
    state_out = f"/tmp/owv_wb_state_{task_id_safe}_{uuid.uuid4().hex[:6]}.json"
    cfg = {"mcpServers": {"workbench": {
        "command": "python3", "args": [WBENCH_MCP],
        "env": {"WBENCH_REPO": WBENCH_REPO, "WBENCH_TASK_ID": task_id_safe,
                "WBENCH_STATE_OUT": state_out, "PYTHONPATH": WBENCH_REPO},
    }}}
    cfg_path = f"/tmp/owv_wb_mcp_{uuid.uuid4().hex[:6]}.json"
    with open(cfg_path, "w") as f: json.dump(cfg, f)
    body = (
        f"You are operating in a workplace sandbox. Tools (mcp__workbench__*):\n"
        f"  calendar_*, email_*, analytics_*, project_management_*, "
        f"customer_relationship_manager_*, company_directory_*\n\n"
        f"The current time is 2023-11-30 09:00:00.\n\n"
        f"User request: {task['metadata']['query']}"
    )
    answer_format = "ANSWER=done"
    verifier_prompt = VERIFIER_PROMPT_WORKBENCH
    return {
        "task": task,
        "cfg_path": cfg_path,
        "state_out": state_out,
        "body": body,
        "answer_format": answer_format,
        "verifier_prompt": verifier_prompt,
        "ground_truth": f"expected_actions={task['expected_answer']}",
    }


# =============================================================================
# Run
# =============================================================================

def run_one(setup: dict, timeout: int = 600):
    cfg_path = setup["cfg_path"]
    body = setup["body"]
    answer_format = setup["answer_format"]
    verifier_prompt = setup["verifier_prompt"]

    lead_prompt = LEAD_PROMPT_TEMPLATE.format(
        task_body=body, answer_format=answer_format
    )

    agents_def = {"verifier": {
        "description": "MANDATORY verifier subagent. Use it to independently re-check the answer before emitting the final ANSWER. Spawn it after every solving attempt.",
        "prompt": verifier_prompt,
    }}

    args = [
        CLAUDE, "--print", "--dangerously-skip-permissions",
        "--mcp-config", cfg_path,
        "--agents", json.dumps(agents_def),
        "--output-format", "stream-json", "--verbose",
        lead_prompt,
    ]
    print(f"==> Task: {setup['task']['id']}")
    print(f"    Ground truth: {setup['ground_truth']}")
    print(f"    MCP config: {cfg_path}")
    print(f"    Lead prompt length: {len(lead_prompt)} chars")
    print()
    print("--- streaming events ---", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        print(f"TIMEOUT after {timeout}s")
        return None
    elapsed = time.time() - t0

    tool_uses, verifier_spawns, verifier_responses = [], [], []
    pending_verify_id = None
    final_text = None

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line: continue
        try: ev = json.loads(line)
        except: continue
        t = ev.get("type")
        if t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    name = blk.get("name") or ""
                    inp = blk.get("input") or {}
                    tool_uses.append({"name": name, "input": inp, "id": blk.get("id")})
                    if name == "Agent" and inp.get("subagent_type") == "verifier":
                        verifier_spawns.append(inp)
                        pending_verify_id = blk.get("id")
        elif t == "user" and pending_verify_id:
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    if blk.get("tool_use_id") == pending_verify_id:
                        c = blk.get("content")
                        if isinstance(c, list):
                            text = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                        else:
                            text = c or ""
                        verifier_responses.append(text)
                        pending_verify_id = None
        elif t == "result":
            final_text = ev.get("result")

    print(f"\n=== Run done in {elapsed:.0f}s rc={proc.returncode} ===")
    print(f"\nFinal text (head 400):\n  {(final_text or '')[:400]!r}")

    print(f"\n=== Tool calls ({len(tool_uses)}) ===")
    for tu in tool_uses:
        n = tu["name"]
        if n == "Agent":
            sub = tu["input"].get("subagent_type")
            sp = (tu["input"].get("prompt") or "")
            print(f"  Agent → {sub} (prompt {len(sp)}c)")
        else:
            short_in = {k: (str(v)[:40] + ("…" if len(str(v)) > 40 else "")) for k, v in tu["input"].items()}
            print(f"  {n}({short_in})")

    print(f"\n=== Verifier rounds: {len(verifier_spawns)} ===")
    for i in range(len(verifier_spawns)):
        sp = verifier_spawns[i].get("prompt", "")
        resp = verifier_responses[i] if i < len(verifier_responses) else ""
        first = (resp or "").strip().split("\n")[0] if resp else ""
        verdict = "OK" if first.startswith("VERIFY_OK") else ("FAIL" if first.startswith("VERIFY_FAIL") else "?")
        print(f"\n--- Verify round {i+1} → {verdict} ---")
        print(f"  lead → verifier prompt (head 300):")
        print("    ", sp[:300].replace("\n", "\n      "))
        print(f"\n  verifier reply (head 400):")
        print("    ", (resp or "")[:400].replace("\n", "\n      "))

    # Ground-truth check
    print(f"\n=== Ground truth check ===")
    if setup["ground_truth"] == "plancraft_state":
        if os.path.exists(setup["state_out"]):
            with open(setup["state_out"]) as f:
                state = json.load(f)
            print(f"  has_target: {state.get('has_target')}")
            print(f"  steps_taken: {state.get('steps_taken')}")
            print(f"\nVERDICT: {'PASS' if state.get('has_target') else 'FAIL'}")
    elif setup["ground_truth"].startswith("expected="):
        # financebench: just compare extracted ANSWER to expected manually
        import re
        m = re.search(r"ANSWER\s*=\s*(.+?)\s*$", final_text or "", re.MULTILINE)
        if m:
            print(f"  extracted: {m.group(1).strip()!r}")
            print(f"  {setup['ground_truth']}")
            print(f"\nVERDICT: (manual judgment — see whether the value matches)")
        else:
            print(f"  no ANSWER= line found")
    elif setup["ground_truth"].startswith("expected_actions="):
        # workbench: look at sandbox state file
        if os.path.exists(setup["state_out"]):
            with open(setup["state_out"]) as f:
                state = json.load(f)
            print(f"  state dump keys: {list(state.keys())}")
            print(f"  {setup['ground_truth']}")
            print(f"\nVERDICT: (manual — compare with verifier output above)")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    target = sys.argv[1]
    setups = {
        "plancraft": setup_plancraft,
        "financebench": setup_financebench,
        "workbench": setup_workbench,
    }
    if target == "all":
        for name, fn in setups.items():
            print("\n" + "="*80)
            print(f"BENCHMARK: {name}")
            print("="*80)
            run_one(fn())
    elif target in setups:
        run_one(setups[target]())
    else:
        print(f"unknown: {target!r}; choose: {list(setups.keys())} or 'all'")
        sys.exit(1)


if __name__ == "__main__":
    main()
