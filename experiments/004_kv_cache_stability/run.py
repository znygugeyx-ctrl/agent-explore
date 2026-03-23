"""Run the KV cache stability experiment (004).

Usage:
    python -m experiments.004_kv_cache_stability.run [--runs N] [--base-url URL]

Tests the Manus "Design Around KV Cache" claims:
- stable:      static system prompt + append-only → TTFT decreases (cache warms up)
- timestamp_s: second-precision timestamp in prompt → TTFT flat/high (cache miss every turn)
- truncate:    drop old messages → TTFT spikes at truncation events

Key differences from Experiment 003:
- Context stability is the variable; all 50 tools are always shown (no tool selection)
- Uses before_llm_call (timestamp_s) and context_transform (truncate) hooks
- Tasks run SEQUENTIALLY within each strategy run — enables cross-task cache warmup
- Strategies run sequentially (one at a time) for clean cache state isolation
- Temperature 0.0 for determinism; reduces TTFT variance from output length
- Primary metric: TTFT by turn number, aggregated across tasks
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import re
import sys
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
import core.providers  # noqa: F401 — registers providers

from .strategies import build_strategy_hooks, STRATEGY_NAMES

# ---------------------------------------------------------------------------
# Import tools from experiment 003 via importlib.
# Direct import fails because "003_prefix_cache" starts with a digit.
# ---------------------------------------------------------------------------
_EXP003_DIR = Path(__file__).parent.parent / "003_prefix_cache"


def _load_module(module_name: str, file_path: Path) -> Any:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_tools_mod = _load_module("exp003_tools", _EXP003_DIR / "tools.py")
ALL_TOOLS = _tools_mod.ALL_TOOLS

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
TASKS_FILE = _EXP003_DIR / "tasks.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful assistant with access to tools. When asked a multi-step question:
1. Use the appropriate tool for EACH step. Do NOT skip steps or compute answers in your head.
2. After getting a tool result, use it as input for the next step if needed.
3. After completing ALL steps, respond with ONLY the final answer value. No explanation needed.
Always use the tools provided - never attempt mental arithmetic or string manipulation."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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
    steps_completed: int = 0
    latency_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    num_turns: int = 0
    ttft_per_turn: list[float] = field(default_factory=list)
    input_tokens_per_turn: list[int] = field(default_factory=list)
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


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

_task_by_id: dict[str, TaskSpec] = {}


def load_tasks() -> list[TaskSpec]:
    tasks = []
    with open(TASKS_FILE) as f:
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


# ---------------------------------------------------------------------------
# Helpers (identical to 003)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Core: run a single task
# ---------------------------------------------------------------------------

async def run_single_task(
    task: TaskSpec,
    model: Model,
    strategy_name: str,
    hooks: dict,
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
        max_turns=10,
        stream_options=StreamOptions(max_tokens=1024, temperature=0.0),
        tool_selection_strategy=None,                        # all tools, always
        before_llm_call=hooks["before_llm_call"],
        context_transform=hooks["context_transform"],
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
                outcome.input_tokens_per_turn.append(msg.usage.input)

        if outcome.ttft_per_turn:
            outcome.avg_ttft = sum(outcome.ttft_per_turn) / len(outcome.ttft_per_turn)

        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolCall):
                        outcome.tools_called.append(block.name)

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


# ---------------------------------------------------------------------------
# Core: run all tasks for one strategy (SEQUENTIAL — enables cache warmup)
# ---------------------------------------------------------------------------

async def run_strategy(
    tasks: list[TaskSpec],
    model: Model,
    strategy_name: str,
    run_id: int,
    base_url: str = "http://localhost:8000/v1",
    truncate_keep_n: int = 2,
) -> StrategyResult:
    result = StrategyResult(strategy=strategy_name, run_id=run_id)
    hooks = build_strategy_hooks(strategy_name, SYSTEM_PROMPT, truncate_keep_n)

    result.cache_before = await get_cache_metrics(base_url)
    logger.info(
        "=== [Run %d] Strategy: %s | cache before: queries=%d hits=%d ===",
        run_id, strategy_name, result.cache_before.queries, result.cache_before.hits,
    )

    # SEQUENTIAL loop — each task completes before the next starts.
    # This allows the vLLM prefix cache to warm up across tasks:
    # task 2's system prompt + 50-tool prefix was already cached by task 1.
    for i, task in enumerate(tasks):
        outcome = await run_single_task(task, model, strategy_name, hooks)
        result.outcomes.append(outcome)

        status = "OK" if outcome.correct else ("ERROR" if outcome.error else "WRONG")
        ttft_str = ",".join(f"{t:.3f}" for t in outcome.ttft_per_turn)
        logger.info(
            "  [Run%d %d/%d] %s/%s: %s (steps=%d/%d, %.2fs, ttft=[%s])",
            run_id, i + 1, len(tasks), strategy_name, task.id, status,
            outcome.steps_completed, task.steps, outcome.latency_seconds, ttft_str,
        )

    result.cache_after = await get_cache_metrics(base_url)
    logger.info(
        "[Run %d] %s done: acc=%.1f%%, lat=%.2fs, avg_ttft=%.3fs, cache=%d/%d (%.1f%%)",
        run_id, strategy_name, result.accuracy * 100, result.avg_latency,
        result.avg_ttft, result.cache_delta_hits, result.cache_delta_queries,
        result.cache_hit_rate * 100,
    )
    return result


# ---------------------------------------------------------------------------
# Save and report
# ---------------------------------------------------------------------------

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
        "cache_hit_rate": result.cache_hit_rate,
        "cache_delta_queries": result.cache_delta_queries,
        "cache_delta_hits": result.cache_delta_hits,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_report(all_results: list[StrategyResult]) -> str:
    lines = ["# Experiment 004: KV Cache Stability — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("50 tools (all shown), 20 tasks, sequential execution, temperature=0.0\n")

    strategies: dict[str, list[StrategyResult]] = {}
    for r in all_results:
        strategies.setdefault(r.strategy, []).append(r)

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        "| Strategy    | Runs | Accuracy | Avg Latency | Avg TTFT | "
        "Cache Hit Rate | Avg Input Tok |"
    )
    lines.append(
        "|-------------|------|----------|-------------|----------|"
        "----------------|---------------|"
    )
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        runs = strategies[name]
        n = len(runs)
        avg_acc = sum(r.accuracy for r in runs) / n
        avg_lat = sum(r.avg_latency for r in runs) / n
        avg_ttft = sum(r.avg_ttft for r in runs) / n
        avg_cache = sum(r.cache_hit_rate for r in runs) / n
        avg_inp = sum(r.avg_input_tokens for r in runs) / n
        lines.append(
            f"| {name:11s} | {n:4d} | {avg_acc:7.1%} | {avg_lat:11.2f}s | "
            f"{avg_ttft:7.3f}s | {avg_cache:13.1%} | {avg_inp:13.0f} |"
        )

    # PRIMARY: TTFT by turn number
    lines.append("\n## TTFT by Turn Number (Primary Result)\n")
    lines.append(
        "Mean TTFT at each turn index, aggregated across all tasks.\n\n"
        "H1: stable TTFT should *decrease* after turn 1 (cross-task cache warming).\n"
        "H2: timestamp_s TTFT should stay *flat/high* (cache miss every turn).\n"
        "H3: truncate TTFT should *spike* at turns where truncation kicks in (turn 3+).\n"
    )

    # Find max turns across all outcomes
    max_turn = 0
    for r in all_results:
        for o in r.outcomes:
            max_turn = max(max_turn, len(o.ttft_per_turn))

    col_names = [name for name in STRATEGY_NAMES if name in strategies]
    header = "| Turn # |" + "".join(f" {n:18s} |" for n in col_names)
    sep = "|--------|" + "".join("-" * 20 + "|" for _ in col_names)
    lines.append(header)
    lines.append(sep)

    for turn_idx in range(max_turn):
        row = f"| {turn_idx + 1:6d} |"
        for name in col_names:
            vals = []
            for r in strategies[name]:
                for o in r.outcomes:
                    if o.error is None and turn_idx < len(o.ttft_per_turn):
                        vals.append(o.ttft_per_turn[turn_idx])
            if vals:
                mean = sum(vals) / len(vals)
                row += f" {mean:.3f}s (n={len(vals):2d})      |"
            else:
                row += "                    |"
        lines.append(row)

    # TTFT by task index (first run of stable) — shows cross-task cache warmup
    lines.append("\n## TTFT by Task Index (stable strategy, run 1)\n")
    lines.append(
        "Shows whether turn-1 TTFT decreases as more tasks are processed "
        "(evidence of cross-task prefix cache warmup).\n"
    )
    if "stable" in strategies:
        last_run = strategies["stable"][0]
        turn_cols = [f"Turn {i+1}" for i in range(max_turn)]
        lines.append("| Task | " + " | ".join(turn_cols) + " |")
        lines.append("|------|" + "--------|" * max_turn)
        for task_idx, o in enumerate(last_run.outcomes):
            cells = []
            for t_idx in range(max_turn):
                if t_idx < len(o.ttft_per_turn):
                    cells.append(f"{o.ttft_per_turn[t_idx]:.3f}s")
                else:
                    cells.append("       ")
            lines.append(f"| {task_idx:4d} | " + " | ".join(cells) + " |")

    # TTFT by task index for all strategies (turn 1 only) — direct cross-task comparison
    lines.append("\n## Turn-1 TTFT by Task Index (all strategies)\n")
    lines.append(
        "Turn 1 is the first LLM call per task (system prompt + task prompt only).\n"
        "For stable, this TTFT should decrease as the system prompt prefix warms up.\n"
        "For timestamp_s, this TTFT should stay high (new timestamp each call).\n"
    )
    lines.append("| Task | " + " | ".join(f"{n:11s}" for n in col_names) + " |")
    lines.append("|------|" + "-------------|" * len(col_names))

    # Use max tasks from first run of any strategy
    n_tasks = max(
        len(strategies[n][0].outcomes) for n in col_names if n in strategies
    )
    for task_idx in range(n_tasks):
        row = f"| {task_idx:4d} |"
        for name in col_names:
            r = strategies[name][0]
            if task_idx < len(r.outcomes):
                o = r.outcomes[task_idx]
                if o.error is None and o.ttft_per_turn:
                    row += f" {o.ttft_per_turn[0]:.3f}s      |"
                else:
                    row += " ERROR        |"
            else:
                row += "             |"
        lines.append(row)

    # Prefix cache metrics
    lines.append("\n## Prefix Cache Metrics\n")
    lines.append("| Strategy    | Run | Queries (delta) | Hits (delta) | Hit Rate |")
    lines.append("|-------------|-----|-----------------|--------------|----------|")
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        for r in strategies[name]:
            lines.append(
                f"| {name:11s} | {r.run_id:3d} | {r.cache_delta_queries:15,d} | "
                f"{r.cache_delta_hits:12,d} | {r.cache_hit_rate:7.1%} |"
            )

    # Per-task accuracy breakdown
    lines.append("\n## Per-Task Results (Run 1)\n")
    lines.append(
        "| Task ID | Strategy    | Correct | Steps | Latency | Avg TTFT | Tokens |"
    )
    lines.append(
        "|---------|-------------|---------|-------|---------|----------|--------|"
    )
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        first_run = strategies[name][0]
        for o in first_run.outcomes:
            task = _task_by_id.get(o.task_id)
            expected_steps = task.steps if task else "?"
            mark = "Y" if o.correct else "N"
            lines.append(
                f"| {o.task_id:35s} | {name:11s} | {mark:7s} | "
                f"{o.steps_completed:>2d}/{expected_steps} | "
                f"{o.latency_seconds:7.2f}s | {o.avg_ttft:7.3f}s | {o.total_tokens:6d} |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Run KV cache stability experiment (004)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs per strategy (default: 1)")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGY_NAMES),
                        help="Strategies to run (default: all three)")
    parser.add_argument("--truncate-keep-n", type=int, default=2,
                        help="keep_last_n for truncate strategy (default: 2)")
    args = parser.parse_args()

    model = Model(
        id=args.model_id,
        name="Qwen3-8B",
        provider="openai_compat",
        base_url=args.base_url,
    )

    tasks = load_tasks()
    logger.info("Loaded %d tasks, %d tools", len(tasks), len(ALL_TOOLS))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[StrategyResult] = []

    # Fully sequential: one run, one strategy, one task at a time.
    # This gives each strategy a clean, deterministic cache state.
    for run_id in range(1, args.runs + 1):
        for strategy_name in args.strategies:
            result = await run_strategy(
                tasks, model, strategy_name, run_id,
                base_url=args.base_url,
                truncate_keep_n=args.truncate_keep_n,
            )
            path = RESULTS_DIR / f"{strategy_name}_run{run_id}.json"
            save_strategy_result(result, path)
            logger.info("Saved: %s", path)
            all_results.append(result)

    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved: %s", report_path)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
