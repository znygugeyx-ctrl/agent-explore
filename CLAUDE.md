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
observer/       Standalone context observation service
  server.py     Persistent HTTP server + SSE + JSONL storage
  client.py     Agent-side thin client (fire-and-forget)
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
- RED LINE: NEVER commit any AWS-related keys, access keys, secret keys, session tokens, or credentials in any code, config, script, example, log, or repository file
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

## Context Observer

Real-time web UI for observing agent context windows. Runs as a separate persistent process.

**Start the server (keep running in a dedicated terminal):**
```bash
python -m observer.server          # http://localhost:7777
python -m observer.server --port 8888  # custom port
```

**All experiments MUST attach the observer.** Add this to every `run.py` after creating `AgentConfig`:
```python
from observer.client import attach_observer

attach_observer(config, task_id=task.id, run_id="exp_NNN_name")
```

- `run_id`: identifies the experiment run (e.g. `"exp_005_guided_decoding"`). Auto-generated if omitted.
- `task_id`: identifies the task within a run. Auto-generated if omitted.
- Observer failures never affect the agent — all emits are fire-and-forget.
- Data persists to `observer/data/` as JSONL files, browsable via the web UI after experiments finish.

## Experiment Convention

Each experiment lives in `experiments/<NNN>_<name>/` with:
- `hypothesis.md` - What we're testing and why
- `config.yaml` - All parameters (model, tools, benchmark, etc.)
- `run.py` - Self-contained entry point (must attach observer, see above)
- `results/` - Output data (JSON, JSONL)
- Results must be reproducible with the same config

### Phased Execution

Run experiments in two phases:
1. **Pilot run**: Execute a small subset first (e.g. 5-10 tasks, 1 strategy). Verify tools work, API quotas hold, data format is correct, and results are plausible. Present pilot summary to user before proceeding.
2. **Full run**: Only after pilot is validated, plan and execute the full-scale experiment.

### Resumability

All `run.py` must support断点恢复 (resume from interruption):
- On start, load existing result file and identify completed task IDs
- Only run missing tasks, then merge new outcomes with existing ones preserving task order
- This handles API failures, quota exhaustion, and long-running experiments gracefully

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

## vLLM Inference Endpoint

GPU inference runs on an EC2 g6e.2xlarge (L40S 48GB) with vLLM + Qwen3-8B. Stopped nightly to save cost. See `infra/README.md` for full details.

**Daily lifecycle:** start instance → start vLLM → SSH tunnel → experiment → stop instance

```bash
# Start instance + get new IP
aws ec2 start-instances --instance-ids i-0e3affd7763024652 --region us-east-1
aws ec2 describe-instances --instance-ids i-0e3affd7763024652 --region us-east-1 \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text

# SSH tunnel (makes localhost:8000 → remote vLLM)
ssh -f -N -L 8000:localhost:8000 -i ~/.ssh/vllm-experiment-key.pem ubuntu@<IP>

# Stop instance
aws ec2 stop-instances --instance-ids i-0e3affd7763024652 --region us-east-1
```

**Using in code:** `Model(id="Qwen/Qwen3-8B", provider="openai_compat", base_url="http://localhost:8000/v1")`

**Key capabilities** (documented in `infra/README.md`):
- Tool calling (Hermes parser)
- Logit bias / logit masking via `StreamOptions.extra={"logit_bias": {...}}`
- Prefix cache metrics via `/metrics` endpoint
- Tokenization via `/tokenize` endpoint

## Dependencies

- `boto3` - AWS Bedrock
- `openai` - OpenAI-compatible APIs (vLLM, etc.)
- `jsonschema` - Tool argument validation
- `pyyaml` - Config loading
