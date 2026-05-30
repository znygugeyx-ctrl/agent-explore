"""
PTY feasibility probe for Claude Code.

Goal: verify pexpect can drive `claude` interactively.
- L1: spawn, send a prompt, capture answer, exit cleanly.
- L2: send a second prompt in same session, verify context is retained.
- L3: trigger a slash command (/clear), verify it took effect.

Run: python3 probe_pty.py
"""

import os
import re
import sys
import time
import pexpect

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
LOG_PATH = os.path.join(os.path.dirname(__file__), "probe_log.txt")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]")
BOX_RE = re.compile(r"[│─┌┐└┘├┤┬┴┼╭╮╯╰╴╶╵╷•·]")


def strip_ansi(s: str) -> str:
    s = ANSI_RE.sub("", s)
    s = BOX_RE.sub("", s)
    return s


def banner(msg: str):
    print(f"\n{'=' * 60}\n{msg}\n{'=' * 60}", flush=True)


def spawn_claude():
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    child = pexpect.spawn(
        CLAUDE_BIN,
        args=["--dangerously-skip-permissions"],
        env=env,
        encoding="utf-8",
        timeout=60,
        dimensions=(40, 120),
    )
    fh = open(LOG_PATH, "w")
    child.logfile_read = fh
    return child, fh


def wait_ready(child, label: str, settle_seconds: float = 2.0):
    """Wait until output goes quiet (UI fully painted)."""
    print(f"[{label}] waiting for ready...", flush=True)
    deadline = time.time() + 30
    last_len = -1
    stable_since = None
    while time.time() < deadline:
        try:
            child.read_nonblocking(size=4096, timeout=0.5)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            print(f"[{label}] EOF", flush=True)
            return False
        cur = len(child.before or "")
        if cur == last_len:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= settle_seconds:
                return True
        else:
            stable_since = None
            last_len = cur
    print(f"[{label}] timeout waiting for ready", flush=True)
    return False


def send_prompt(child, text: str):
    # CC accepts typed input; submit with Enter.
    child.send(text)
    time.sleep(0.3)
    child.send("\r")


def collect_until_idle(child, idle_seconds: float = 5.0, max_wait: float = 90.0) -> str:
    """Read everything until output is quiet for idle_seconds."""
    buf = []
    start = time.time()
    last_data = time.time()
    while time.time() - start < max_wait:
        try:
            chunk = child.read_nonblocking(size=8192, timeout=0.5)
            if chunk:
                buf.append(chunk)
                last_data = time.time()
        except pexpect.TIMEOUT:
            if time.time() - last_data >= idle_seconds:
                break
        except pexpect.EOF:
            break
    return "".join(buf)


def find_answer(text: str, needles: list) -> bool:
    clean = strip_ansi(text)
    for n in needles:
        if n in clean:
            return True
    return False


def main():
    banner("PTY Probe — Claude Code")
    print(f"Binary: {CLAUDE_BIN}", flush=True)
    print(f"Log:    {LOG_PATH}", flush=True)

    child, fh = spawn_claude()
    results = {}

    try:
        # ---- L1: startup + single prompt ----
        banner("L1: startup + single prompt")
        if not wait_ready(child, "startup", settle_seconds=3.0):
            results["L1_startup"] = False
            return results

        send_prompt(child, "Reply with exactly the single number: 2+2=?")
        out1 = collect_until_idle(child, idle_seconds=6.0, max_wait=90.0)
        clean1 = strip_ansi(out1)
        print("---- L1 raw tail ----", flush=True)
        print(clean1[-1500:], flush=True)
        results["L1_answered"] = bool(re.search(r"(?<![0-9])4(?![0-9])", clean1))

        # ---- L2: second prompt, context retention ----
        banner("L2: second prompt — context retention")
        send_prompt(
            child,
            "What was the number I just asked about? Reply with only that single digit.",
        )
        out2 = collect_until_idle(child, idle_seconds=6.0, max_wait=90.0)
        clean2 = strip_ansi(out2)
        print("---- L2 raw tail ----", flush=True)
        print(clean2[-1500:], flush=True)
        results["L2_context"] = bool(re.search(r"(?<![0-9])4(?![0-9])", clean2))

        # ---- L3: slash command ----
        banner("L3: slash command (/clear)")
        send_prompt(child, "/clear")
        out3 = collect_until_idle(child, idle_seconds=4.0, max_wait=30.0)
        clean3 = strip_ansi(out3)
        print("---- L3 raw tail ----", flush=True)
        print(clean3[-1500:], flush=True)
        # After /clear, ask the same question — if context cleared, it should not know.
        send_prompt(
            child,
            "What was the number I asked about earlier? If you don't know, reply 'UNKNOWN'.",
        )
        out3b = collect_until_idle(child, idle_seconds=6.0, max_wait=90.0)
        clean3b = strip_ansi(out3b)
        print("---- L3b raw tail ----", flush=True)
        print(clean3b[-1500:], flush=True)
        results["L3_clear_worked"] = "UNKNOWN" in clean3b.upper() or not re.search(
            r"(?<![0-9])4(?![0-9])", clean3b
        )

    finally:
        try:
            child.send("/exit")
            child.send("\r")
            time.sleep(1)
            child.close(force=True)
        except Exception:
            pass
        fh.close()

    banner("RESULTS")
    for k, v in results.items():
        mark = "PASS" if v else "FAIL"
        print(f"  {mark}  {k}", flush=True)
    return results


if __name__ == "__main__":
    main()
