"""Run the logit masking + multi-turn experiment (v2: static per-task strategies).

Usage:
    python -m experiments.002_logit_masking.run [--runs N] [--base-url URL]

Changes from v1:
- Strategies are static per-task (relevant_tools, not step_tools)
- 3 runs execute in parallel via asyncio.gather
- Full message trace saved per task outcome
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.agent import AgentConfig, run_agent
from core.llm import extract_text
from core.types import (
    AssistantMessage,
    Model,
    StreamOptions,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
import core.providers

from .strategies import (
    collect_tool_tokens,
    make_desc_mask_strategy,
    make_logit_mask_strategy,
    make_remove_strategy,
)
from .tools import ALL_TOOLS, TOOL_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"

SYSTEM_PROMPT = """You are a helpful assistant with access to tools. When asked a multi-step question:
1. Use the appropriate tool for EACH step. Do NOT skip steps or compute answers in your head.
2. After getting a tool result, use it as input for the next step if needed.
3. After completing ALL steps, respond with ONLY the final answer value. No explanation needed.
Always use the tools provided - never attempt mental arithmetic or string manipulation."""


@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    relevant_tools: list[str]
    steps: int = 2
    domain: str = ""


@dataclass
class TaskOutcome:
    task_id: str
    strategy: str
    correct: bool = False
    answer: str = ""
    expected: str = ""
    tools_called: list[str] = field(default_factory=list)
    invalid_tool_calls: list[str] = field(default_factory=list)
    steps_completed: int = 0
    latency_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    num_turns: int = 0
    error: str | None = None
    trace: list[dict] = field(default_factory=list)


@dataclass
class StrategyResult:
    strategy: str
    run_id: int
    outcomes: list[TaskOutcome] = field(default_factory=list)
    token_map: dict[str, list[int]] | None = None

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
    def avg_input_tokens(self) -> float:
        vals = [o.input_tokens for o in self.outcomes if o.error is None]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def avg_output_tokens(self) -> float:
        vals = [o.output_tokens for o in self.outcomes if o.error is None]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def total_invalid_tool_calls(self) -> int:
        return sum(len(o.invalid_tool_calls) for o in self.outcomes)

    @property
    def step_completion_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        completed = 0
        for o in self.outcomes:
            task = _task_by_id.get(o.task_id)
            if task and o.steps_completed >= task.steps:
                completed += 1
        return completed / len(self.outcomes)


_task_by_id: dict[str, TaskSpec] = {}


def load_tasks() -> list[TaskSpec]:
    tasks = []
    with open(EXPERIMENT_DIR / "tasks.jsonl") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            task = TaskSpec(
                id=data["id"],
                prompt=data["prompt"],
                expected_answer=data["expected_answer"],
                relevant_tools=data["metadata"]["relevant_tools"],
                steps=data["metadata"].get("steps", 2),
                domain=data["metadata"].get("domain", ""),
            )
            tasks.append(task)
            _task_by_id[task.id] = task
    return tasks


def check_answer(expected: str, actual: str) -> bool:
    import re
    norm_expected = expected.strip().lower()
    norm_actual = actual.strip().lower()
    if norm_expected in norm_actual:
        return True
    try:
        exp_num = float(norm_expected)
        numbers = re.findall(r"-?\d+\.?\d*", norm_actual)
        for n in numbers:
            if abs(float(n) - exp_num) < 0.01:
                return True
    except ValueError:
        pass
    return False


def serialize_messages(messages: list) -> list[dict]:
    """Serialize agent messages to JSON-safe dicts for trace logging."""
    trace = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            trace.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            content_blocks = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    content_blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolCall):
                    content_blocks.append({
                        "type": "tool_call",
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.arguments,
                    })
            trace.append({
                "role": "assistant",
                "content": content_blocks,
                "usage": {"input": msg.usage.input, "output": msg.usage.output},
            })
        elif isinstance(msg, ToolResultMessage):
            trace.append({
                "role": "tool_result",
                "tool_call_id": msg.tool_call_id,
                "tool_name": msg.tool_name,
                "content": [b.text for b in msg.content],
            })
    return trace


async def run_single_task(
    task: TaskSpec,
    model: Model,
    strategy_name: str,
    strategy_fn: Any,
) -> TaskOutcome:
    outcome = TaskOutcome(
        task_id=task.id,
        strategy=strategy_name,
        expected=task.expected_answer,
    )

    config = AgentConfig(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        max_turns=8,
        stream_options=StreamOptions(max_tokens=1024, temperature=0.0),
        tool_selection_strategy=strategy_fn,
    )

    start = time.time()
    try:
        messages = await run_agent(config, task.prompt)
        outcome.latency_seconds = time.time() - start
        outcome.num_turns = sum(1 for m in messages if isinstance(m, AssistantMessage))

        # Save full trace
        outcome.trace = serialize_messages(messages)

        # Aggregate usage
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                outcome.input_tokens += msg.usage.input
                outcome.output_tokens += msg.usage.output
                outcome.total_tokens += msg.usage.total_tokens

        # Track tools called
        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolCall):
                        outcome.tools_called.append(block.name)
                        if block.name not in task.relevant_tools:
                            outcome.invalid_tool_calls.append(block.name)

        # Count completed tool results
        outcome.steps_completed = sum(
            1 for m in messages if isinstance(m, ToolResultMessage)
        )

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


async def run_strategy(
    tasks: list[TaskSpec],
    model: Model,
    strategy_name: str,
    run_id: int,
    token_map: dict[str, list[int]] | None = None,
) -> StrategyResult:
    """Run all tasks with a given strategy (sequentially for cache testing)."""
    result = StrategyResult(strategy=strategy_name, run_id=run_id, token_map=token_map)
    logger.info("=== [Run %d] Strategy: %s ===", run_id, strategy_name)

    for i, task in enumerate(tasks):
        if strategy_name == "all":
            strategy_fn = None
        elif strategy_name == "remove":
            strategy_fn = make_remove_strategy(task.relevant_tools)
        elif strategy_name == "logit_mask":
            assert token_map is not None
            strategy_fn = make_logit_mask_strategy(task.relevant_tools, token_map)
        elif strategy_name == "desc_mask":
            strategy_fn = make_desc_mask_strategy(task.relevant_tools)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        outcome = await run_single_task(task, model, strategy_name, strategy_fn)
        result.outcomes.append(outcome)

        status = "OK" if outcome.correct else "WRONG"
        if outcome.error:
            status = "ERROR"
        logger.info(
            "  [Run%d %d/%d] %s/%s: %s (tools=%s, steps=%d/%d, %.2fs, %d tok)",
            run_id, i + 1, len(tasks), strategy_name, task.id, status,
            ",".join(outcome.tools_called) or "none",
            outcome.steps_completed, task.steps,
            outcome.latency_seconds, outcome.total_tokens,
        )

    logger.info(
        "[Run %d] %s: accuracy=%.1f%%, avg_latency=%.2fs, step_completion=%.1f%%",
        run_id, strategy_name,
        result.accuracy * 100, result.avg_latency, result.step_completion_rate * 100,
    )
    return result


def save_strategy_result(result: StrategyResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "strategy": result.strategy,
        "run_id": result.run_id,
        "accuracy": result.accuracy,
        "avg_latency": result.avg_latency,
        "avg_input_tokens": result.avg_input_tokens,
        "avg_output_tokens": result.avg_output_tokens,
        "step_completion_rate": result.step_completion_rate,
        "total_invalid_tool_calls": result.total_invalid_tool_calls,
        "token_map": result.token_map,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_report(all_results: list[StrategyResult]) -> str:
    lines = ["# Experiment 002 (v2): Static Mask vs Remove — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("Strategy design: per-task static (tool list constant across turns)\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        "| Strategy | Runs | Accuracy | Step Completion | "
        "Avg Latency (s) | Avg Input Tok | Avg Output Tok | Invalid Calls |"
    )
    lines.append(
        "|----------|------|----------|-----------------|"
        "-----------------|---------------|----------------|---------------|"
    )

    strategies: dict[str, list[StrategyResult]] = {}
    for r in all_results:
        strategies.setdefault(r.strategy, []).append(r)

    for name in ["all", "remove", "logit_mask", "desc_mask"]:
        if name not in strategies:
            continue
        runs = strategies[name]
        n = len(runs)
        avg_acc = sum(r.accuracy for r in runs) / n
        avg_step = sum(r.step_completion_rate for r in runs) / n
        avg_lat = sum(r.avg_latency for r in runs) / n
        avg_inp = sum(r.avg_input_tokens for r in runs) / n
        avg_out = sum(r.avg_output_tokens for r in runs) / n
        avg_inv = sum(r.total_invalid_tool_calls for r in runs) / n

        lines.append(
            f"| {name:10s} | {n:4d} | {avg_acc:7.1%} | {avg_step:14.1%} | "
            f"{avg_lat:15.2f} | {avg_inp:13.0f} | {avg_out:14.0f} | {avg_inv:13.1f} |"
        )

    # Per-task breakdown (last run)
    lines.append("\n## Per-Task Results (Last Run)\n")
    lines.append(
        "| Task ID | Strategy | Correct | Tools Called | "
        "Steps | Latency (s) | Tokens |"
    )
    lines.append(
        "|---------|----------|---------|-------------|"
        "-------|-------------|--------|"
    )

    for name in ["all", "remove", "logit_mask", "desc_mask"]:
        if name not in strategies:
            continue
        last_run = strategies[name][-1]
        for o in last_run.outcomes:
            task = _task_by_id.get(o.task_id)
            expected_steps = task.steps if task else "?"
            mark = "Y" if o.correct else "N"
            tools_str = ",".join(o.tools_called) if o.tools_called else "none"
            invalid_mark = " (!)" if o.invalid_tool_calls else ""
            lines.append(
                f"| {o.task_id:26s} | {name:10s} | {mark:7s} | "
                f"{tools_str + invalid_mark:30s} | "
                f"{o.steps_completed:>2d}/{expected_steps} | "
                f"{o.latency_seconds:11.2f} | {o.total_tokens:6d} |"
            )

    # Latency analysis
    lines.append("\n## Latency Analysis\n")
    for name in ["all", "remove", "logit_mask", "desc_mask"]:
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
            lines.append(f"- Min: {all_lats[0]:.3f}s, Max: {all_lats[-1]:.3f}s")
            lines.append("")

    # Token map
    if "logit_mask" in strategies and strategies["logit_mask"][0].token_map:
        lines.append("## Token Map (Logit Mask)\n")
        lines.append("| Tool Name | Token IDs Blocked |")
        lines.append("|-----------|-------------------|")
        for name, ids in sorted(strategies["logit_mask"][0].token_map.items()):
            lines.append(f"| {name} | {ids} |")
        lines.append("")

    errors = [o for r in all_results for o in r.outcomes if o.error]
    if errors:
        lines.append("## Errors\n")
        for o in errors:
            lines.append(f"- **{o.task_id}** ({o.strategy}): {o.error}")

    return "\n".join(lines)


async def run_one_pass(
    run_id: int,
    tasks: list[TaskSpec],
    model: Model,
    strategy_names: list[str],
    token_map: dict[str, list[int]] | None,
) -> list[StrategyResult]:
    """Run all strategies sequentially for one pass (preserves cache ordering)."""
    results = []
    for strategy_name in strategy_names:
        result = await run_strategy(tasks, model, strategy_name, run_id, token_map)
        # Save immediately
        path = RESULTS_DIR / f"{strategy_name}_run{run_id}.json"
        save_strategy_result(result, path)
        logger.info("Saved: %s", path)
        results.append(result)
    return results


async def main():
    parser = argparse.ArgumentParser(description="Run logit masking experiment (v2)")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per strategy")
    parser.add_argument("--base-url", default="http://localhost:8000/v1", help="vLLM base URL")
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B", help="Model ID")
    parser.add_argument(
        "--strategies", nargs="+",
        default=["all", "remove", "logit_mask", "desc_mask"],
        help="Strategies to run",
    )
    args = parser.parse_args()

    model = Model(
        id=args.model_id,
        name="Qwen3-8B",
        provider="openai_compat",
        base_url=args.base_url,
    )

    tasks = load_tasks()
    logger.info("Loaded %d tasks", len(tasks))

    # Collect token map for logit masking
    token_map: dict[str, list[int]] | None = None
    if "logit_mask" in args.strategies:
        logger.info("Collecting token map for logit masking...")
        token_map = await collect_tool_tokens(args.base_url, args.model_id, TOOL_NAMES)
        for name, ids in token_map.items():
            logger.info("  %s: %s", name, ids)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Run all passes in parallel (3 runs concurrently)
    logger.info("Starting %d parallel runs...", args.runs)
    pass_results = await asyncio.gather(*[
        run_one_pass(run_id, tasks, model, args.strategies, token_map)
        for run_id in range(1, args.runs + 1)
    ])

    # Flatten results
    all_results: list[StrategyResult] = []
    for pass_result in pass_results:
        all_results.extend(pass_result)

    # Generate report
    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report_v2.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved: %s", report_path)

    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
