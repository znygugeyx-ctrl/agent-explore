"""Run the prefix cache validation experiment (v3).

Usage:
    python -m experiments.003_prefix_cache.run [--runs N] [--base-url URL]

Key differences from Experiment 002:
- 50 tools (vs 8): tool definitions dominate the prompt prefix
- TTFT (time to first token) measured per turn
- vLLM prefix cache metrics collected per strategy
- 4-6 step tasks for longer conversations
- Remove/Mask target the first 10 irrelevant tools (by position)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
import urllib.request
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
    select_tools_to_target,
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

N_TOOLS_TO_TARGET = 10  # Number of tools to remove/mask per task


@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    relevant_tools: list[str]
    steps: int = 4
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
    ttft_per_turn: list[float] = field(default_factory=list)
    avg_ttft: float = 0.0
    error: str | None = None
    trace: list[dict] = field(default_factory=list)


@dataclass
class CacheMetrics:
    queries: int = 0
    hits: int = 0
    hit_rate: float = 0.0


@dataclass
class StrategyResult:
    strategy: str
    run_id: int
    outcomes: list[TaskOutcome] = field(default_factory=list)
    token_map: dict[str, list[int]] | None = None
    cache_before: CacheMetrics = field(default_factory=CacheMetrics)
    cache_after: CacheMetrics = field(default_factory=CacheMetrics)

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
    def avg_ttft(self) -> float:
        all_ttfts = []
        for o in self.outcomes:
            if o.error is None:
                all_ttfts.extend(o.ttft_per_turn)
        return sum(all_ttfts) / len(all_ttfts) if all_ttfts else 0.0

    @property
    def cache_delta_queries(self) -> int:
        return self.cache_after.queries - self.cache_before.queries

    @property
    def cache_delta_hits(self) -> int:
        return self.cache_after.hits - self.cache_before.hits

    @property
    def cache_hit_rate(self) -> float:
        dq = self.cache_delta_queries
        return self.cache_delta_hits / dq if dq > 0 else 0.0

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
                steps=data["metadata"].get("steps", 4),
                domain=data["metadata"].get("domain", ""),
            )
            tasks.append(task)
            _task_by_id[task.id] = task
    return tasks


def check_answer(expected: str, actual: str) -> bool:
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
                        "type": "tool_call", "id": block.id,
                        "name": block.name, "arguments": block.arguments,
                    })
            trace.append({
                "role": "assistant", "content": content_blocks,
                "usage": {"input": msg.usage.input, "output": msg.usage.output},
                "ttft": msg.usage.ttft_seconds,
            })
        elif isinstance(msg, ToolResultMessage):
            trace.append({
                "role": "tool_result", "tool_call_id": msg.tool_call_id,
                "tool_name": msg.tool_name,
                "content": [b.text for b in msg.content],
            })
    return trace


async def get_cache_metrics(base_url: str) -> CacheMetrics:
    """Query vLLM /metrics endpoint for prefix cache stats."""
    # Strip /v1 suffix to get base server URL
    server_url = base_url.rstrip("/")
    if server_url.endswith("/v1"):
        server_url = server_url[:-3]
    metrics_url = f"{server_url}/metrics"

    def _fetch():
        req = urllib.request.Request(metrics_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode()

    try:
        text = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        queries = 0
        hits = 0
        for line in text.split("\n"):
            if line.startswith("vllm:prefix_cache_queries_total{"):
                queries = int(float(line.split()[-1]))
            elif line.startswith("vllm:prefix_cache_hits_total{"):
                hits = int(float(line.split()[-1]))
        hit_rate = hits / queries if queries > 0 else 0.0
        return CacheMetrics(queries=queries, hits=hits, hit_rate=hit_rate)
    except Exception as e:
        logger.warning("Failed to get cache metrics: %s", e)
        return CacheMetrics()


async def run_single_task(
    task: TaskSpec,
    model: Model,
    strategy_name: str,
    strategy_fn: Any,
) -> TaskOutcome:
    outcome = TaskOutcome(
        task_id=task.id, strategy=strategy_name, expected=task.expected_answer,
    )

    config = AgentConfig(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        max_turns=10,
        stream_options=StreamOptions(max_tokens=1024, temperature=0.0),
        tool_selection_strategy=strategy_fn,
    )

    start = time.time()
    try:
        messages = await run_agent(config, task.prompt)
        outcome.latency_seconds = time.time() - start
        outcome.num_turns = sum(1 for m in messages if isinstance(m, AssistantMessage))
        outcome.trace = serialize_messages(messages)

        for msg in messages:
            if isinstance(msg, AssistantMessage):
                outcome.input_tokens += msg.usage.input
                outcome.output_tokens += msg.usage.output
                outcome.total_tokens += msg.usage.total_tokens
                if msg.usage.ttft_seconds > 0:
                    outcome.ttft_per_turn.append(msg.usage.ttft_seconds)

        if outcome.ttft_per_turn:
            outcome.avg_ttft = sum(outcome.ttft_per_turn) / len(outcome.ttft_per_turn)

        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolCall):
                        outcome.tools_called.append(block.name)
                        if block.name not in task.relevant_tools:
                            outcome.invalid_tool_calls.append(block.name)

        outcome.steps_completed = sum(
            1 for m in messages if isinstance(m, ToolResultMessage)
        )

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
    base_url: str = "http://localhost:8000/v1",
) -> StrategyResult:
    result = StrategyResult(strategy=strategy_name, run_id=run_id, token_map=token_map)

    # Capture cache metrics before
    result.cache_before = await get_cache_metrics(base_url)
    logger.info("=== [Run %d] Strategy: %s (cache queries=%d, hits=%d) ===",
                run_id, strategy_name, result.cache_before.queries, result.cache_before.hits)

    for i, task in enumerate(tasks):
        # Build per-task strategy
        if strategy_name == "all":
            strategy_fn = None
        else:
            targets = select_tools_to_target(ALL_TOOLS, task.relevant_tools, N_TOOLS_TO_TARGET)
            if strategy_name == "remove":
                strategy_fn = make_remove_strategy(task.relevant_tools, targets)
            elif strategy_name == "logit_mask":
                assert token_map is not None
                strategy_fn = make_logit_mask_strategy(task.relevant_tools, targets, token_map)
            elif strategy_name == "desc_mask":
                strategy_fn = make_desc_mask_strategy(task.relevant_tools, targets)
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")

        outcome = await run_single_task(task, model, strategy_name, strategy_fn)
        result.outcomes.append(outcome)

        status = "OK" if outcome.correct else "WRONG"
        if outcome.error:
            status = "ERROR"
        logger.info(
            "  [Run%d %d/%d] %s/%s: %s (tools=%s, steps=%d/%d, %.2fs, ttft=%.3fs)",
            run_id, i + 1, len(tasks), strategy_name, task.id, status,
            ",".join(outcome.tools_called[:6]) or "none",
            outcome.steps_completed, task.steps,
            outcome.latency_seconds, outcome.avg_ttft,
        )

    # Capture cache metrics after
    result.cache_after = await get_cache_metrics(base_url)
    dq = result.cache_delta_queries
    dh = result.cache_delta_hits
    logger.info(
        "[Run %d] %s: acc=%.1f%%, lat=%.2fs, ttft=%.3fs, cache=%d/%d (%.1f%%)",
        run_id, strategy_name, result.accuracy * 100, result.avg_latency,
        result.avg_ttft, dh, dq, result.cache_hit_rate * 100,
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
        "avg_ttft": result.avg_ttft,
        "step_completion_rate": result.step_completion_rate,
        "cache_hit_rate": result.cache_hit_rate,
        "cache_delta_queries": result.cache_delta_queries,
        "cache_delta_hits": result.cache_delta_hits,
        "token_map": result.token_map,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_report(all_results: list[StrategyResult]) -> str:
    lines = ["# Experiment 003 (v3): Prefix Cache Validation — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"50 tools, {N_TOOLS_TO_TARGET} tools removed/masked per task\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        "| Strategy | Runs | Accuracy | Avg Latency | Avg TTFT | "
        "Cache Hit Rate | Avg Input Tok | Avg Output Tok |"
    )
    lines.append(
        "|----------|------|----------|-------------|----------|"
        "----------------|---------------|----------------|"
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
        avg_lat = sum(r.avg_latency for r in runs) / n
        avg_ttft = sum(r.avg_ttft for r in runs) / n
        avg_cache = sum(r.cache_hit_rate for r in runs) / n
        avg_inp = sum(r.avg_input_tokens for r in runs) / n
        avg_out = sum(r.avg_output_tokens for r in runs) / n

        lines.append(
            f"| {name:10s} | {n:4d} | {avg_acc:7.1%} | {avg_lat:11.2f}s | "
            f"{avg_ttft:7.3f}s | {avg_cache:13.1%} | {avg_inp:13.0f} | {avg_out:14.0f} |"
        )

    # TTFT Analysis
    lines.append("\n## TTFT Analysis (Time to First Token)\n")
    for name in ["all", "remove", "logit_mask", "desc_mask"]:
        if name not in strategies:
            continue
        all_ttfts = []
        for r in strategies[name]:
            for o in r.outcomes:
                if o.error is None:
                    all_ttfts.extend(o.ttft_per_turn)
        if all_ttfts:
            all_ttfts.sort()
            n = len(all_ttfts)
            lines.append(f"### {name}")
            lines.append(f"- Mean: {sum(all_ttfts)/n:.3f}s")
            lines.append(f"- Median: {all_ttfts[n//2]:.3f}s")
            lines.append(f"- P90: {all_ttfts[int(n*0.9)]:.3f}s")
            lines.append(f"- Min: {all_ttfts[0]:.3f}s, Max: {all_ttfts[-1]:.3f}s")
            lines.append(f"- Count: {n} turns")
            lines.append("")

    # Cache metrics
    lines.append("## Prefix Cache Metrics\n")
    lines.append("| Strategy | Run | Queries (delta) | Hits (delta) | Hit Rate |")
    lines.append("|----------|-----|-----------------|--------------|----------|")
    for name in ["all", "remove", "logit_mask", "desc_mask"]:
        if name not in strategies:
            continue
        for r in strategies[name]:
            lines.append(
                f"| {name:10s} | {r.run_id:3d} | {r.cache_delta_queries:15,d} | "
                f"{r.cache_delta_hits:12,d} | {r.cache_hit_rate:7.1%} |"
            )

    # Per-task breakdown (last run)
    lines.append("\n## Per-Task Results (Last Run)\n")
    lines.append(
        "| Task ID | Strategy | Correct | Steps | "
        "Latency | Avg TTFT | Tokens |"
    )
    lines.append(
        "|---------|----------|---------|-------|"
        "---------|----------|--------|"
    )
    for name in ["all", "remove", "logit_mask", "desc_mask"]:
        if name not in strategies:
            continue
        last_run = strategies[name][-1]
        for o in last_run.outcomes:
            task = _task_by_id.get(o.task_id)
            expected_steps = task.steps if task else "?"
            mark = "Y" if o.correct else "N"
            lines.append(
                f"| {o.task_id:35s} | {name:10s} | {mark:7s} | "
                f"{o.steps_completed:>2d}/{expected_steps} | "
                f"{o.latency_seconds:7.2f}s | {o.avg_ttft:7.3f}s | {o.total_tokens:6d} |"
            )

    # Token map
    if "logit_mask" in strategies and strategies["logit_mask"][0].token_map:
        lines.append("\n## Token Map (Logit Mask — first 10 tools)\n")
        lines.append("| Tool Name | Token IDs Blocked |")
        lines.append("|-----------|-------------------|")
        tm = strategies["logit_mask"][0].token_map
        for name in list(tm.keys())[:10]:
            lines.append(f"| {name} | {tm[name]} |")

    return "\n".join(lines)


async def run_one_pass(
    run_id: int,
    tasks: list[TaskSpec],
    model: Model,
    strategy_names: list[str],
    token_map: dict[str, list[int]] | None,
    base_url: str,
) -> list[StrategyResult]:
    results = []
    for strategy_name in strategy_names:
        result = await run_strategy(
            tasks, model, strategy_name, run_id, token_map, base_url
        )
        path = RESULTS_DIR / f"{strategy_name}_run{run_id}.json"
        save_strategy_result(result, path)
        logger.info("Saved: %s", path)
        results.append(result)
    return results


async def main():
    parser = argparse.ArgumentParser(description="Run prefix cache experiment (v3)")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument(
        "--strategies", nargs="+",
        default=["all", "remove", "logit_mask", "desc_mask"],
    )
    args = parser.parse_args()

    model = Model(
        id=args.model_id, name="Qwen3-8B",
        provider="openai_compat", base_url=args.base_url,
    )

    tasks = load_tasks()
    logger.info("Loaded %d tasks, %d tools", len(tasks), len(ALL_TOOLS))

    token_map: dict[str, list[int]] | None = None
    if "logit_mask" in args.strategies:
        logger.info("Collecting token map for logit masking...")
        token_map = await collect_tool_tokens(args.base_url, args.model_id, TOOL_NAMES)
        for name, ids in list(token_map.items())[:10]:
            logger.info("  %s: %s", name, ids)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Starting %d parallel runs...", args.runs)
    pass_results = await asyncio.gather(*[
        run_one_pass(run_id, tasks, model, args.strategies, token_map, args.base_url)
        for run_id in range(1, args.runs + 1)
    ])

    all_results: list[StrategyResult] = []
    for pass_result in pass_results:
        all_results.extend(pass_result)

    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report_v3.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved: %s", report_path)

    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
