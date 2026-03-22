"""LLM provider abstraction and registry.

Design: Provider registry pattern (from pi-mono api-registry.ts).
Each provider implements the LLMProvider protocol and is registered by name.
Top-level stream() and complete() functions resolve the provider and delegate.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from .types import (
    AssistantMessage,
    Context,
    DoneEvent,
    ErrorEvent,
    Model,
    StreamEvent,
    StreamOptions,
    TextContent,
    ToolCall,
)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers. Implement stream() to add a new provider."""

    @property
    def name(self) -> str: ...

    async def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


# -- Provider registry --

_providers: dict[str, LLMProvider] = {}


def register_provider(provider: LLMProvider) -> None:
    """Register an LLM provider by name."""
    _providers[provider.name] = provider


def get_provider(name: str) -> LLMProvider:
    """Get a registered provider by name. Raises KeyError if not found."""
    if name not in _providers:
        available = ", ".join(_providers.keys()) or "(none)"
        raise KeyError(f'Provider "{name}" not registered. Available: {available}')
    return _providers[name]


def list_providers() -> list[str]:
    """List all registered provider names."""
    return list(_providers.keys())


# -- Top-level API --

async def stream(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream LLM response. Resolves provider from model.provider."""
    provider = get_provider(model.provider)
    async for event in provider.stream(model, context, options):
        yield event


async def complete(
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AssistantMessage:
    """Get a complete LLM response (non-streaming convenience)."""
    result: AssistantMessage | None = None
    async for event in stream(model, context, options):
        if isinstance(event, DoneEvent):
            result = event.message
        elif isinstance(event, ErrorEvent):
            result = event.error
    if result is None:
        raise RuntimeError("Stream ended without done/error event")
    return result


def extract_tool_calls(message: AssistantMessage) -> list[ToolCall]:
    """Extract ToolCall blocks from an assistant message."""
    return [b for b in message.content if isinstance(b, ToolCall)]


def extract_text(message: AssistantMessage) -> str:
    """Extract concatenated text from an assistant message."""
    return "".join(b.text for b in message.content if isinstance(b, TextContent))
