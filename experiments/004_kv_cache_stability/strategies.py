"""Context stability strategies for Experiment 004: KV Cache Stability.

Three strategies testing the Manus claims about prefix cache stability:

- stable:       No hooks — static system prompt, messages appended normally (control).
                The agent's default behavior IS the stable baseline. Cache should warm
                up across sequential tasks.

- timestamp_s:  before_llm_call injects a second-precision wall-clock timestamp at the
                START of the system prompt. Changes every second, so virtually every LLM
                call sees a different prefix → full prefix cache miss.

- truncate:     context_transform keeps only the last N assistant-step groups from the
                message history. Breaks the append-only invariant: turn 3's prefix is NOT
                a superset of turn 2's prefix → cache miss at every truncation event.
"""

from __future__ import annotations

import time
from typing import Callable

from core.types import AssistantMessage, Context, Message


# ---------------------------------------------------------------------------
# Strategy 1: stable (control) — no hooks
# ---------------------------------------------------------------------------

def make_stable_hooks() -> dict:
    """Return hook dict for the stable (control) strategy.

    No hooks needed. Stable prefix + append-only messages = maximum cache reuse.
    """
    return {"before_llm_call": None, "context_transform": None}


# ---------------------------------------------------------------------------
# Strategy 2: timestamp_s — second-precision timestamp invalidates prefix
# ---------------------------------------------------------------------------

def make_timestamp_s_hooks(base_system_prompt: str) -> dict:
    """Return hooks for the timestamp_s strategy.

    Prepends a second-precision timestamp to the system prompt:
        [Current time: 2026-03-22 14:05:37]

    The timestamp is at position 0, so ALL subsequent tokens (50 tool definitions,
    instructions) are invalidated in the KV cache whenever the second ticks over.
    During a multi-turn task (5-20 seconds), the second changes between turns,
    making cache miss rate approach 100%.
    """
    def before_llm_call(context: Context) -> Context:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        stamped_prompt = f"[Current time: {ts}]\n\n{base_system_prompt}"
        return Context(
            system_prompt=stamped_prompt,
            messages=context.messages,
            tools=context.tools,
        )

    return {"before_llm_call": before_llm_call, "context_transform": None}


# ---------------------------------------------------------------------------
# Strategy 3: truncate — break append-only by dropping early step groups
# ---------------------------------------------------------------------------

def _split_into_step_groups(
    messages: list[Message],
) -> tuple[list[Message], list[list[Message]]]:
    """Split message list into (anchor, step_groups).

    The anchor is the first message (UserMessage with task prompt) — always kept.
    Each step group is [AssistantMessage, ToolResultMessage*, ...].

    In the ReAct loop:
        UserMessage(task)              ← anchor
        AssistantMessage(tool_call_1)  ← step group 0
        ToolResultMessage(result_1)    ← step group 0 (continued)
        AssistantMessage(tool_call_2)  ← step group 1
        ToolResultMessage(result_2)    ← step group 1 (continued)
        AssistantMessage(final_answer) ← step group N (no tool results)
    """
    if not messages:
        return [], []

    anchor = [messages[0]]
    step_groups: list[list[Message]] = []
    current: list[Message] = []

    for msg in messages[1:]:
        if isinstance(msg, AssistantMessage) and current:
            step_groups.append(current)
            current = [msg]
        else:
            current.append(msg)

    if current:
        step_groups.append(current)

    return anchor, step_groups


def make_truncate_hooks(keep_last_n: int = 2) -> dict:
    """Return hooks for the truncate strategy.

    Keeps the task anchor (first UserMessage) plus the last `keep_last_n` step groups.

    With keep_last_n=2 on a 4-step task:
      Before turn 1: [User, Asst1]                            → unchanged (1 group)
      Before turn 2: [User, Asst1, TR1, Asst2]                → unchanged (2 groups)
      Before turn 3: [User, Asst1, TR1, Asst2, TR2, Asst3]    → [User, Asst2, TR2, Asst3]
      Before turn 4: [User, Asst2, TR2, Asst3, TR3, Asst4]    → [User, Asst3, TR3, Asst4]

    At turn 3+, the message history is NOT a prefix-extension of the prior turn's
    history → prefix cache miss at every truncation event.
    """
    def context_transform(messages: list[Message]) -> list[Message]:
        anchor, step_groups = _split_into_step_groups(messages)
        if len(step_groups) <= keep_last_n:
            return messages  # No truncation needed yet
        kept = step_groups[-keep_last_n:]
        result: list[Message] = list(anchor)
        for group in kept:
            result.extend(group)
        return result

    return {"before_llm_call": None, "context_transform": context_transform}


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGY_NAMES = ["stable", "timestamp_s", "truncate"]


def build_strategy_hooks(
    strategy_name: str,
    base_system_prompt: str,
    truncate_keep_n: int = 2,
) -> dict:
    """Build the hook dict for a given strategy name.

    Returns:
        {"before_llm_call": Callable | None, "context_transform": Callable | None}
    """
    if strategy_name == "stable":
        return make_stable_hooks()
    elif strategy_name == "timestamp_s":
        return make_timestamp_s_hooks(base_system_prompt)
    elif strategy_name == "truncate":
        return make_truncate_hooks(keep_last_n=truncate_keep_n)
    else:
        raise ValueError(f"Unknown strategy: {strategy_name!r}. Valid: {STRATEGY_NAMES}")
