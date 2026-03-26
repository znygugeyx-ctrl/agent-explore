"""Minimal ReAct agent loop with hook points for experimentation.

The agent loop is intentionally simple (<200 lines). Complex behaviors
(tool masking, context pruning, rollback) are implemented via hooks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .llm import complete, extract_tool_calls
from .tools import AgentTool, execute_tools_parallel
from .types import (
    AssistantMessage,
    Context,
    Message,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)

from .types import Model, StreamOptions


@dataclass
class AgentConfig:
    """Configuration for the ReAct agent loop.

    Hook points are the primary extension mechanism for experiments.
    For example, tool_selection_strategy can implement "mask vs remove" experiments.
    """

    model: Model
    system_prompt: str
    tools: list[AgentTool]
    max_turns: int = 20
    stream_options: StreamOptions = field(default_factory=StreamOptions)

    # -- Hook points (all optional, for experimentation) --

    # Called before each LLM call. Can modify context (e.g., prune messages).
    before_llm_call: Callable[[Context], Awaitable[Context] | Context] | None = None

    # Called after each LLM response. For logging/analysis.
    after_llm_call: Callable[[AssistantMessage], Awaitable[None] | None] | None = None

    # Controls which tools the LLM sees each turn. KEY experimental variable.
    # Receives (all_tools, current_context), returns tools to present to LLM.
    # "Remove" strategy: filter out irrelevant tools.
    # "Mask" strategy: return all tools but mark some as unavailable in descriptions.
    tool_selection_strategy: (
        Callable[[list[AgentTool], Context], list[AgentTool]] | None
    ) = None

    # Called before each tool execution. Return False to block.
    before_tool_exec: (
        Callable[[ToolCall, AgentTool | None], Awaitable[bool] | bool] | None
    ) = None

    # Called after each tool execution. Can modify the result.
    after_tool_exec: (
        Callable[[ToolCall, ToolResultMessage], Awaitable[ToolResultMessage] | ToolResultMessage]
        | None
    ) = None

    # Transform message history before sending to LLM (e.g., truncation).
    context_transform: (
        Callable[[list[Message]], list[Message]] | None
    ) = None


async def _maybe_await(result: Any) -> Any:
    """Await if coroutine, otherwise return directly."""
    if hasattr(result, "__await__"):
        return await result
    return result


async def _llm_call_with_retry(
    model: Model,
    context: Context,
    options: StreamOptions,
    max_retries: int = 3,
) -> AssistantMessage:
    """Call LLM with retry on provider errors (throttling, transient failures).

    Non-retryable errors (e.g. input too long) return immediately.
    Throttling errors use longer backoff (10s, 30s, 60s).
    """
    import asyncio

    for attempt in range(1, max_retries + 1):
        response = await complete(model, context, options)
        if response.error_message is None:
            return response

        err = response.error_message
        err_lower = err.lower()

        # Input too long = strategy defect (e.g. raw HTML exceeds context window)
        # Not retryable — same input will always fail
        if "too long" in err_lower or "validation" in err_lower:
            logger.warning("Non-retryable LLM error: %s", err)
            return response

        if attempt < max_retries:
            # Throttling needs much longer backoff to let TPM quota recover
            if "throttl" in err_lower or "too many tokens" in err_lower:
                wait = [10, 30, 60][min(attempt - 1, 2)]
            else:
                wait = min(2 ** (attempt + 1), 30)
            logger.warning(
                "LLM error (attempt %d/%d): %s — retrying in %ds",
                attempt, max_retries, err, wait,
            )
            await asyncio.sleep(wait)
        else:
            logger.error("LLM error after %d retries: %s", max_retries, err)
    return response


async def run_agent(
    config: AgentConfig,
    prompt: str | UserMessage,
) -> list[Message]:
    """Run the ReAct agent loop.

    Returns the full message history including all turns.
    """
    # Initialize message history
    if isinstance(prompt, str):
        initial_msg = UserMessage(content=prompt)
    else:
        initial_msg = prompt

    messages: list[Message] = [initial_msg]

    for turn in range(config.max_turns):
        # Build context for this turn
        turn_messages = messages
        if config.context_transform:
            turn_messages = config.context_transform(list(messages))

        # Select tools for this turn
        tools = config.tools
        turn_extra: dict[str, Any] | None = None
        if config.tool_selection_strategy:
            ctx_for_selection = Context(
                system_prompt=config.system_prompt,
                messages=turn_messages,
                tools=[t for t in config.tools],
            )
            result = config.tool_selection_strategy(config.tools, ctx_for_selection)
            # Strategy can return tools or (tools, extra_params) tuple
            if isinstance(result, tuple):
                tools, turn_extra = result
            else:
                tools = result

        # Build LLM context
        context = Context(
            system_prompt=config.system_prompt,
            messages=turn_messages,
            tools=tools if tools else None,
        )

        # Pre-LLM hook
        if config.before_llm_call:
            context = await _maybe_await(config.before_llm_call(context))

        # Merge per-turn extra params into stream options
        turn_options = config.stream_options
        if turn_extra:
            from dataclasses import replace
            merged_extra = {**(turn_options.extra or {}), **turn_extra}
            turn_options = replace(turn_options, extra=merged_extra)

        # LLM call with retry on provider errors
        response = await _llm_call_with_retry(config.model, context, turn_options)
        messages.append(response)

        # Post-LLM hook
        if config.after_llm_call:
            await _maybe_await(config.after_llm_call(response))

        # Extract tool calls
        tool_calls = extract_tool_calls(response)
        if not tool_calls:
            break  # No tools to call - agent is done

        # Execute tools
        results = await execute_tools_parallel(config.tools, tool_calls)

        # Post-tool hooks
        if config.after_tool_exec:
            processed = []
            for tc, result in zip(tool_calls, results):
                result = await _maybe_await(config.after_tool_exec(tc, result))
                processed.append(result)
            results = processed

        messages.extend(results)

        logger.debug(
            "Turn %d: %d tool calls, stop_reason=%s",
            turn + 1,
            len(tool_calls),
            response.stop_reason,
        )

    return messages
