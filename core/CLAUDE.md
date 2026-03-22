# core - Minimal ReAct Agent Framework

## Purpose

Provides the foundational components for building AI agents:
LLM provider abstraction, tool system, and a ReAct agent loop.

## Architecture

```
types.py  -->  llm.py  -->  providers/  (bedrock, openai_compat)
                  |
types.py  -->  tools.py
                  |
              agent.py  (uses llm.py + tools.py)
```

## Key Interfaces

### LLMProvider (llm.py)
```python
class LLMProvider(Protocol):
    name: str
    async def stream(self, model, context, options) -> AsyncIterator[StreamEvent]
```

### AgentConfig (agent.py)
```python
@dataclass
class AgentConfig:
    model: Model
    system_prompt: str
    tools: list[AgentTool]
    max_turns: int = 20
    # Hook points for experiments:
    tool_selection_strategy: Callable | None  # mask vs remove
    before_llm_call: Callable | None
    after_llm_call: Callable | None
    context_transform: Callable | None
```

### AgentTool (tools.py)
```python
@dataclass
class AgentTool(Tool):
    execute: Callable[[str, dict], Awaitable[dict]]
```

## Adding a New Provider

1. Create `core/providers/my_provider.py`
2. Implement `LLMProvider` protocol (name property + stream method)
3. Call `register_provider(MyProvider())` at module level
4. Import in `core/providers/__init__.py`

## Adding a New Tool

```python
from core.tools import tool

@tool(name="my_tool", description="...", parameters={...})
async def my_tool(tool_call_id: str, params: dict) -> dict:
    return {"result": ...}
```

## Design Principles

- Provider registry pattern from pi-mono: decouple LLM selection from usage
- All providers return the same StreamEvent types
- Agent loop is <200 lines - complex behavior goes in hooks
- Tools are async functions with JSON Schema validation
- Context (system_prompt + messages + tools) is the universal LLM input
- Errors from tools are returned to the LLM (not raised), enabling self-correction
