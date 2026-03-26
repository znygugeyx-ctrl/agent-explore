"""Run the content format experiment (007).

Usage:
    python -m experiments.007_content_format.run [--runs N] [--strategies ...]

Tests how web page content format affects DeepSearch agent performance.
4 strategies: raw_html, markdown, text_only, pruned_html.
Each strategy runs end-to-end independently (no shared cache).
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
import core.providers  # noqa: F401 — registers providers

from bench.verifier import GAIAVerifier
from observer.client import attach_observer
from tools.web_search import web_search
from tools.fetch_page import fetch_page

from .strategies import build_format_hook, STRATEGY_NAMES

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
TASKS_FILE = EXPERIMENT_DIR / "tasks.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a research assistant that answers factual questions by searching the web.

RULES (you MUST follow these):
1. You MUST call web_search before answering ANY question. NEVER answer from memory.
2. After getting search results, use fetch_page to read the most relevant URLs.
3. Read the page content carefully to find the specific answer.
4. If the first page doesn't have the answer, try other URLs or refine your search.
5. For multi-part questions, search and fetch multiple pages as needed.
6. When you have found the answer, respond with ONLY the final answer value.
   Do NOT include reasoning, explanation, or intermediate steps in your final response.
   Good: "42" or "Paris" or "fluffy"
   Bad: "Based on my research, the answer is 42 because..."

IMPORTANT: Your very first action must ALWAYS be a web_search call."""

ALL_TOOLS = [web_search, fetch_page]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskOutcome:
    task_id: str
    strategy: str
    run_id: int = 0
    correct: bool = False
    answer: str = ""
    expected: str = ""
    verification_reason: str = ""
    num_turns: int = 0
    num_web_search_calls: int = 0
    num_fetch_page_calls: int = 0
    fetch_content_sizes: list[int] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0
    error: str | None = None
    level: int = 0


@dataclass
class StrategyResult:
    strategy: str
    run_id: int
    outcomes: list[TaskOutcome] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        # Errors (e.g. context overflow) count as wrong — they are strategy defects
        return sum(1 for o in self.outcomes if o.correct) / len(self.outcomes) if self.outcomes else 0.0

    @property
    def avg_latency(self) -> float:
        lats = [o.latency_seconds for o in self.outcomes if o.error is None]
        return sum(lats) / len(lats) if lats else 0.0

    @property
    def avg_input_tokens(self) -> float:
        vals = [o.input_tokens for o in self.outcomes if o.error is None]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def avg_fetch_size(self) -> float:
        all_sizes = []
        for o in self.outcomes:
            all_sizes.extend(o.fetch_content_sizes)
        return sum(all_sizes) / len(all_sizes) if all_sizes else 0.0


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks(path: Path = TASKS_FILE) -> list[TaskSpec]:
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            tasks.append(TaskSpec(
                id=data["id"],
                prompt=data["prompt"],
                expected_answer=data["expected_answer"],
                metadata=data.get("metadata", {}),
            ))
    return tasks


# ---------------------------------------------------------------------------
# Extract final answer from agent messages
# ---------------------------------------------------------------------------

def extract_answer(messages: list) -> str:
    """Extract the agent's final text answer from message history."""
    for msg in reversed(messages):
        if isinstance(msg, AssistantMessage):
            text = extract_text(msg).strip()
            if text:
                return text
    return ""


# ---------------------------------------------------------------------------
# Collect metrics from messages
# ---------------------------------------------------------------------------

def collect_metrics(messages: list, outcome: TaskOutcome) -> None:
    """Populate outcome metrics from message history."""
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            outcome.num_turns += 1
            outcome.input_tokens += msg.usage.input
            outcome.output_tokens += msg.usage.output
            for block in msg.content:
                if isinstance(block, ToolCall):
                    if block.name == "web_search":
                        outcome.num_web_search_calls += 1
                    elif block.name == "fetch_page":
                        outcome.num_fetch_page_calls += 1
        elif isinstance(msg, ToolResultMessage):
            if msg.tool_name == "fetch_page" and not msg.is_error:
                try:
                    data = json.loads(msg.content[0].text)
                    outcome.fetch_content_sizes.append(data.get("content_length", 0))
                except (json.JSONDecodeError, IndexError):
                    pass


# ---------------------------------------------------------------------------
# Core: run single task
# ---------------------------------------------------------------------------

async def run_single_task(
    task: TaskSpec,
    model: Model,
    strategy: str,
    run_id: int,
    verifier: GAIAVerifier,
    max_turns: int = 15,
) -> TaskOutcome:
    outcome = TaskOutcome(
        task_id=task.id,
        strategy=strategy,
        run_id=run_id,
        expected=task.expected_answer,
        level=int(task.metadata.get("level", 0)),
    )

    format_hook = build_format_hook(strategy)

    config = AgentConfig(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        max_turns=max_turns,
        stream_options=StreamOptions(max_tokens=4096, temperature=0.0),
        after_tool_exec=format_hook,
    )

    # Observer: format hook first, then observer chains into it
    attach_observer(config, run_id="exp_007_phase2", task_id=f"{strategy}_r{run_id}_{task.id}")

    start = time.time()
    try:
        messages = await run_agent(config, task.prompt)
        outcome.latency_seconds = time.time() - start

        outcome.answer = extract_answer(messages)
        collect_metrics(messages, outcome)

        # Record LLM errors (e.g. "input too long") for analysis
        for msg in messages:
            if isinstance(msg, AssistantMessage) and msg.error_message:
                outcome.error = msg.error_message
                break

        # Verify answer
        is_correct, reason = await verifier.verify(
            task.prompt, task.expected_answer, outcome.answer, task.metadata
        )
        outcome.correct = is_correct
        outcome.verification_reason = reason

    except Exception as e:
        outcome.latency_seconds = time.time() - start
        outcome.error = str(e)
        logger.error("Task %s failed: %s", task.id, e)

    return outcome


# ---------------------------------------------------------------------------
# Core: run strategy
# ---------------------------------------------------------------------------

async def run_strategy(
    tasks: list[TaskSpec],
    model: Model,
    strategy: str,
    run_id: int,
    verifier: GAIAVerifier,
    max_turns: int = 15,
    concurrency: int = 3,
) -> StrategyResult:
    result = StrategyResult(strategy=strategy, run_id=run_id)
    sem = asyncio.Semaphore(concurrency)
    completed = [0]

    logger.info("=== [Run %d] Strategy: %s | %d tasks (concurrency=%d) ===",
                run_id, strategy, len(tasks), concurrency)

    async def _run_one(i: int, task: TaskSpec) -> TaskOutcome:
        async with sem:
            outcome = await run_single_task(task, model, strategy, run_id, verifier, max_turns)
            completed[0] += 1
            status = "OK" if outcome.correct else ("ERR" if outcome.error else "WRONG")
            logger.info(
                "  [%d/%d] L%d %s: %s | turns=%d search=%d fetch=%d | %.1fs | %d tok",
                completed[0], len(tasks), outcome.level, task.id[:12], status,
                outcome.num_turns, outcome.num_web_search_calls, outcome.num_fetch_page_calls,
                outcome.latency_seconds, outcome.input_tokens + outcome.output_tokens,
            )
            return outcome

    outcomes = await asyncio.gather(*[_run_one(i, t) for i, t in enumerate(tasks)])
    result.outcomes = list(outcomes)

    logger.info(
        "[Run %d] %s done: acc=%.1f%%, avg_lat=%.1fs, avg_input=%d tok, avg_fetch_size=%d chars",
        run_id, strategy, result.accuracy * 100, result.avg_latency,
        result.avg_input_tokens, result.avg_fetch_size,
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
        "avg_fetch_size": result.avg_fetch_size,
        "outcomes": [asdict(o) for o in result.outcomes],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_report(all_results: list[StrategyResult]) -> str:
    lines = ["# Experiment 007: Content Format — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    strategies: dict[str, list[StrategyResult]] = {}
    for r in all_results:
        strategies.setdefault(r.strategy, []).append(r)

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        "| Strategy     | Runs | Accuracy | Avg Latency | Avg Input Tok | "
        "Avg Fetch Size | Avg Turns | Avg Fetches |"
    )
    lines.append(
        "|--------------|------|----------|-------------|---------------|"
        "----------------|-----------|-------------|"
    )
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        runs = strategies[name]
        n = len(runs)
        avg_acc = sum(r.accuracy for r in runs) / n
        avg_lat = sum(r.avg_latency for r in runs) / n
        avg_inp = sum(r.avg_input_tokens for r in runs) / n
        avg_fs = sum(r.avg_fetch_size for r in runs) / n
        avg_turns = sum(
            sum(o.num_turns for o in r.outcomes) / len(r.outcomes)
            for r in runs
        ) / n
        avg_fetches = sum(
            sum(o.num_fetch_page_calls for o in r.outcomes) / len(r.outcomes)
            for r in runs
        ) / n
        lines.append(
            f"| {name:12s} | {n:4d} | {avg_acc:7.1%} | {avg_lat:11.1f}s | "
            f"{avg_inp:13.0f} | {avg_fs:14.0f} | {avg_turns:9.1f} | {avg_fetches:11.1f} |"
        )

    # Per-level accuracy
    lines.append("\n## Accuracy by Level\n")
    lines.append("| Strategy     | L1 | L2 | L3 |")
    lines.append("|--------------|----|----|---| ")
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        by_level: dict[int, list[bool]] = {}
        for r in strategies[name]:
            for o in r.outcomes:
                if o.error is None:
                    by_level.setdefault(o.level, []).append(o.correct)
        cells = []
        for lvl in [1, 2, 3]:
            vals = by_level.get(lvl, [])
            if vals:
                cells.append(f"{sum(vals)/len(vals):.0%}")
            else:
                cells.append("-")
        lines.append(f"| {name:12s} | {' | '.join(cells)} |")

    # Per-task detail (first run)
    lines.append("\n## Per-Task Results (Run 1)\n")
    lines.append(
        "| Task ID | Level | Strategy | Correct | Answer | Turns | Fetches | Tokens | Latency |"
    )
    lines.append(
        "|---------|-------|----------|---------|--------|-------|---------|--------|---------|"
    )
    for name in STRATEGY_NAMES:
        if name not in strategies:
            continue
        first_run = strategies[name][0]
        for o in first_run.outcomes:
            mark = "Y" if o.correct else ("E" if o.error else "N")
            ans = (o.answer[:30] + "...") if len(o.answer) > 30 else o.answer
            lines.append(
                f"| {o.task_id[:16]} | L{o.level} | {name:12s} | {mark:7s} | "
                f"{ans:30s} | {o.num_turns:5d} | {o.num_fetch_page_calls:7d} | "
                f"{o.input_tokens + o.output_tokens:6d} | {o.latency_seconds:7.1f}s |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Run content format experiment (007)")
    parser.add_argument("--runs", type=int, default=2, help="Runs per strategy (default: 2)")
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGY_NAMES))
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--tasks", type=str, default=str(TASKS_FILE))
    parser.add_argument("--concurrency", type=int, default=2, help="Parallel tasks per strategy (default: 2)")
    args = parser.parse_args()

    model = Model(
        id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        name="Claude Haiku 4.5",
        provider="bedrock",
    )

    judge_model = Model(
        id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        name="Claude Sonnet (judge)",
        provider="bedrock",
    )
    verifier = GAIAVerifier(judge_model=judge_model)

    tasks = load_tasks(Path(args.tasks))
    logger.info("Loaded %d tasks, strategies=%s, runs=%d", len(tasks), args.strategies, args.runs)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[StrategyResult] = []

    for run_id in range(1, args.runs + 1):
        for strategy in args.strategies:
            path = RESULTS_DIR / f"{strategy}_run{run_id}.json"

            # Resume: load existing partial/complete results
            existing_outcomes: dict[str, TaskOutcome] = {}
            if path.exists():
                try:
                    with open(path) as f:
                        saved = json.load(f)
                    for o in saved.get("outcomes", []):
                        existing_outcomes[o["task_id"]] = TaskOutcome(**{
                            k: v for k, v in o.items()
                        })
                except Exception:
                    pass  # corrupted file — re-run all

            # Full: skip entirely
            if len(existing_outcomes) == len(tasks):
                logger.info("SKIP (already done): %s", path)
                sr = StrategyResult(strategy=strategy, run_id=run_id)
                sr.outcomes = [existing_outcomes[t.id] for t in tasks]
                all_results.append(sr)
                continue

            # Partial: only run missing tasks
            missing = [t for t in tasks if t.id not in existing_outcomes]
            if existing_outcomes:
                logger.info("PARTIAL resume: %d/%d done, %d to run",
                            len(existing_outcomes), len(tasks), len(missing))

            result = await run_strategy(
                missing, model, strategy, run_id, verifier, args.max_turns, args.concurrency
            )

            # Merge existing + new outcomes, preserving task order
            merged = StrategyResult(strategy=strategy, run_id=run_id)
            new_outcomes = {o.task_id: o for o in result.outcomes}
            for t in tasks:
                if t.id in new_outcomes:
                    merged.outcomes.append(new_outcomes[t.id])
                elif t.id in existing_outcomes:
                    merged.outcomes.append(existing_outcomes[t.id])
            save_strategy_result(merged, path)
            logger.info("Saved: %s (%d outcomes)", path, len(merged.outcomes))
            all_results.append(merged)

    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved: %s", report_path)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
