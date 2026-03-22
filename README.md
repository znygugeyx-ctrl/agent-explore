# agent-explore

Experimental framework for validating hypotheses about AI agents.

## Structure

- `core/` - Minimal ReAct agent framework (LLM abstraction, tool system, agent loop)
- `bench/` - Benchmark evaluation infrastructure (runner, verifiers, statistics)
- `experiments/` - Individual experiment directories
- `tools/` - Reusable tool implementations

## Setup

```bash
pip install -e ".[dev]"
```

## Quick Test

```python
import asyncio
from core.types import Model, StreamOptions
from core.agent import AgentConfig, run_agent
from tools.calculator import calculator
import core.providers

model = Model(
    id='us.anthropic.claude-sonnet-4-20250514-v1:0',
    name='Claude Sonnet 4',
    provider='bedrock',
)
config = AgentConfig(
    model=model,
    system_prompt='Use the calculator tool for math.',
    tools=[calculator],
    stream_options=StreamOptions(max_tokens=1024),
)
messages = asyncio.run(run_agent(config, 'What is 137 * 456 + 99?'))
```

See `CLAUDE.md` for full documentation.
