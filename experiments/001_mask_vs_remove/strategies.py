"""Tool selection strategies for mask vs remove experiment."""

from __future__ import annotations

from core.tools import AgentTool
from core.types import Context


def make_remove_strategy(relevant_tools: list[str]):
    """Remove strategy: only keep relevant tools in the list."""

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
        return [t for t in all_tools if t.name in relevant_tools]

    return strategy


def make_mask_strategy(relevant_tools: list[str]):
    """Mask strategy: keep all tools, mark irrelevant ones as [UNAVAILABLE]."""

    def strategy(all_tools: list[AgentTool], context: Context) -> list[AgentTool]:
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
        return result

    return strategy
