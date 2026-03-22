"""AWS Bedrock provider using the Converse Stream API.

Credentials are read from environment variables via boto3's default credential chain
(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION). No keys in code.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

import boto3

from ..llm import register_provider
from ..types import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
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


def _parse_partial_json(s: str) -> dict[str, Any]:
    """Best-effort parse of potentially incomplete JSON."""
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _normalize_tool_call_id(id: str) -> str:
    """Bedrock requires tool call IDs matching [a-zA-Z0-9_-]{1,64}."""
    sanitized = "".join(c if c.isalnum() or c in "_-" else "_" for c in id)
    return sanitized[:64]


def _convert_messages(context: Context) -> list[dict[str, Any]]:
    """Convert our Message list to Bedrock converse format."""
    result: list[dict[str, Any]] = []

    for msg in context.messages:
        if isinstance(msg, UserMessage):
            if isinstance(msg.content, str):
                content = [{"text": msg.content}]
            else:
                content = []
                for block in msg.content:
                    if isinstance(block, TextContent):
                        content.append({"text": block.text})
            result.append({"role": "user", "content": content})

        elif isinstance(msg, AssistantMessage):
            content = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    content.append({"text": block.text})
                elif isinstance(block, ThinkingContent):
                    content.append({
                        "reasoningContent": {"reasoningText": {"text": block.thinking}}
                    })
                elif isinstance(block, ToolCall):
                    content.append({
                        "toolUse": {
                            "toolUseId": _normalize_tool_call_id(block.id),
                            "name": block.name,
                            "input": block.arguments,
                        }
                    })
            if content:
                result.append({"role": "assistant", "content": content})

        elif isinstance(msg, ToolResultMessage):
            # Bedrock requires tool results in a user message
            tool_result = {
                "toolResult": {
                    "toolUseId": _normalize_tool_call_id(msg.tool_call_id),
                    "content": [{"text": b.text} for b in msg.content if isinstance(b, TextContent)],
                    "status": "error" if msg.is_error else "success",
                }
            }
            # Merge consecutive tool results into the same user message
            if result and result[-1]["role"] == "user" and any(
                "toolResult" in c for c in result[-1]["content"]
            ):
                result[-1]["content"].append(tool_result)
            else:
                result.append({"role": "user", "content": [tool_result]})

    return result


def _convert_tools(tools: list[Any] | None) -> dict[str, Any] | None:
    """Convert our Tool list to Bedrock toolConfig format."""
    if not tools:
        return None
    tool_specs = []
    for t in tools:
        spec = {
            "toolSpec": {
                "name": t.name,
                "description": t.description,
                "inputSchema": {"json": t.parameters},
            }
        }
        tool_specs.append(spec)
    return {"tools": tool_specs}


def _map_stop_reason(reason: str | None) -> str:
    """Map Bedrock stop reason to our StopReason."""
    mapping = {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "tool_use": "tool_use",
        "max_tokens": "length",
        "content_filtered": "stop",
    }
    return mapping.get(reason or "", "stop")


class BedrockProvider:
    """AWS Bedrock provider using converse_stream API."""

    @property
    def name(self) -> str:
        return "bedrock"

    async def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        options = options or StreamOptions()

        output = AssistantMessage(
            content=[],
            model=model.id,
            provider=model.provider,
        )

        # Track partial state for streaming tool calls
        block_map: dict[int, dict[str, Any]] = {}  # bedrock_index -> {type, our_index, partial_json}

        try:
            # Build request params
            params: dict[str, Any] = {
                "modelId": model.id,
                "messages": _convert_messages(context),
            }
            if context.system_prompt:
                params["system"] = [{"text": context.system_prompt}]

            inference_config: dict[str, Any] = {}
            if options.max_tokens:
                inference_config["maxTokens"] = options.max_tokens
            if options.temperature is not None:
                inference_config["temperature"] = options.temperature
            if inference_config:
                params["inferenceConfig"] = inference_config

            tool_config = _convert_tools(context.tools)
            if tool_config:
                params["toolConfig"] = tool_config

            # Call Bedrock in a thread (boto3 is synchronous)
            response = await asyncio.to_thread(
                self._call_converse_stream, params
            )

            # Process the stream events
            for item in response:
                if "messageStart" in item:
                    yield StartEvent(partial=output)

                elif "contentBlockStart" in item:
                    event = item["contentBlockStart"]
                    idx = event.get("contentBlockIndex", 0)
                    start = event.get("start", {})

                    if "toolUse" in start:
                        tc = ToolCall(
                            id=start["toolUse"].get("toolUseId", ""),
                            name=start["toolUse"].get("name", ""),
                            arguments={},
                        )
                        output.content.append(tc)
                        our_idx = len(output.content) - 1
                        block_map[idx] = {"type": "tool_call", "our_index": our_idx, "partial_json": ""}
                        yield ToolCallStartEvent(content_index=our_idx, partial=output)

                elif "contentBlockDelta" in item:
                    event = item["contentBlockDelta"]
                    idx = event.get("contentBlockIndex", 0)
                    delta = event.get("delta", {})

                    if "text" in delta:
                        if idx not in block_map:
                            # First text delta - create text block
                            output.content.append(TextContent(text=""))
                            our_idx = len(output.content) - 1
                            block_map[idx] = {"type": "text", "our_index": our_idx}

                        info = block_map[idx]
                        block = output.content[info["our_index"]]
                        if isinstance(block, TextContent):
                            block.text += delta["text"]
                            yield TextDeltaEvent(
                                content_index=info["our_index"],
                                delta=delta["text"],
                                partial=output,
                            )

                    elif "toolUse" in delta and idx in block_map:
                        info = block_map[idx]
                        block = output.content[info["our_index"]]
                        if isinstance(block, ToolCall):
                            input_chunk = delta["toolUse"].get("input", "")
                            info["partial_json"] += input_chunk
                            block.arguments = _parse_partial_json(info["partial_json"])
                            yield ToolCallDeltaEvent(
                                content_index=info["our_index"],
                                delta=input_chunk,
                                partial=output,
                            )

                    elif "reasoningContent" in delta:
                        # Thinking/reasoning content
                        reasoning = delta["reasoningContent"]
                        if idx not in block_map:
                            output.content.append(ThinkingContent(thinking=""))
                            our_idx = len(output.content) - 1
                            block_map[idx] = {"type": "thinking", "our_index": our_idx}

                        info = block_map[idx]
                        block = output.content[info["our_index"]]
                        if isinstance(block, ThinkingContent) and "text" in reasoning:
                            block.thinking += reasoning["text"]

                elif "contentBlockStop" in item:
                    event = item["contentBlockStop"]
                    idx = event.get("contentBlockIndex", 0)
                    if idx in block_map:
                        info = block_map[idx]
                        block = output.content[info["our_index"]]
                        if isinstance(block, ToolCall):
                            block.arguments = _parse_partial_json(info.get("partial_json", ""))
                            yield ToolCallEndEvent(
                                content_index=info["our_index"],
                                tool_call=block,
                                partial=output,
                            )

                elif "messageStop" in item:
                    output.stop_reason = _map_stop_reason(
                        item["messageStop"].get("stopReason")
                    )

                elif "metadata" in item:
                    usage = item["metadata"].get("usage", {})
                    output.usage.input = usage.get("inputTokens", 0)
                    output.usage.output = usage.get("outputTokens", 0)
                    output.usage.cache_read = usage.get("cacheReadInputTokens", 0)
                    output.usage.cache_write = usage.get("cacheWriteInputTokens", 0)
                    output.usage.total_tokens = (
                        usage.get("totalTokens", 0)
                        or output.usage.input + output.usage.output
                    )

            yield DoneEvent(reason=output.stop_reason, message=output)

        except Exception as e:
            output.stop_reason = "error"
            output.error_message = str(e)
            yield ErrorEvent(reason="error", error=output)

    def _call_converse_stream(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Synchronous call to Bedrock converse_stream. Collects stream events."""
        client = boto3.client("bedrock-runtime")
        response = client.converse_stream(**params)
        # Collect all events from the stream
        events = []
        for event in response.get("stream", []):
            events.append(event)
        return events


# Auto-register on import
register_provider(BedrockProvider())
