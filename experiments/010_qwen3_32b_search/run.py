"""Run experiment 010: Qwen3-30B-A3B-Thinking-2507 (base) on GAIA search tasks.

Uses core.agent with standard hermes JSON tool calling (same as 007).
Content format: text_only (best strategy from 007).

Usage:
    python -m experiments.010_qwen3_32b_search.run [--runs N] [--pilot]
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
    ToolCall,
    ToolResultMessage,
)
import core.providers  # noqa: F401

import re as _re
from bs4 import BeautifulSoup

from bench.verifier import GAIAVerifier
from observer.client import attach_observer
from tools.web_search import web_search
from tools.fetch_page import fetch_page
from core.types import TextContent, ToolResultMessage as _TRM

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
TASKS_FILE = Path(__file__).parent.parent / "007_content_format" / "tasks.jsonl"

MODEL_ID = "Qwen/Qwen3-30B-A3B-Thinking-2507"
BASE_URL = "http://localhost:8001/v1"

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

IMPORTANT: Your very first action must ALWAYS be a web_search call.

/no_think"""

ALL_TOOLS = [web_search, fetch_page]


def _text_only_hook():
    """text_only after_tool_exec hook: convert fetch_page HTML to plain text."""
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return _re.sub(r"\n{3,}", "\n\n", text)

    async def after_tool_exec(tc, result: _TRM) -> _TRM:
        if tc.name != "fetch_page" or result.is_error:
            return result
        try:
            data = json.loads(result.content[0].text)
            data["content"] = _html_to_text(data["content"])
            data["content_length"] = len(data["content"])
            data["format"] = "text_only"
            result.content = [TextContent(text=json.dumps(data, ensure_ascii=False))]
        except Exception:
            pass
        return result

    return after_tool_exec


@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskOutcome:
    task_id: str
    run_id: int = 0
    correct: bool = False
    answer: str = ""
    expected: str = ""
    verification_reason: str = ""
    num_turns: int = 0
    num_web_search_calls: int = 0
    num_fetch_page_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0
    error: str | None = None
    level: int = 0


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


def extract_answer(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AssistantMessage):
            text = extract_text(msg).strip()
            if text:
                return text
    return ""


def collect_metrics(messages: list, outcome: TaskOutcome) -> None:
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


async def run_single_task(
    task: TaskSpec,
    model: Model,
    run_id: int,
    verifier: GAIAVerifier,
    max_turns: int = 30,
) -> TaskOutcome:
    outcome = TaskOutcome(
        task_id=task.id,
        run_id=run_id,
        expected=task.expected_answer,
        level=int(task.metadata.get("level", 0)),
    )

    format_hook = _text_only_hook()

    config = AgentConfig(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        max_turns=max_turns,
        stream_options=StreamOptions(max_tokens=8192, temperature=0.6),
        after_tool_exec=format_hook,
    )

    attach_observer(config, run_id="exp_010_qwen3_30b_a3b", task_id=f"r{run_id}_{task.id[:8]}")

    start = time.time()
    try:
        messages = await run_agent(config, task.prompt)
        outcome.latency_seconds = time.time() - start
        outcome.answer = extract_answer(messages)
        collect_metrics(messages, outcome)

        for msg in messages:
            if isinstance(msg, AssistantMessage) and msg.error_message:
                outcome.error = msg.error_message
                break

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


async def run_all_tasks(
    tasks: list[TaskSpec],
    model: Model,
    run_id: int,
    verifier: GAIAVerifier,
    max_turns: int = 30,
    concurrency: int = 1,
) -> list[TaskOutcome]:
    sem = asyncio.Semaphore(concurrency)
    completed = [0]

    async def _run_one(task: TaskSpec) -> TaskOutcome:
        async with sem:
            outcome = await run_single_task(task, model, run_id, verifier, max_turns)
            completed[0] += 1
            status = "OK" if outcome.correct else ("ERR" if outcome.error else "WRONG")
            logger.info(
                "[%d/%d] L%d %s: %s | turns=%d search=%d fetch=%d | %.1fs | %d in %d out tok",
                completed[0], len(tasks), outcome.level, task.id[:12], status,
                outcome.num_turns, outcome.num_web_search_calls, outcome.num_fetch_page_calls,
                outcome.latency_seconds, outcome.input_tokens, outcome.output_tokens,
            )
            return outcome

    return list(await asyncio.gather(*[_run_one(t) for t in tasks]))


def generate_report(all_runs: list[list[TaskOutcome]]) -> str:
    lines = ["# Experiment 010: Qwen3-30B-A3B-Thinking-2507 (base) — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_outcomes = [o for run in all_runs for o in run]
    n_runs = len(all_runs)

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    acc = avg([float(o.correct) for o in all_outcomes])
    lat = avg([o.latency_seconds for o in all_outcomes if not o.error])
    turns = avg([o.num_turns for o in all_outcomes])
    searches = avg([o.num_web_search_calls for o in all_outcomes])
    fetches = avg([o.num_fetch_page_calls for o in all_outcomes])
    inp = avg([o.input_tokens for o in all_outcomes if not o.error])
    out = avg([o.output_tokens for o in all_outcomes if not o.error])

    lines.append("## Summary\n")
    lines.append(f"- Runs: {n_runs}, Tasks: {len(all_runs[0]) if all_runs else 0}")
    lines.append(f"- **Accuracy: {acc:.1%}** ({sum(o.correct for o in all_outcomes)}/{len(all_outcomes)})")
    lines.append(f"- Avg latency: {lat:.1f}s | Avg turns: {turns:.1f}")
    lines.append(f"- Avg web_search: {searches:.1f} | Avg fetch_page: {fetches:.1f}")
    lines.append(f"- Avg input tokens: {inp:.0f} | Avg output tokens: {out:.0f}\n")

    lines.append("## Accuracy by Level\n")
    lines.append("| Level | Correct | Total | % |")
    lines.append("|-------|---------|-------|---|")
    for lvl in [1, 2, 3]:
        lo = [o for o in all_outcomes if o.level == lvl]
        c = sum(o.correct for o in lo)
        pct = f"{c/len(lo):.0%}" if lo else "N/A"
        lines.append(f"| L{lvl} | {c} | {len(lo)} | {pct} |")

    lines.append("\n## vs Baselines\n")
    lines.append("| Model | Size | Accuracy | Latency | Input tok | Tool format |")
    lines.append("|-------|------|----------|---------|-----------|-------------|")
    lines.append(f"| **Qwen3-30B-A3B-Thinking (this)** | 30B (3B active) | **{acc:.1%}** | {lat:.0f}s | {inp:.0f} | JSON hermes |")
    lines.append(f"| MiroThinker-1.7-mini (008, 256K) | 30B | 38.9% | 225s | 304205 | XML/MCP |")
    lines.append(f"| Claude Haiku 4.5 (007) | ~3.5B | 67.3% | 76s | 179034 | JSON Bedrock |")

    lines.append("\n## Per-Task Results\n")
    lines.append("| Run | Task | L | OK | Answer | Turns | S | F | Lat |")
    lines.append("|-----|------|---|----|----|-------|---|---|-----|")
    for o in all_outcomes:
        mark = "Y" if o.correct else ("E" if o.error else "N")
        ans = (o.answer[:25] + "...") if len(o.answer) > 25 else o.answer
        lines.append(
            f"| {o.run_id} | {o.task_id[:14]} | L{o.level} | {mark} | {ans:25s} | "
            f"{o.num_turns} | {o.num_web_search_calls} | {o.num_fetch_page_calls} | {o.latency_seconds:.0f}s |"
        )

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--pilot", action="store_true", help="First 3 tasks only")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    model = Model(
        id=MODEL_ID,
        name="Qwen3-30B-A3B-Thinking",
        provider="openai_compat",
        base_url=BASE_URL,
    )
    judge_model = Model(
        id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        name="Claude Sonnet (judge)",
        provider="bedrock",
    )
    verifier = GAIAVerifier(judge_model=judge_model)

    tasks = load_tasks()
    if args.pilot:
        tasks = tasks[:3]
        logger.info("PILOT: %d tasks", len(tasks))
    logger.info("Loaded %d tasks, runs=%d", len(tasks), args.runs)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_runs: list[list[TaskOutcome]] = []

    for run_id in range(1, args.runs + 1):
        out_path = RESULTS_DIR / f"run{run_id}.json"

        existing: dict[str, TaskOutcome] = {}
        if out_path.exists():
            try:
                saved = json.loads(out_path.read_text())
                for o in saved.get("outcomes", []):
                    existing[o["task_id"]] = TaskOutcome(**o)
            except Exception:
                pass

        if len(existing) == len(tasks):
            logger.info("SKIP (done): %s", out_path)
            all_runs.append([existing[t.id] for t in tasks])
            continue

        missing = [t for t in tasks if t.id not in existing]
        if existing:
            logger.info("PARTIAL resume: %d/%d done", len(existing), len(tasks))

        logger.info("=== Run %d | %d tasks ===", run_id, len(missing))
        new_outcomes = await run_all_tasks(missing, model, run_id, verifier, args.max_turns, args.concurrency)

        outcome_map = {o.task_id: o for o in new_outcomes}
        merged = []
        for t in tasks:
            if t.id in outcome_map:
                merged.append(outcome_map[t.id])
            elif t.id in existing:
                merged.append(existing[t.id])

        acc = sum(o.correct for o in merged) / len(merged) if merged else 0
        out_path.write_text(json.dumps({
            "run_id": run_id, "model": MODEL_ID, "accuracy": acc,
            "outcomes": [asdict(o) for o in merged],
        }, indent=2, ensure_ascii=False))
        logger.info("Saved %s (acc=%.1f%%)", out_path, acc * 100)
        all_runs.append(merged)

    report = generate_report(all_runs)
    (RESULTS_DIR / "report.md").write_text(report)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
