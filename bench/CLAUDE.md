# bench - Benchmark Evaluation Infrastructure

## Purpose

Run reproducible benchmark evaluations on agent configurations.
Supports parallel execution, multiple attempts (pass@k), and multi-run statistics.

## Components

- **types.py**: Task, AttemptResult, TaskResult, BenchmarkResult
- **runner.py**: Load tasks, run evaluations, save results
- **verifier.py**: Verify answers (ExactMatch, Contains, LLMJudge)
- **stats.py**: Aggregate multiple runs (mean, std, CI)

## Task Format (JSONL)

```json
{"id": "task_001", "prompt": "What is 2+2?", "expected_answer": "4"}
{"id": "task_002", "prompt": "Capital of France?", "expected_answer": "Paris"}
```

Optional fields: `tools` (list of tool names), `metadata` (dict).

## Running a Benchmark

```python
from bench.runner import load_tasks, run_benchmark, save_results
from bench.verifier import ExactMatchVerifier
from core.agent import AgentConfig
from core.types import Model

tasks = load_tasks("experiments/001/tasks.jsonl")
config = AgentConfig(model=model, system_prompt="...", tools=[...])
result = await run_benchmark(tasks, config, ExactMatchVerifier(), num_attempts=3)
save_results(result, "experiments/001/results/run_1.json")
```

## Adding a Verifier

```python
from bench.verifier import BaseVerifier

class MyVerifier(BaseVerifier):
    async def verify(self, question, expected, predicted, metadata=None):
        # Return (is_correct: bool, reasoning: str)
        return predicted == expected, "exact match"
```

## Multi-Run Aggregation

```python
from bench.stats import aggregate_runs, print_summary
stats = aggregate_runs("experiments/001/results/")
print_summary(stats, "Experiment 001")
```

Output: mean, std, min, max, 95% CI across runs.

## Result Format (JSON)

```json
{
  "name": "benchmark",
  "model": "claude-sonnet-4",
  "overall_score": 0.85,
  "total_tasks": 20,
  "correct_tasks": 17,
  "tasks": [...]
}
```
