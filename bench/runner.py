"""Benchmark evaluation runner."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from core.agent import AgentConfig, run_agent
from core.llm import extract_text
from core.types import AssistantMessage, TextContent, Usage

from .types import AttemptResult, BenchmarkResult, Task, TaskResult
from .verifier import BaseVerifier

logger = logging.getLogger(__name__)


def load_tasks(path: str | Path) -> list[Task]:
    """Load benchmark tasks from a JSONL file.

    Each line should be a JSON object with: id, prompt, expected_answer.
    Optional: tools (list[str]), metadata (dict).
    """
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            tasks.append(
                Task(
                    id=data["id"],
                    prompt=data["prompt"],
                    expected_answer=data["expected_answer"],
                    tools=data.get("tools"),
                    metadata=data.get("metadata", {}),
                )
            )
    return tasks


async def run_single_task(
    task: Task,
    config: AgentConfig,
    verifier: BaseVerifier,
    num_attempts: int = 1,
) -> TaskResult:
    """Run a single benchmark task with multiple attempts."""
    result = TaskResult(task=task)

    for attempt_idx in range(num_attempts):
        attempt = AttemptResult(task_id=task.id)
        start_time = time.time()

        try:
            messages = await run_agent(config, task.prompt)
            attempt.messages = messages
            attempt.duration_seconds = time.time() - start_time

            # Extract answer from last assistant message
            for msg in reversed(messages):
                if isinstance(msg, AssistantMessage):
                    attempt.answer = extract_text(msg)
                    # Aggregate usage
                    attempt.usage.input += msg.usage.input
                    attempt.usage.output += msg.usage.output
                    attempt.usage.total_tokens += msg.usage.total_tokens
                    break

            # Aggregate all usage
            for msg in messages:
                if isinstance(msg, AssistantMessage) and msg != messages[-1]:
                    attempt.usage.input += msg.usage.input
                    attempt.usage.output += msg.usage.output
                    attempt.usage.total_tokens += msg.usage.total_tokens

            # Verify answer
            correct, reasoning = await verifier.verify(
                question=task.prompt,
                expected=task.expected_answer,
                predicted=attempt.answer,
                metadata=task.metadata,
            )
            attempt.correct = correct
            attempt.judge_reasoning = reasoning

        except Exception as e:
            attempt.error = str(e)
            attempt.duration_seconds = time.time() - start_time
            logger.error("Task %s attempt %d failed: %s", task.id, attempt_idx + 1, e)

        result.attempts.append(attempt)

        # Early exit on correct answer (pass@k)
        if attempt.correct:
            break

    return result


async def run_benchmark(
    tasks: list[Task],
    config: AgentConfig,
    verifier: BaseVerifier,
    num_attempts: int = 1,
    max_parallel: int = 5,
) -> BenchmarkResult:
    """Run benchmark evaluation on all tasks.

    Args:
        tasks: List of benchmark tasks.
        config: Agent configuration.
        verifier: Answer verifier.
        num_attempts: Number of attempts per task (pass@k).
        max_parallel: Maximum concurrent tasks.
    """
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_with_limit(task: Task) -> TaskResult:
        async with semaphore:
            logger.info("Running task %s", task.id)
            return await run_single_task(task, config, verifier, num_attempts)

    results = await asyncio.gather(*[run_with_limit(t) for t in tasks])

    return BenchmarkResult(
        name="benchmark",
        model=config.model.id,
        tasks=list(results),
    )


def save_results(result: BenchmarkResult, path: str | Path) -> None:
    """Save benchmark results to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "name": result.name,
        "model": result.model,
        "overall_score": result.overall_score,
        "total_tasks": len(result.tasks),
        "correct_tasks": sum(1 for t in result.tasks if t.any_correct),
        "timestamp": result.timestamp,
        "usage": {
            "input": result.total_usage.input,
            "output": result.total_usage.output,
            "total_tokens": result.total_usage.total_tokens,
        },
        "tasks": [
            {
                "id": tr.task.id,
                "prompt": tr.task.prompt,
                "expected_answer": tr.task.expected_answer,
                "pass_rate": tr.pass_rate,
                "any_correct": tr.any_correct,
                "attempts": [
                    {
                        "answer": a.answer,
                        "correct": a.correct,
                        "judge_reasoning": a.judge_reasoning,
                        "duration_seconds": a.duration_seconds,
                        "error": a.error,
                        "usage": {
                            "input": a.usage.input,
                            "output": a.usage.output,
                            "total_tokens": a.usage.total_tokens,
                        },
                    }
                    for a in tr.attempts
                ],
            }
            for tr in result.tasks
        ],
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Results saved to %s", path)
