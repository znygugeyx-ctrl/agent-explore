# agent-explore

Experimental framework for validating hypotheses about AI agents.
Modular, minimal, fully transparent - no black-box dependencies.

## Repository Structure

```
core/           Minimal ReAct agent framework
  types.py      Core types: Message, Tool, Context, Model, StreamEvent
  llm.py        LLM provider abstraction + registry
  providers/    Provider implementations (Bedrock, OpenAI-compatible)
  agent.py      ReAct agent loop with hook points
  tools.py      Tool definition, validation, execution
bench/          Benchmark evaluation infrastructure
  types.py      Task, TaskResult, AttemptResult, BenchmarkResult
  runner.py     Parallel evaluation runner
  verifier.py   Answer verification (exact match, LLM judge)
  stats.py      Multi-run statistical aggregation
experiments/    Individual experiment directories
tools/          Reusable tool implementations
configs/        Shared configuration files
```

## Security Rules

- NEVER hardcode API keys, credentials, or secrets in code
- All credentials read from environment variables (boto3 default chain)
- AWS Bedrock: uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
- vLLM/OpenAI-compat: pass base_url and api_key via config, not code

## Quick Start

```bash
pip install -e ".[dev]"

# Run agent with Bedrock Claude
python -c "
import asyncio
from core.agent import AgentConfig, run_agent
from core.types import Model
import core.providers  # registers providers

model = Model(id='us.anthropic.claude-sonnet-4-20250514', name='Sonnet', provider='bedrock')
config = AgentConfig(model=model, system_prompt='You are helpful.', tools=[])
messages = asyncio.run(run_agent(config, 'Hello'))
"

# Run a benchmark
python -c "
import asyncio
from bench.runner import load_tasks, run_benchmark, save_results
from bench.verifier import ExactMatchVerifier
# ... see bench/CLAUDE.md for details
"
```

## Experiment Convention

Each experiment lives in `experiments/<NNN>_<name>/` with:
- `hypothesis.md` - What we're testing and why
- `config.yaml` - All parameters (model, tools, benchmark, etc.)
- `run.py` - Self-contained entry point
- `results/` - Output data (JSON, JSONL)
- Results must be reproducible with the same config

## Code Style

- Python 3.11+, async/await throughout
- Dataclasses for data types, Protocols for interfaces
- Type annotations on all public functions
- Files should be under 200 lines where possible
- No over-engineering: simplest approach that works

## Key Design Decisions

- **Provider registry pattern**: `register_provider()` / `get_provider()` from pi-mono
- **Hook-based extension**: Agent loop uses hooks (before_llm_call, tool_selection_strategy, etc.) for experiments
- **tool_selection_strategy hook**: The primary mechanism for "mask vs remove" experiments
- **Async throughout**: All LLM calls and tool executions are async
- **JSON Schema for tools**: Tool parameters validated with jsonschema

## Dependencies

- `boto3` - AWS Bedrock
- `openai` - OpenAI-compatible APIs (vLLM, etc.)
- `jsonschema` - Tool argument validation
- `pyyaml` - Config loading
