"""
Probe 3: daemon-mode swarm with teammate-to-teammate DM.

Goal: verify we can drive a real Claude Code swarm via `--print`:
- lead creates a team
- lead spawns 2 teammates (alice, bob)
- alice and bob exchange DMs
- lead reports the combined result

Observability:
1. stream-json: capture every TeamCreate / Agent / SendMessage tool_use
2. filesystem: snapshot ~/.claude/teams/<name>/ and ~/.claude/tasks/<name>/
3. timeline.jsonl files for any spawned background jobs
"""

import json
import os
import subprocess
import time
import shutil
import sys

CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
LOG_DIR = os.path.dirname(__file__)
TEAM_NAME = f"probe3-{int(time.time())}"
TEAMS_DIR = os.path.expanduser(f"~/.claude/teams/{TEAM_NAME}")
TASKS_DIR = os.path.expanduser(f"~/.claude/tasks/{TEAM_NAME}")


def banner(s):
    print(f"\n{'=' * 60}\n{s}\n{'=' * 60}", flush=True)


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


def summarize(events: list) -> dict:
    s = {
        "total": len(events),
        "types": {},
        "tool_uses": [],
        "team_create": [],
        "agent_spawn": [],
        "send_message": [],
        "user_msgs_inbound": [],
        "final_text": None,
    }
    for ev in events:
        t = ev.get("type", "?")
        s["types"][t] = s["types"].get(t, 0) + 1
        if t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    name = blk.get("name")
                    inp = blk.get("input") or {}
                    s["tool_uses"].append({"name": name, "input": inp})
                    if name == "TeamCreate":
                        s["team_create"].append(inp)
                    elif name == "Agent":
                        s["agent_spawn"].append(
                            {
                                "subagent_type": inp.get("subagent_type"),
                                "name": inp.get("name"),
                                "team_name": inp.get("team_name"),
                                "prompt_preview": (inp.get("prompt") or "")[:120],
                            }
                        )
                    elif name == "SendMessage":
                        s["send_message"].append(
                            {
                                "to": inp.get("to"),
                                "msg_preview": str(inp.get("message", ""))[:120],
                            }
                        )
        if t == "user":
            # inbound messages from teammates surface as user-role turns
            content = (ev.get("message", {}) or {}).get("content")
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "tool_result":
                        continue  # skip tool results
                txt = json.dumps(content)[:200]
                s["user_msgs_inbound"].append(txt)
            elif isinstance(content, str):
                s["user_msgs_inbound"].append(content[:200])
        if t == "result":
            s["final_text"] = ev.get("result")
    return s


def snapshot_fs():
    snap = {}
    for d, label in [(TEAMS_DIR, "team"), (TASKS_DIR, "tasks")]:
        if os.path.isdir(d):
            files = []
            for root, _, fs in os.walk(d):
                for f in fs:
                    p = os.path.join(root, f)
                    rel = os.path.relpath(p, d)
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = -1
                    files.append({"path": rel, "size": size})
            snap[label] = {"dir": d, "files": files}
        else:
            snap[label] = {"dir": d, "files": None}
    return snap


def main():
    banner(f"Probe 3 — swarm with team={TEAM_NAME}")

    # cleanup any prior state
    for d in (TEAMS_DIR, TASKS_DIR):
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)

    lead_prompt = f"""You are the lead agent for a small swarm experiment.

Do exactly the following sequence using the available tools. Be brief.

1. Call TeamCreate with team_name="{TEAM_NAME}" and description="probe3 DM test".
2. Spawn two teammates using the Agent tool, each with team_name="{TEAM_NAME}":
   - name="alice", subagent_type="general-purpose", prompt="You are ALICE. When you receive a DM from BOB asking for a number, reply to bob with: 'My number is 7'. After replying, go idle."
   - name="bob",   subagent_type="general-purpose", prompt="You are BOB. Send a DM to alice asking 'What is your number?'. Wait for her reply. Once you receive it, send a DM to the lead with: 'COMBINED=alice+5=<her_number+5>'. Then go idle."
3. Wait until you (the lead) receive bob's DM containing 'COMBINED='.
4. Reply with exactly: FINAL:<the COMBINED string bob sent>

Do not improvise. Do not skip steps. Use the tools by name as written.
"""

    args = [
        CLAUDE,
        "--print",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        lead_prompt,
    ]

    print(f"Spawning lead (timeout 6min)...", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=360)
        elapsed = time.time() - t0
        print(f"lead exited rc={proc.returncode} in {elapsed:.1f}s", flush=True)
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        print(f"lead TIMEOUT after {elapsed:.1f}s — saving partial output", flush=True)
        with open(os.path.join(LOG_DIR, "probe3_stdout.txt"), "w") as f:
            f.write(e.stdout or "")
        with open(os.path.join(LOG_DIR, "probe3_stderr.txt"), "w") as f:
            f.write(e.stderr or "")
        snap = snapshot_fs()
        print("FS snapshot at timeout:", json.dumps(snap, indent=2), flush=True)
        return

    with open(os.path.join(LOG_DIR, "probe3_stdout.txt"), "w") as f:
        f.write(proc.stdout)
    with open(os.path.join(LOG_DIR, "probe3_stderr.txt"), "w") as f:
        f.write(proc.stderr)

    events = parse_stream(proc.stdout)
    s = summarize(events)

    banner("SUMMARY")
    print(f"events: {s['total']}  types: {s['types']}", flush=True)
    print(f"TeamCreate calls:   {len(s['team_create'])} -> {s['team_create']}", flush=True)
    print(f"Agent spawn calls:  {len(s['agent_spawn'])}", flush=True)
    for a in s["agent_spawn"]:
        print(f"  - name={a['name']} type={a['subagent_type']} team={a['team_name']}", flush=True)
    print(f"SendMessage calls:  {len(s['send_message'])}", flush=True)
    for m in s["send_message"]:
        print(f"  - to={m['to']!r}  msg={m['msg_preview']!r}", flush=True)
    print(f"Inbound user msgs (potential teammate DMs to lead): {len(s['user_msgs_inbound'])}", flush=True)
    for u in s["user_msgs_inbound"][:5]:
        print(f"  ! {u[:160]}", flush=True)
    print(f"final: {(s['final_text'] or '')[:300]!r}", flush=True)

    banner("FILESYSTEM SNAPSHOT")
    snap = snapshot_fs()
    print(json.dumps(snap, indent=2), flush=True)

    banner("PASS/FAIL")
    teamcreate_ok = len(s["team_create"]) >= 1
    spawn_ok = len(s["agent_spawn"]) >= 2
    dm_ok = len(s["send_message"]) >= 1  # at minimum bob -> lead
    fs_team_ok = snap["team"]["files"] is not None and len(snap["team"]["files"]) > 0
    final_ok = "FINAL:COMBINED=" in (s["final_text"] or "")
    print(f"  TeamCreate fired:        {'PASS' if teamcreate_ok else 'FAIL'}", flush=True)
    print(f"  ≥2 teammates spawned:    {'PASS' if spawn_ok else 'FAIL'}", flush=True)
    print(f"  ≥1 SendMessage call:     {'PASS' if dm_ok else 'FAIL'}", flush=True)
    print(f"  team config on disk:     {'PASS' if fs_team_ok else 'FAIL'}", flush=True)
    print(f"  final answer relayed:    {'PASS' if final_ok else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
