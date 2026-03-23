"""Agent-side client for the observer server.

Usage:
    from observer.client import attach_observer

    attach_observer(config)                      # auto run_id + task_id
    attach_observer(config, task_id="calc_001")  # explicit task_id
    attach_observer(config, run_id="exp_005")    # group into a named run

The observer server must be running separately:
    python -m observer.server

If the server is not running, all emits fail silently — the agent is unaffected.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading
import time
import urllib.request
from typing import Any

from core.agent import AgentConfig
from core.types import (
    AssistantMessage,
    Context,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Auto run_id: date + last 4 digits of PID — unique per process, human-readable
_run_id = time.strftime("%Y-%m-%d") + f"_{os.getpid() % 10000:04d}"

_task_counter = 0
_task_lock = threading.Lock()

_server_url = "http://localhost:7777"


def set_server_url(url: str) -> None:
    global _server_url
    _server_url = url


def _next_task_id() -> str:
    global _task_counter
    with _task_lock:
        _task_counter += 1
        return f"Task {_task_counter}"


# ---------------------------------------------------------------------------
# Serialization — mirrors exactly what is sent to the model
# ---------------------------------------------------------------------------

def _ser_content(block: Any) -> dict:
    if isinstance(block, TextContent):
        return {"type": "text", "text": block.text}
    if isinstance(block, ThinkingContent):
        return {"type": "thinking", "thinking": block.thinking}
    if isinstance(block, ToolCall):
        return {"type": "tool_call", "id": block.id, "name": block.name, "arguments": block.arguments}
    if isinstance(block, ImageContent):
        return {"type": "image", "mime_type": block.mime_type, "data": "[image data omitted]"}
    return {"type": "unknown", "raw": str(block)}


def _ser_message(msg: Any) -> dict:
    if isinstance(msg, UserMessage):
        content = msg.content if isinstance(msg.content, str) else [_ser_content(c) for c in msg.content]
        return {"role": "user", "content": content}
    if isinstance(msg, AssistantMessage):
        return {"role": "assistant", "content": [_ser_content(c) for c in msg.content]}
    if isinstance(msg, ToolResultMessage):
        return {
            "role": "tool_result",
            "tool_call_id": msg.tool_call_id,
            "tool_name": msg.tool_name,
            "content": [_ser_content(c) for c in msg.content],
            "is_error": msg.is_error,
        }
    return {"role": "unknown", "content": str(msg)}


def _ser_tool(t: Any) -> dict:
    return {"name": t.name, "description": t.description, "parameters": t.parameters}


def _ser_usage(u: Any) -> dict:
    return {
        "input": u.input,
        "output": u.output,
        "cache_read": u.cache_read,
        "cache_write": u.cache_write,
        "ttft_seconds": u.ttft_seconds,
        "cost_total": u.cost.total,
    }


# ---------------------------------------------------------------------------
# Fire-and-forget HTTP POST
# ---------------------------------------------------------------------------

def _sync_post(data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(
        _server_url + "/api/events",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=2)


async def _async_post(data: dict) -> None:
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _sync_post, data)
    except Exception:
        pass  # server down → silent


def _emit(data: dict) -> None:
    """Schedule a fire-and-forget POST. Never raises, never blocks the agent."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_post(data))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Hook chaining helper
# ---------------------------------------------------------------------------

async def _call(fn, *args):
    if fn is None:
        return args[0] if args else None
    result = fn(*args)
    if inspect.isawaitable(result):
        result = await result
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def attach_observer(
    config: AgentConfig,
    task_id: str | None = None,
    run_id: str | None = None,
    server_url: str | None = None,
) -> str:
    """Attach context observer to an AgentConfig.

    Chains into existing before_llm_call / after_llm_call / after_tool_exec hooks.
    Returns the task_id used.
    """
    if server_url:
        set_server_url(server_url)

    used_task_id = task_id or _next_task_id()
    used_run_id = run_id or _run_id

    turn_counter = [0]
    orig_before = config.before_llm_call
    orig_after = config.after_llm_call
    orig_tool = config.after_tool_exec

    async def _before(ctx: Context) -> Context:
        # Always run original hook first — we emit the final context the model actually sees
        if orig_before:
            ctx = await _call(orig_before, ctx)
        turn_counter[0] += 1
        try:
            _emit({
                "ts": time.time(),
                "run_id": used_run_id,
                "task_id": used_task_id,
                "type": "context",
                "turn": turn_counter[0],
                "data": {
                    "system_prompt": ctx.system_prompt,
                    "messages": [_ser_message(m) for m in ctx.messages],
                    "tools": [_ser_tool(t) for t in (ctx.tools or [])],
                    "tool_count": len(ctx.tools) if ctx.tools else 0,
                },
            })
        except Exception:
            pass
        return ctx

    async def _after(resp: AssistantMessage) -> None:
        try:
            _emit({
                "ts": time.time(),
                "run_id": used_run_id,
                "task_id": used_task_id,
                "type": "response",
                "turn": turn_counter[0],
                "data": {
                    "content": [_ser_content(c) for c in resp.content],
                    "usage": _ser_usage(resp.usage),
                    "stop_reason": resp.stop_reason,
                    "model": resp.model,
                },
            })
        except Exception:
            pass
        if orig_after:
            await _call(orig_after, resp)

    async def _tool(tc: ToolCall, result: ToolResultMessage) -> ToolResultMessage:
        if orig_tool:
            result = await _call(orig_tool, tc, result)
        try:
            _emit({
                "ts": time.time(),
                "run_id": used_run_id,
                "task_id": used_task_id,
                "type": "tool_result",
                "turn": turn_counter[0],
                "data": {
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                    "result": [_ser_content(c) for c in result.content],
                    "is_error": result.is_error,
                },
            })
        except Exception:
            pass
        return result

    config.before_llm_call = _before
    config.after_llm_call = _after
    config.after_tool_exec = _tool
    return used_task_id
