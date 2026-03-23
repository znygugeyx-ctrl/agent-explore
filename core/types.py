"""Core type definitions for agent-explore framework.

Follows pi-mono's type system (types.ts), adapted to Python dataclasses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Union


# -- Stop reason --

StopReason = Literal["stop", "length", "tool_use", "error"]


# -- Content blocks --

@dataclass
class TextContent:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImageContent:
    data: str  # base64 encoded
    mime_type: str
    type: Literal["image"] = "image"


@dataclass
class ThinkingContent:
    thinking: str
    type: Literal["thinking"] = "thinking"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    type: Literal["tool_call"] = "tool_call"


ContentBlock = Union[TextContent, ImageContent, ThinkingContent, ToolCall]


# -- Usage tracking --

@dataclass
class Cost:
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.0


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: Cost = field(default_factory=Cost)
    ttft_seconds: float = 0.0


# -- Messages --

@dataclass
class UserMessage:
    content: str | list[TextContent | ImageContent]
    role: Literal["user"] = "user"
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class AssistantMessage:
    content: list[TextContent | ThinkingContent | ToolCall]
    model: str = ""
    provider: str = ""
    usage: Usage = field(default_factory=Usage)
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    role: Literal["assistant"] = "assistant"
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: list[TextContent | ImageContent]
    is_error: bool = False
    role: Literal["tool_result"] = "tool_result"
    timestamp: float = field(default_factory=lambda: time.time())


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


# -- Tool definition --

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


# -- Model definition --

@dataclass
class ModelCost:
    input: float = 0.0   # $/million tokens
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class Model:
    id: str
    name: str
    provider: str
    context_window: int = 128000
    max_tokens: int = 4096
    base_url: str = ""
    cost: ModelCost = field(default_factory=ModelCost)
    reasoning: bool = False
    input_types: list[str] = field(default_factory=lambda: ["text"])


# -- Context (main input to LLM) --

@dataclass
class Context:
    system_prompt: str | None = None
    messages: list[Message] = field(default_factory=list)
    tools: list[Tool] | None = None


# -- Stream options --

@dataclass
class StreamOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning: str | None = None
    extra: dict[str, Any] | None = None  # Provider-specific params (e.g. logit_bias for vLLM)


# -- Streaming events --

@dataclass
class StartEvent:
    partial: AssistantMessage
    type: Literal["start"] = "start"


@dataclass
class TextDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["text_delta"] = "text_delta"


@dataclass
class ToolCallStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["toolcall_start"] = "toolcall_start"


@dataclass
class ToolCallDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["toolcall_delta"] = "toolcall_delta"


@dataclass
class ToolCallEndEvent:
    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage
    type: Literal["toolcall_end"] = "toolcall_end"


@dataclass
class DoneEvent:
    reason: StopReason
    message: AssistantMessage
    type: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    reason: StopReason
    error: AssistantMessage
    type: Literal["error"] = "error"


StreamEvent = Union[
    StartEvent,
    TextDeltaEvent,
    ToolCallStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    DoneEvent,
    ErrorEvent,
]
