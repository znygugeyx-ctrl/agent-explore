"""OpenAI-compatible provider for vLLM, LM Studio, and other OpenAI API servers."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from ..llm import register_provider
from ..types import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
    ImageContent,
    Model,
    StartEvent,
    StreamEvent,
    StreamOptions,
    TextContent,
    TextDeltaEvent,
    ThinkingContent,
    ToolCall,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultMessage,
    Usage,
    UserMessage,
)


def _convert_messages(context: Context) -> list[dict[str, Any]]:
    """Convert our Message list to OpenAI chat format."""
    result: list[dict[str, Any]] = []

    if context.system_prompt:
        result.append({"role": "system", "content": context.system_prompt})

    for msg in context.messages:
        if isinstance(msg, UserMessage):
            if isinstance(msg.content, str):
                result.append({"role": "user", "content": msg.content})
            else:
                parts = []
                for block in msg.content:
                    if isinstance(block, TextContent):
                        parts.append({"type": "text", "text": block.text})
                    elif isinstance(block, ImageContent):
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{block.mime_type};base64,{block.data}"},
                        })
                result.append({"role": "user", "content": parts})

        elif isinstance(msg, AssistantMessage):
            content_text = ""
            tool_calls_list = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    content_text += block.text
                elif isinstance(block, ToolCall):
                    tool_calls_list.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.arguments),
                        },
                    })
            entry: dict[str, Any] = {"role": "assistant"}
            if content_text:
                entry["content"] = content_text
            if tool_calls_list:
                entry["tool_calls"] = tool_calls_list
            result.append(entry)

        elif isinstance(msg, ToolResultMessage):
            text = "".join(b.text for b in msg.content if isinstance(b, TextContent))
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": text,
            })

    return result


def _convert_tools(tools: list[Any] | None) -> list[dict[str, Any]] | None:
    """Convert our Tool list to OpenAI function calling format."""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _map_finish_reason(reason: str | None) -> str:
    """Map OpenAI finish_reason to our StopReason."""
    mapping = {
        "stop": "stop",
        "length": "length",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "stop",
    }
    return mapping.get(reason or "", "stop")


class OpenAICompatProvider:
    """OpenAI-compatible provider for vLLM and other servers."""

    def __init__(self, base_url: str = "", api_key: str = "no-key"):
        self._base_url = base_url
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "openai_compat"

    async def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        options = options or StreamOptions()
        base_url = model.base_url or self._base_url
        if not base_url:
            raise ValueError("base_url required for OpenAI-compatible provider (set on Model or provider)")

        client = AsyncOpenAI(base_url=base_url, api_key=self._api_key)

        output = AssistantMessage(
            content=[],
            model=model.id,
            provider=model.provider,
        )

        # Track streaming tool calls by index
        tool_call_map: dict[int, dict[str, Any]] = {}

        try:
            params: dict[str, Any] = {
                "model": model.id,
                "messages": _convert_messages(context),
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if options.max_tokens:
                params["max_tokens"] = options.max_tokens
            if options.temperature is not None:
                params["temperature"] = options.temperature

            tools = _convert_tools(context.tools)
            if tools:
                params["tools"] = tools

            response = await client.chat.completions.create(**params)

            started = False
            async for chunk in response:
                if not started:
                    yield StartEvent(partial=output)
                    started = True

                choice = chunk.choices[0] if chunk.choices else None
                if choice and choice.delta:
                    delta = choice.delta

                    # Text content
                    if delta.content:
                        # Find or create text block
                        text_idx = None
                        for i, b in enumerate(output.content):
                            if isinstance(b, TextContent):
                                text_idx = i
                                break
                        if text_idx is None:
                            output.content.append(TextContent(text=""))
                            text_idx = len(output.content) - 1

                        output.content[text_idx].text += delta.content
                        yield TextDeltaEvent(
                            content_index=text_idx,
                            delta=delta.content,
                            partial=output,
                        )

                    # Tool calls
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            tc_idx = tc_delta.index
                            if tc_idx not in tool_call_map:
                                # New tool call
                                tc = ToolCall(
                                    id=tc_delta.id or "",
                                    name=tc_delta.function.name or "" if tc_delta.function else "",
                                    arguments={},
                                )
                                output.content.append(tc)
                                our_idx = len(output.content) - 1
                                tool_call_map[tc_idx] = {
                                    "our_index": our_idx,
                                    "partial_args": "",
                                }
                                yield ToolCallStartEvent(
                                    content_index=our_idx, partial=output
                                )

                            info = tool_call_map[tc_idx]
                            block = output.content[info["our_index"]]

                            # Update ID/name if provided
                            if isinstance(block, ToolCall):
                                if tc_delta.id:
                                    block.id = tc_delta.id
                                if tc_delta.function and tc_delta.function.name:
                                    block.name = tc_delta.function.name

                                # Accumulate arguments
                                if tc_delta.function and tc_delta.function.arguments:
                                    arg_chunk = tc_delta.function.arguments
                                    info["partial_args"] += arg_chunk
                                    try:
                                        block.arguments = json.loads(info["partial_args"])
                                    except json.JSONDecodeError:
                                        pass
                                    yield ToolCallDeltaEvent(
                                        content_index=info["our_index"],
                                        delta=arg_chunk,
                                        partial=output,
                                    )

                    if choice.finish_reason:
                        output.stop_reason = _map_finish_reason(choice.finish_reason)

                # Usage info (final chunk)
                if chunk.usage:
                    output.usage.input = chunk.usage.prompt_tokens or 0
                    output.usage.output = chunk.usage.completion_tokens or 0
                    output.usage.total_tokens = chunk.usage.total_tokens or 0

            # Emit tool call end events
            for tc_idx, info in tool_call_map.items():
                block = output.content[info["our_index"]]
                if isinstance(block, ToolCall):
                    try:
                        block.arguments = json.loads(info["partial_args"])
                    except json.JSONDecodeError:
                        block.arguments = {}
                    yield ToolCallEndEvent(
                        content_index=info["our_index"],
                        tool_call=block,
                        partial=output,
                    )

            yield DoneEvent(reason=output.stop_reason, message=output)

        except Exception as e:
            output.stop_reason = "error"
            output.error_message = str(e)
            yield ErrorEvent(reason="error", error=output)


# Auto-register default instance
register_provider(OpenAICompatProvider())
