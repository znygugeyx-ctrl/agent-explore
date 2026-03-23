"""Run the mask vs remove experiment.

Usage:
    python -m experiments.001_mask_vs_remove.run [--runs N] [--base-url URL]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from core.agent import AgentConfig, run_agent
from core.llm import extract_text, extract_tool_calls
from core.types import (
    AssistantMessage,
    Model,
    StreamOptions,
    TextContent,
    ToolCall,
)
import core.providers

from .strategies import make_mask_strategy, make_remove_strategy
from .tools import ALL_TOOLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"

SYSTEM_PROMPT = """You are a helpful assistant with access to tools. When asked a question:
1. Use the appropriate tool to compute the answer.
2. After getting the tool result, respond with ONLY the final answer value. No explanation needed.
Do NOT attempt to compute answers in your head - always use the tools provided."""


@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    relevant_tools: list[str]
    domain: str = ""


@dataclass
class TaskOutcome:
    task_id: str
    strategy: str
    correct: bool = False
    answer: str = ""
    expected: str = ""
    tool_called: str = ""
    tool_args: dict = field(default_factory=dict)
    invalid_tool_call: bool = False
    latency_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    num_turns: int = 0
    error: str | None = None


@dataclass
class StrategyResult:
    strategy: str
    run_id: int
    outcomes: list[TaskOutcome] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for o in self.outcomes if o.correct) / len(self.outcomes)

    @property
    def avg_latency(self) -> float:
        lats = [o.latency_seconds for o in self.outcomes if o.error is None]
        return sum(lats) / len(lats) if lats else 0.0

    @property
    def total_input_tokens(self) -> int:
        return sum(o.input_tokens for o in self.outcomes)

    @property
    def total_output_tokens(self) -> int:
        return sum(o.output_tokens for o in self.outcomes)

    @property
    def invalid_tool_calls(self) -> int:
        return sum(1 for o in self.outcomes if o.invalid_tool_call)


def load_tasks() -> list[TaskSpec]:
    tasks = []
    with open(EXPERIMENT_DIR / "tasks.jsonl") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            tasks.append(TaskSpec(
                id=data["id"],
                prompt=data["prompt"],
                expected_answer=data["expected_answer"],
                relevant_tools=data["metadata"]["relevant_tools"],
                domain=data["metadata"].get("domain", ""),
            ))
    return tasks


def check_answer(expected: str, actual: str) -> bool:
    """Check if actual answer contains the expected answer."""
    norm_expected = expected.strip().lower()
    norm_actual = actual.strip().lower()
    # Direct containment
    if norm_expected in norm_actual:
        return True
    # Try numeric comparison
    try:
        exp_num = float(norm_expected)
        # Find numbers in actual
        import re
        numbers = re.findall(r"-?\d+\.?\d*", norm_actual)
        for n in numbers:
            if abs(float(n) - exp_num) < 0.01:
                return True
    except ValueError:
        pass
    return False


async def run_single_task(
    task: TaskSpec,
    model: Model,
    strategy_name: str,
    strategy_fn,
) -> TaskOutcome:
    """Run a single task and return the outcome."""
    outcome = TaskOutcome(
        task_id=task.id,
        strategy=strategy_name,
        expected=task.expected_answer,
    )

    config = AgentConfig(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        max_turns=5,
        stream_options=StreamOptions(max_tokens=512, temperature=0.0),
        tool_selection_strategy=strategy_fn,
    )

    start = time.time()
    try:
        messages = await run_agent(config, task.prompt)
        outcome.latency_seconds = time.time() - start
        outcome.num_turns = sum(1 for m in messages if isinstance(m, AssistantMessage))

        # Aggregate usage
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                outcome.input_tokens += msg.usage.input
                outcome.output_tokens += msg.usage.output
                outcome.total_tokens += msg.usage.total_tokens

        # Find which tool was called
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolCall):
                        outcome.tool_called = block.name
                        outcome.tool_args = block.arguments
                        # Check if tool was irrelevant
                        if block.name not in task.relevant_tools:
                            outcome.invalid_tool_call = True
                        break

        # Extract final answer
        for msg in reversed(messages):
            if isinstance(msg, AssistantMessage):
                outcome.answer = extract_text(msg)
                break

        outcome.correct = check_answer(task.expected_answer, outcome.answer)

    except Exception as e:
        outcome.latency_seconds = time.time() - start
        outcome.error = str(e)
        logger.error("Task %s failed: %s", task.id, e)

    return outcome


async def fetch_vllm_metrics(base_url: str) -> dict:
    """Fetch prefix cache stats from vLLM metrics endpoint."""
    import urllib.request
    metrics_url = base_url.replace("/v1", "") + "/metrics"
    try:
        with urllib.request.urlopen(metrics_url, timeout=5) as resp:
            text = resp.read().decode()
        stats = {}
        for line in text.split("\n"):
            if line.startswith("vllm:prefix_cache_hit_rate"):
                stats["prefix_cache_hit_rate"] = float(line.split()[-1])
            if line.startswith("vllm:prefix_cache_total_queries_total"):
                stats["prefix_cache_queries"] = float(line.split()[-1])
        return stats
    except Exception as e:
        return {"error": str(e)}


async def run_strategy(
    tasks: list[TaskSpec],
    model: Model,
    strategy_name: str,
    run_id: int,
) -> StrategyResult:
    """Run all tasks with a given strategy (sequentially for cache testing)."""
    result = StrategyResult(strategy=strategy_name, run_id=run_id)
    logger.info("=== Strategy: %s, Run: %d ===", strategy_name, run_id)

    # Fetch pre-run metrics
    pre_metrics = await fetch_vllm_metrics(model.base_url)
    logger.info("Pre-run metrics: %s", pre_metrics)

    for i, task in enumerate(tasks):
        # Build strategy function for this task
        if strategy_name == "all":
            strategy_fn = None
        elif strategy_name == "remove":
            strategy_fn = make_remove_strategy(task.relevant_tools)
        elif strategy_name == "mask":
            strategy_fn = make_mask_strategy(task.relevant_tools)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        outcome = await run_single_task(task, model, strategy_name, strategy_fn)
        result.outcomes.append(outcome)

        status = "OK" if outcome.correct else "WRONG"
        if outcome.error:
            status = "ERROR"
        logger.info(
            "  [%d/%d] %s: %s (tool=%s, %.2fs, %d tokens)",
            i + 1, len(tasks), task.id, status,
            outcome.tool_called, outcome.latency_seconds, outcome.total_tokens,
        )

    # Fetch post-run metrics
    post_metrics = await fetch_vllm_metrics(model.base_url)
    logger.info("Post-run metrics: %s", post_metrics)
    logger.info(
        "Strategy %s Run %d: accuracy=%.1f%%, avg_latency=%.2fs, invalid=%d",
        strategy_name, run_id,
        result.accuracy * 100, result.avg_latency, result.invalid_tool_calls,
    )

    return result


def save_strategy_result(result: StrategyResult, path: Path) -> None:
    """Save a strategy result to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "strategy": result.strategy,
        "run_id": result.run_id,
        "accuracy": result.accuracy,
        "avg_latency": result.avg_latency,
        "total_input_tokens": result.total_input_tokens,
        "total_output_tokens": result.total_output_tokens,
        "invalid_tool_calls": result.invalid_tool_calls,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_report(all_results: list[StrategyResult]) -> str:
    """Generate a markdown comparison report."""
    lines = ["# Experiment 001: Mask vs Remove — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Strategy | Runs | Accuracy | Avg Latency (s) | Avg Input Tokens | Avg Output Tokens | Invalid Calls |")
    lines.append("|----------|------|----------|-----------------|------------------|-------------------|---------------|")

    strategies = {}
    for r in all_results:
        if r.strategy not in strategies:
            strategies[r.strategy] = []
        strategies[r.strategy].append(r)

    for name in ["all", "remove", "mask"]:
        if name not in strategies:
            continue
        runs = strategies[name]
        n = len(runs)
        accs = [r.accuracy for r in runs]
        lats = [r.avg_latency for r in runs]
        inp_tokens = [r.total_input_tokens / len(r.outcomes) for r in runs]
        out_tokens = [r.total_output_tokens / len(r.outcomes) for r in runs]
        invalids = [r.invalid_tool_calls for r in runs]

        avg_acc = sum(accs) / n
        avg_lat = sum(lats) / n
        avg_inp = sum(inp_tokens) / n
        avg_out = sum(out_tokens) / n
        avg_inv = sum(invalids) / n

        lines.append(
            f"| {name:8s} | {n:4d} | {avg_acc:7.1%} | {avg_lat:15.2f} | {avg_inp:16.0f} | {avg_out:17.0f} | {avg_inv:13.1f} |"
        )

    # Per-task breakdown
    lines.append("\n## Per-Task Results (Last Run)\n")
    lines.append("| Task ID | Domain | Strategy | Correct | Tool Called | Latency (s) | Tokens |")
    lines.append("|---------|--------|----------|---------|------------|-------------|--------|")

    for name in ["all", "remove", "mask"]:
        if name not in strategies:
            continue
        last_run = strategies[name][-1]
        for o in last_run.outcomes:
            correct_mark = "Y" if o.correct else "N"
            invalid_mark = " (!)" if o.invalid_tool_call else ""
            lines.append(
                f"| {o.task_id:8s} | {'':<6s} | {name:8s} | {correct_mark:7s} | "
                f"{o.tool_called + invalid_mark:10s} | {o.latency_seconds:11.2f} | {o.total_tokens:6d} |"
            )

    # Latency distribution
    lines.append("\n## Latency Analysis\n")
    for name in ["all", "remove", "mask"]:
        if name not in strategies:
            continue
        all_lats = []
        for r in strategies[name]:
            all_lats.extend(o.latency_seconds for o in r.outcomes if o.error is None)
        if all_lats:
            all_lats.sort()
            n = len(all_lats)
            lines.append(f"### {name}")
            lines.append(f"- Mean: {sum(all_lats)/n:.3f}s")
            lines.append(f"- Median: {all_lats[n//2]:.3f}s")
            lines.append(f"- P90: {all_lats[int(n*0.9)]:.3f}s")
            lines.append(f"- Min: {all_lats[0]:.3f}s")
            lines.append(f"- Max: {all_lats[-1]:.3f}s")
            # First 5 vs last 5 (cache warmup effect)
            first5 = all_lats[:5]
            last5 = all_lats[-5:]
            lines.append(f"- First 5 avg: {sum(first5)/len(first5):.3f}s")
            lines.append(f"- Last 5 avg: {sum(last5)/len(last5):.3f}s")
            lines.append("")

    # Error analysis
    errors = [o for r in all_results for o in r.outcomes if o.error]
    if errors:
        lines.append("## Errors\n")
        for o in errors:
            lines.append(f"- **{o.task_id}** ({o.strategy}): {o.error}")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Run mask vs remove experiment")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per strategy")
    parser.add_argument("--base-url", default="http://localhost:8000/v1", help="vLLM base URL")
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B", help="Model ID")
    args = parser.parse_args()

    model = Model(
        id=args.model_id,
        name="Qwen3-8B",
        provider="openai_compat",
        base_url=args.base_url,
    )

    tasks = load_tasks()
    logger.info("Loaded %d tasks", len(tasks))

    all_results: list[StrategyResult] = []

    for run_id in range(1, args.runs + 1):
        for strategy_name in ["all", "remove", "mask"]:
            result = await run_strategy(tasks, model, strategy_name, run_id)
            all_results.append(result)

            # Save individual result
            path = RESULTS_DIR / f"{strategy_name}_run{run_id}.json"
            save_strategy_result(result, path)
            logger.info("Saved: %s", path)

    # Generate report
    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved: %s", report_path)

    # Print summary to console
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
