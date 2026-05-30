"""
Filesystem watcher for Claude Code swarm runs.

Polls ~/.claude/teams/{team_name}/ and ~/.claude/tasks/{team_name}/ at a fixed
interval. On every detected change, records a snapshot. Designed to run as a
background thread alongside `claude --print` swarm invocations, capturing
mailbox / task list state before they are cleaned up at team teardown.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

HOME = os.path.expanduser("~")


def _file_signature(path: str) -> tuple[float, int] | None:
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except FileNotFoundError:
        return None


def _walk(root: str) -> list[str]:
    out = []
    if not os.path.isdir(root):
        return out
    for d, _, files in os.walk(root):
        for fn in files:
            out.append(os.path.join(d, fn))
    return out


def _read_safe(path: str) -> str | None:
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


class SwarmFsWatcher:
    """Polls team / tasks directories, emits a JSONL trace of every change."""

    def __init__(self, team_name: str, out_path: str, poll_s: float = 0.5):
        self.team_name = team_name
        self.out_path = out_path
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._team_dir = os.path.join(HOME, ".claude", "teams", team_name)
        self._tasks_dir = os.path.join(HOME, ".claude", "tasks", team_name)
        self._sigs: dict[str, tuple[float, int] | None] = {}

    def start(self):
        os.makedirs(os.path.dirname(self.out_path), exist_ok=True)
        # truncate
        open(self.out_path, "w").close()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 3.0):
        self._stop.set()
        if self._thread:
            # final sweep — capture any last writes before teardown wipes them
            self._sweep(final=True)
            self._thread.join(timeout=join_timeout)

    def _emit(self, event: dict):
        event["t"] = time.time()
        with open(self.out_path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _sweep(self, final: bool = False):
        # candidate file list — both dirs
        seen = set()
        for root in (self._team_dir, self._tasks_dir):
            for path in _walk(root):
                seen.add(path)
                sig = _file_signature(path)
                old = self._sigs.get(path)
                if sig != old:
                    rel = os.path.relpath(path, HOME)
                    content = _read_safe(path)
                    self._emit(
                        {
                            "kind": "file_change",
                            "path": rel,
                            "abs_path": path,
                            "old_sig": old,
                            "new_sig": sig,
                            "content": content,
                            "final": final,
                        }
                    )
                    self._sigs[path] = sig
        # detect deletions
        for path in list(self._sigs.keys()):
            if path not in seen:
                rel = os.path.relpath(path, HOME)
                self._emit(
                    {"kind": "file_deleted", "path": rel, "abs_path": path, "final": final}
                )
                del self._sigs[path]

    def _loop(self):
        # signal readiness
        self._emit(
            {
                "kind": "watcher_start",
                "team": self.team_name,
                "team_dir": self._team_dir,
                "tasks_dir": self._tasks_dir,
                "poll_s": self.poll_s,
            }
        )
        while not self._stop.is_set():
            try:
                self._sweep()
            except Exception as e:
                self._emit({"kind": "watcher_error", "error": repr(e)})
            self._stop.wait(self.poll_s)
        self._emit({"kind": "watcher_stop"})


def load_trace(path: str) -> list[dict]:
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out
