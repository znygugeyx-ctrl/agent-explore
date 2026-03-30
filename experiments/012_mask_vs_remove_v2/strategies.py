"""Turn-aware tool selection strategies for Experiment 012 v4.

v4 changes:
  - Removed remove_static (no independent hypothesis)
  - Replaced mask_desc with mask_hint: injects available tool names into user
    message prefix instead of modifying tool descriptions. Tool definitions
    stay completely unchanged → prefix cache preserved.

All strategies share the same interface:
    strategy(all_tools, turn_idx) -> (tools_list, extra_params_dict)

Special extra_params keys:
  "user_message_prefix"  (str) — mask_hint only; run.py prepends this to user_msg
  "logit_bias"           (dict) — mask_logit only; passed to vLLM via StreamOptions.extra
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.tools import AgentTool


TurnStrategy = Any  # (list[AgentTool], int) -> tuple[list[AgentTool], dict]


def make_all_strategy():
    """Baseline: all 60 tools visible every turn, no restriction."""
    def strategy(all_tools: list[AgentTool], turn_idx: int) -> tuple[list[AgentTool], dict]:
        return all_tools, {}
    return strategy


def make_remove_dynamic_strategy(schedule: dict[int, list[str]]):
    """Remove dynamic: per-turn tool list — only this turn's group (5 tools) visible.

    Tool list CHANGES each turn → breaks prefix cache (the key Manus hypothesis target).
    Expected: best accuracy (small choice set), worst TTFT (no cache reuse).
    """
    def strategy(all_tools: list[AgentTool], turn_idx: int) -> tuple[list[AgentTool], dict]:
        available = set(schedule.get(turn_idx, []))
        return [t for t in all_tools if t.name in available], {}
    return strategy


def make_mask_hint_strategy(schedule: dict[int, list[str]]):
    """Hint mask: all 60 tools in context, inject available tool names into user message.

    Tool definitions are UNCHANGED across turns → system+tools prefix cache preserved.
    Each user message is prefixed with which group's tools are available this turn.

    This mirrors real-world MCP-style routing: the router tells the model which
    tools are relevant for this request without altering the tool registry.

    Expected: accuracy close to remove_dynamic, TTFT close to all/mask_logit.
    """
    def strategy(all_tools: list[AgentTool], turn_idx: int) -> tuple[list[AgentTool], dict]:
        available = schedule.get(turn_idx, [])
        hint = f"[Available tools this turn: {', '.join(available)}]\n\n"
        return all_tools, {"user_message_prefix": hint}
    return strategy


def make_mask_logit_strategy(
    schedule: dict[int, list[str]],
    group_token_map: dict[str, int],
):
    """Logit mask (group-level): all 60 tools visible, unavailable GROUPS token-blocked.

    Tool definitions UNCHANGED → prefix cache preserved (same as all/mask_hint).
    Available group's prefix token NEVER enters logit_bias → collision-free.

    Expected: accuracy == remove_dynamic (correct group always unblocked),
              TTFT close to all/mask_hint (stable prompt prefix).
    """
    def strategy(all_tools: list[AgentTool], turn_idx: int) -> tuple[list[AgentTool], dict]:
        available_names = set(schedule.get(turn_idx, []))
        available_groups = {n.split("_")[0] for n in available_names}
        logit_bias = {
            str(tid): -100
            for grp, tid in group_token_map.items()
            if grp not in available_groups
        }
        extra = {"logit_bias": logit_bias} if logit_bias else {}
        return all_tools, extra
    return strategy


def build_strategy(
    name: str,
    schedule: dict[int, list[str]],
    group_token_map: dict[str, int] | None = None,
) -> TurnStrategy:
    """Factory: build a strategy by name given a task's schedule."""
    if name == "all":
        return make_all_strategy()
    if name == "remove_dynamic":
        return make_remove_dynamic_strategy(schedule)
    if name == "mask_hint":
        return make_mask_hint_strategy(schedule)
    if name == "mask_logit":
        if group_token_map is None:
            raise ValueError("mask_logit requires group_token_map")
        return make_mask_logit_strategy(schedule, group_token_map)
    raise ValueError(f"Unknown strategy: {name!r}")


async def collect_group_tokens(
    base_url: str,
    model_id: str,
    tool_names: list[str],
) -> dict[str, int]:
    """Collect one token ID per group prefix via vLLM /tokenize endpoint.

    Returns: {group_prefix: token_id}
    Raises: ValueError if any group has inconsistent first tokens across its tools.
    """
    from core.providers.openai_compat import tokenize

    tool_first_token: dict[str, int] = {}
    for name in tool_names:
        for variant in [name, f" {name}"]:
            try:
                ids = await tokenize(base_url, model_id, variant)
                if ids:
                    tool_first_token[name] = ids[0]
                    break
            except Exception:
                pass

    group_tokens: dict[str, set[int]] = {}
    for name, tid in tool_first_token.items():
        prefix = name.split("_")[0]
        group_tokens.setdefault(prefix, set()).add(tid)

    group_token_map: dict[str, int] = {}
    for prefix, tids in group_tokens.items():
        if len(tids) > 1:
            raise ValueError(
                f"Group '{prefix}' has inconsistent first tokens: {tids}. "
                "Tools in the same group must share the same first token."
            )
        group_token_map[prefix] = next(iter(tids))

    return group_token_map
