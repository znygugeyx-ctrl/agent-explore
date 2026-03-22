"""Tool definition, validation, and execution."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import jsonschema

from .types import TextContent, Tool, ToolCall, ToolResultMessage


@dataclass
class AgentTool(Tool):
    """A tool with an execute function."""

    execute: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] = None  # type: ignore


class ToolValidationError(Exception):
    """Raised when tool call arguments fail validation."""


def validate_tool_call(tool: Tool, tool_call: ToolCall) -> dict[str, Any]:
    """Validate tool call arguments against the tool's JSON Schema.

    Returns validated arguments. Raises ToolValidationError on failure.
    """
    try:
        jsonschema.validate(instance=tool_call.arguments, schema=tool.parameters)
        return tool_call.arguments
    except jsonschema.ValidationError as e:
        msg = (
            f'Validation failed for tool "{tool_call.name}":\n'
            f"  - {e.json_path}: {e.message}\n\n"
            f"Received arguments:\n{json.dumps(tool_call.arguments, indent=2)}"
        )
        raise ToolValidationError(msg) from e


def find_tool(tools: list[AgentTool], name: str) -> AgentTool | None:
    """Find a tool by name."""
    return next((t for t in tools if t.name == name), None)


async def execute_tool(
    tools: list[AgentTool], tool_call: ToolCall
) -> ToolResultMessage:
    """Validate and execute a single tool call. Returns a ToolResultMessage."""
    tool = find_tool(tools, tool_call.name)
    if tool is None:
        return ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=[TextContent(text=f'Tool "{tool_call.name}" not found')],
            is_error=True,
        )

    try:
        validate_tool_call(tool, tool_call)
    except ToolValidationError as e:
        return ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=[TextContent(text=str(e))],
            is_error=True,
        )

    try:
        result = await tool.execute(tool_call.id, tool_call.arguments)
        text = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        return ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=[TextContent(text=text)],
        )
    except Exception as e:
        return ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=[TextContent(text=f"Tool execution error: {e}")],
            is_error=True,
        )


async def execute_tools_parallel(
    tools: list[AgentTool], tool_calls: list[ToolCall]
) -> list[ToolResultMessage]:
    """Execute multiple tool calls in parallel."""
    tasks = [execute_tool(tools, tc) for tc in tool_calls]
    return list(await asyncio.gather(*tasks))


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable:
    """Decorator to create an AgentTool from an async function.

    Usage:
        @tool(name="calculator", description="...", parameters={...})
        async def calculator(tool_call_id: str, params: dict) -> dict:
            return {"result": ...}
    """

    def decorator(fn: Callable) -> AgentTool:
        return AgentTool(
            name=name,
            description=description,
            parameters=parameters,
            execute=fn,
        )

    return decorator
