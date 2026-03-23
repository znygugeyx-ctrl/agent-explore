"""Tool selection strategies for Experiment 003: prefix cache validation.

Four strategies, all static per-task:
- all: baseline, all 50 tools visible every turn
- remove: delete the first 10 irrelevant tools from prompt (breaks prefix)
- logit_mask: all 50 tools visible, 10 irrelevant tools blocked via logit_bias (preserves prefix)
- desc_mask: all 50 tools visible, 10 irrelevant tools marked [UNAVAILABLE] (breaks prefix)
"""

from __future__ import annotations

from typing import Any

from core.tools import AgentTool
from core.types import Context


def select_tools_to_target(
    all_tools: list[AgentTool],
    relevant_tools: list[str],
    n: int = 10,
) -> list[str]:
    """Select the first N irrelevant tools by position to remove/mask.

    Picks from the front of the tool list to maximally disrupt prefix cache.
    """
    targets = []
    for t in all_tools:
        if t.name not in relevant_tools:
            targets.append(t.name)
            if len(targets) >= n:
                break
    return targets


def make_remove_strategy(relevant_tools: list[str], tools_to_remove: list[str]):
    """Remove strategy: delete targeted tools from the prompt."""
    remove_set = set(tools_to_remove) - set(relevant_tools)

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
        return [t for t in all_tools if t.name not in remove_set]

    return strategy


def make_logit_mask_strategy(
    relevant_tools: list[str],
    tools_to_mask: list[str],
    token_map: dict[str, list[int]],
):
    """Logit mask strategy: all tools visible, targeted tools blocked via logit_bias.

    Prompt is UNCHANGED — prefix cache is preserved across tasks.
    """
    logit_bias: dict[str, int] = {}
    for tool_name in tools_to_mask:
        if tool_name not in relevant_tools:
            for tid in token_map.get(tool_name, []):
                logit_bias[str(tid)] = -100

    extra = {"logit_bias": logit_bias} if logit_bias else {}

    def strategy(
        all_tools: list[AgentTool], context: Context
    ) -> tuple[list[AgentTool], dict[str, Any]]:
        return all_tools, extra

    return strategy


def make_desc_mask_strategy(relevant_tools: list[str], tools_to_mask: list[str]):
    """Desc mask strategy: all tools visible, targeted tools marked [UNAVAILABLE].

    Descriptions are modified — prefix changes per task (cache miss expected).
    """
    mask_set = set(tools_to_mask) - set(relevant_tools)
    _cached: list[AgentTool] | None = None

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
        nonlocal _cached
        if _cached is not None:
            return _cached
        result = []
        for t in all_tools:
            if t.name in mask_set:
                masked = AgentTool(
                    name=t.name,
                    description=f"[UNAVAILABLE - do not use this tool] {t.description}",
                    parameters=t.parameters,
                    execute=t.execute,
                )
                result.append(masked)
            else:
                result.append(t)
        _cached = result
        return result

    return strategy


async def collect_tool_tokens(
    base_url: str, model_id: str, tool_names: list[str]
) -> dict[str, list[int]]:
    """Collect token ID variants for each tool name via vLLM /tokenize endpoint."""
    from core.providers.openai_compat import tokenize

    raw_map: dict[str, set[int]] = {name: set() for name in tool_names}

    for name in tool_names:
        variants = [name, f" {name}"]
        for variant in variants:
            try:
                ids = await tokenize(base_url, model_id, variant)
                if ids:
                    raw_map[name].add(ids[0])
            except Exception:
                pass

    # Filter out tokens appearing in 3+ tool names
    token_freq: dict[int, int] = {}
    for tokens in raw_map.values():
        for tid in tokens:
            token_freq[tid] = token_freq.get(tid, 0) + 1

    token_map: dict[str, list[int]] = {}
    for name in tool_names:
        safe = [t for t in raw_map[name] if token_freq[t] < 3]
        token_map[name] = sorted(safe)

    return token_map
