"""Tool selection strategies for Experiment 002 (v2): static per-task masking.

All strategies receive `relevant_tools: list[str]` — the tools needed for
the ENTIRE task. The tool list is CONSTANT across all turns within a task.

Four strategies:
- all: baseline, all 8 tools visible every turn
- remove: only task-relevant tools visible (remove unneeded ones)
- logit_mask: all tools visible, unneeded tools suppressed via logit_bias
- desc_mask: all tools visible, unneeded tools marked [UNAVAILABLE]
"""

from __future__ import annotations

from typing import Any

from core.tools import AgentTool
from core.types import Context


def make_remove_strategy(relevant_tools: list[str]):
    """Remove strategy: only show tools relevant to this task (static)."""

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
        return [t for t in all_tools if t.name in relevant_tools]

    return strategy


def make_logit_mask_strategy(
    relevant_tools: list[str],
    token_map: dict[str, list[int]],
):
    """Logit mask strategy: all tools visible, unneeded tools blocked via logit_bias (static).

    token_map: {tool_name: [token_id, ...]} - token variants to block.
    Returns (tools, extra_params) tuple.
    """
    # Pre-compute logit_bias once (it's the same every turn)
    logit_bias: dict[str, int] = {}
    for tool_name, token_ids in token_map.items():
        if tool_name not in relevant_tools:
            for tid in token_ids:
                logit_bias[str(tid)] = -100

    extra = {"logit_bias": logit_bias} if logit_bias else {}

    def strategy(
        all_tools: list[AgentTool], context: Context
    ) -> tuple[list[AgentTool], dict[str, Any]]:
        return all_tools, extra

    return strategy


def make_desc_mask_strategy(relevant_tools: list[str]):
    """Description mask strategy: all tools visible, unneeded ones marked [UNAVAILABLE] (static)."""
    # Pre-compute the masked tool list once (it's the same every turn)
    _cached: list[AgentTool] | None = None

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
        nonlocal _cached
        if _cached is not None:
            return _cached
        result = []
        for t in all_tools:
            if t.name in relevant_tools:
                result.append(t)
            else:
                masked = AgentTool(
                    name=t.name,
                    description=f"[UNAVAILABLE - do not use this tool] {t.description}",
                    parameters=t.parameters,
                    execute=t.execute,
                )
                result.append(masked)
        _cached = result
        return result

    return strategy


async def collect_tool_tokens(
    base_url: str, model_id: str, tool_names: list[str]
) -> dict[str, list[int]]:
    """Collect token ID variants for each tool name via vLLM /tokenize endpoint.

    Strategy: collect the first token of each tool name variant (bare,
    space-prefixed). We AVOID quote-prefixed variants because token 1 in Qwen3
    is the double-quote character — blocking it would prevent all JSON generation.

    We also filter out tokens that appear as first token of 3+ different tool
    names (too generic to be useful for blocking a specific tool).
    """
    from core.providers.openai_compat import tokenize

    raw_map: dict[str, set[int]] = {name: set() for name in tool_names}

    for name in tool_names:
        variants = [
            name,            # "calculator"
            f" {name}",      # " calculator" (space prefix common in BPE)
        ]
        for variant in variants:
            try:
                ids = await tokenize(base_url, model_id, variant)
                if ids:
                    raw_map[name].add(ids[0])
            except Exception:
                pass

    # Filter out tokens that appear in 3+ different tool names
    token_frequency: dict[int, int] = {}
    for tokens in raw_map.values():
        for tid in tokens:
            token_frequency[tid] = token_frequency.get(tid, 0) + 1

    token_map: dict[str, list[int]] = {}
    for name in tool_names:
        safe_tokens = [t for t in raw_map[name] if token_frequency[t] < 3]
        token_map[name] = sorted(safe_tokens)

    return token_map
