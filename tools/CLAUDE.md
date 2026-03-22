# tools - Reusable Tool Implementations

## Purpose

Shared tool implementations usable across experiments.

## Defining a Tool

```python
from core.tools import tool

@tool(
    name="my_tool",
    description="What this tool does",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
        },
        "required": ["param1"],
    },
)
async def my_tool(tool_call_id: str, params: dict) -> dict:
    return {"result": "..."}
```

## Available Tools

- `calculator` - Safe math expression evaluation

## Conventions

- Tools are async functions returning dicts
- Parameters defined as JSON Schema
- Handle errors gracefully (return error info, don't crash)
- Tools are experimental subjects too - design matters
