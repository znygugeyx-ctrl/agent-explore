"""
Unified runner for the three orchestration modes under Claude Code.

All three entrypoints — run_single / run_ow / run_sw — return RunResult
with the same shape so downstream benchmark / scoring code is mode-agnostic.

Observability: lead-view only (per design decision). For OW and SW we capture
every tool_use the lead emits (Agent / TeamCreate / SendMessage), which is
sufficient to verify the mode actually engaged its protocol.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DEFAULT_TIMEOUT = 240


@dataclass
class RunResult:
    mode: str  # "single" | "ow" | "sw"
    ok: bool
    final_text: str | None
    elapsed_s: float
    rc: int
    timeout: bool = False

    # event counts and tool inventory (lead view)
    n_events: int = 0
    event_types: dict[str, int] = field(default_factory=dict)
    tool_uses: list[dict[str, Any]] = field(default_factory=list)

    # mode-specific extracted facts
    team_create_calls: list[dict] = field(default_factory=list)
    agent_spawns: list[dict] = field(default_factory=list)
    send_messages: list[dict] = field(default_factory=list)

    # raw stream for forensics; truncated if huge
    raw_stdout_path: str | None = None

    # SW only: filesystem trace path (mailbox / task list snapshots)
    fs_trace_path: str | None = None
    team_name: str | None = None

    def short(self) -> dict:
        d = asdict(self)
        d.pop("event_types", None)
        return {
            "mode": self.mode,
            "ok": self.ok,
            "final_text": (self.final_text or "")[:200],
            "elapsed_s": round(self.elapsed_s, 1),
            "n_events": self.n_events,
            "n_tool_uses": len(self.tool_uses),
            "n_agent_spawns": len(self.agent_spawns),
            "n_send_messages": len(self.send_messages),
        }


def _parse_stream(stdout: str) -> list[dict]:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _ingest_events(events: list[dict], r: RunResult) -> None:
    r.n_events = len(events)
    for ev in events:
        t = ev.get("type", "?")
        r.event_types[t] = r.event_types.get(t, 0) + 1
        if t == "assistant":
            for blk in (ev.get("message", {}) or {}).get("content", []) or []:
                if blk.get("type") == "tool_use":
                    name = blk.get("name")
                    inp = blk.get("input") or {}
                    r.tool_uses.append({"name": name, "input_keys": list(inp.keys())})
                    if name == "TeamCreate":
                        r.team_create_calls.append(inp)
                    elif name == "Agent":
                        r.agent_spawns.append(
                            {
                                "name": inp.get("name"),
                                "subagent_type": inp.get("subagent_type"),
                                "team_name": inp.get("team_name"),
                                "prompt_preview": (inp.get("prompt") or "")[:160],
                            }
                        )
                    elif name == "SendMessage":
                        r.send_messages.append(
                            {
                                "to": inp.get("to"),
                                "message_preview": str(inp.get("message", ""))[:160],
                            }
                        )
        if t == "result":
            r.final_text = ev.get("result")


def _invoke(
    prompt: str,
    extra_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    log_dir: str | None = None,
    tag: str = "run",
    early_stop_on_answer: bool = False,
    answer_grace_s: float = 8.0,
) -> tuple[RunResult, str]:
    """
    Run claude --print and capture stream-json.

    early_stop_on_answer: if True, stream stdout in real time. Once a `result`
        event arrives OR an assistant text contains a final ANSWER line, wait
        `answer_grace_s` seconds for any pending tool calls to flush, then
        terminate the process. This is needed for SW mode where the lead's
        in-process inbox-poll loop otherwise keeps it alive.
    """
    args = [
        CLAUDE_BIN,
        "--print",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if extra_args:
        args += extra_args
    args.append(prompt)

    r = RunResult(mode="?", ok=False, final_text=None, elapsed_s=0.0, rc=-1)
    t0 = time.time()

    if not early_stop_on_answer:
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            stdout, stderr = proc.stdout, proc.stderr
            r.rc = proc.returncode
        except subprocess.TimeoutExpired as e:
            r.timeout = True
            so, se = e.stdout, e.stderr
            if isinstance(so, bytes):
                so = so.decode("utf-8", errors="replace")
            if isinstance(se, bytes):
                se = se.decode("utf-8", errors="replace")
            stdout = so or ""
            stderr = se or ""
            r.rc = -2
    else:
        # streaming path with early-stop
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        stdout_lines = []
        stderr_acc = []
        answer_seen_at = None
        deadline = t0 + timeout
        import select
        import re as _re
        ANS_RE = _re.compile(r"^\s*ANSWER\s*=", _re.MULTILINE)

        try:
            while True:
                if proc.poll() is not None:
                    # drain remaining
                    rest = proc.stdout.read() if proc.stdout else ""
                    if rest:
                        stdout_lines.append(rest)
                    break
                now = time.time()
                if now > deadline:
                    r.timeout = True
                    proc.terminate()
                    try: proc.wait(timeout=3)
                    except Exception: proc.kill()
                    break
                if answer_seen_at and (now - answer_seen_at) >= answer_grace_s:
                    proc.terminate()
                    try: proc.wait(timeout=3)
                    except Exception: proc.kill()
                    break

                ready, _, _ = select.select([proc.stdout], [], [], 0.5)
                if ready:
                    line = proc.stdout.readline()
                    if not line:
                        continue
                    stdout_lines.append(line)
                    # check for ANSWER in assistant text or in result
                    try:
                        ev = json.loads(line.strip())
                    except Exception:
                        ev = None
                    if ev:
                        if ev.get("type") == "assistant":
                            blocks = (ev.get("message", {}) or {}).get("content", []) or []
                            for b in blocks:
                                if b.get("type") == "text" and b.get("text") and ANS_RE.search(b["text"]):
                                    answer_seen_at = answer_seen_at or now
                                    break
                        elif ev.get("type") == "result" and ev.get("result") and ANS_RE.search(str(ev.get("result", ""))):
                            answer_seen_at = answer_seen_at or now
            stderr_acc.append(proc.stderr.read() if proc.stderr else "")
            r.rc = proc.returncode if proc.returncode is not None else -2
        finally:
            try: proc.stdout.close()
            except Exception: pass
            try: proc.stderr.close()
            except Exception: pass
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_acc)
    r.elapsed_s = time.time() - t0

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"{tag}_{uuid.uuid4().hex[:8]}.jsonl")
        with open(path, "w") as f:
            f.write(stdout)
        r.raw_stdout_path = path

    events = _parse_stream(stdout)
    _ingest_events(events, r)
    r.ok = (r.rc == 0) and (r.final_text is not None)
    return r, stderr


# ---------- mode 1: Single ----------

def run_single(
    task_prompt: str,
    timeout: int = DEFAULT_TIMEOUT,
    log_dir: str | None = None,
    tag: str = "single",
) -> RunResult:
    r, _ = _invoke(task_prompt, extra_args=None, timeout=timeout, log_dir=log_dir, tag=tag)
    r.mode = "single"
    return r


# ---------- mode 2: Orchestrator-Worker ----------

def run_ow(
    task_prompt: str,
    workers: dict[str, dict],
    orchestrator_instructions: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    log_dir: str | None = None,
    tag: str = "ow",
) -> RunResult:
    """
    workers: {name: {"description": str, "prompt": str}} passed via --agents.
    orchestrator_instructions: optional preamble forcing the lead to delegate.
    """
    if orchestrator_instructions is None:
        names = ", ".join(workers.keys())
        orchestrator_instructions = (
            f"You are an orchestrator. Available worker subagents: {names}. "
            f"For the task below, you MUST delegate to one or more of these workers "
            f"using the Agent tool with the appropriate subagent_type. "
            f"Synthesize their outputs into a final answer.\n\n"
        )
    full = orchestrator_instructions + "TASK:\n" + task_prompt
    extra = ["--agents", json.dumps(workers)]
    r, _ = _invoke(full, extra_args=extra, timeout=timeout, log_dir=log_dir, tag=tag)
    r.mode = "ow"
    return r


# ---------- mode 3: Swarm ----------

def run_sw(
    task_prompt: str,
    teammates: list[dict],
    team_name: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    log_dir: str | None = None,
    tag: str = "sw",
) -> RunResult:
    """
    teammates: list of {name, subagent_type, prompt} — lead spawns each via Agent tool.
    The lead is instructed to:
      1. TeamCreate
      2. Agent(...) for every teammate, attaching them to the team
      3. Coordinate via SendMessage as needed
      4. Synthesize and return final answer
    """
    if team_name is None:
        team_name = f"sw-{uuid.uuid4().hex[:8]}"

    teammate_lines = "\n".join(
        f"  - name={t['name']!r}, subagent_type={t['subagent_type']!r}, role_prompt={t['prompt']!r}"
        for t in teammates
    )

    teammate_names = ", ".join(repr(t["name"]) for t in teammates)

    lead_prompt = f"""You are the lead of a swarm. Set up the swarm and coordinate it to solve the task.

REQUIRED setup steps (do them in order before anything else):
1. Call TeamCreate with team_name="{team_name}" and a one-line description.
2. For EACH teammate listed below, call the Agent tool with team_name="{team_name}",
   the given name, the given subagent_type, and the role_prompt as the prompt.

TEAMMATES:
{teammate_lines}

After spawning, coordinate via SendMessage to get the task solved.

STRICT FINAL-OUTPUT PROTOCOL — failure to follow this means the run is invalid:

1. After teammates have returned the information you need, SYNTHESIZE the final answer
   YOURSELF. Do NOT wait for additional teammate turns. Do NOT print messages like
   "waiting for X" — those are not answers.

2. Once you have a complete final answer:
   a) Call TaskStop on EACH teammate ({teammate_names}) to terminate them.
      If TaskStop is unavailable, send SendMessage with message={{"type":"shutdown_request"}}
      to each teammate.
   b) IGNORE every subsequent inbox notification (idle, shutdown_approved, etc).
      Do NOT call any further tools. Do NOT respond to teammate messages.
   c) Emit ONE final assistant message that:
        - includes the answer in detail
        - ends with a line literally starting with "ANSWER=" containing the structured
          answer (json dict, list, or string per the task)
   d) Then STOP. No further output.

3. The "ANSWER=" line is mandatory. Without it the run is scored as invalid.

TASK TO SOLVE:
{task_prompt}
"""
    # Start filesystem watcher BEFORE spawning the swarm so we capture the
    # team config and inboxes as they appear/change. Stop and dump on exit.
    fs_trace_path = None
    watcher = None
    if log_dir:
        try:
            from .fs_watcher import SwarmFsWatcher
        except ImportError:
            from fs_watcher import SwarmFsWatcher  # type: ignore
        fs_trace_path = os.path.join(log_dir, f"{tag}_{team_name}_fs.jsonl")
        watcher = SwarmFsWatcher(team_name=team_name, out_path=fs_trace_path, poll_s=0.5)
        watcher.start()
    try:
        r, _ = _invoke(
            lead_prompt,
            extra_args=None,
            timeout=timeout,
            log_dir=log_dir,
            tag=tag,
            early_stop_on_answer=True,
            answer_grace_s=20.0,
        )
    finally:
        if watcher is not None:
            watcher.stop()
    r.mode = "sw"
    r.fs_trace_path = fs_trace_path
    r.team_name = team_name
    return r
