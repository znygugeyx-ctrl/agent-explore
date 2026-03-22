"""Benchmark data types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from core.types import Message, Usage


@dataclass
class Task:
    """A single benchmark task."""

    id: str
    prompt: str
    expected_answer: str
    tools: list[str] | None = None  # Tool names available for this task
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttemptResult:
    """Result of a single attempt at a task."""

    task_id: str
    answer: str = ""
    correct: bool = False
    judge_reasoning: str = ""
    messages: list[Message] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass
class TaskResult:
    """Aggregated result for a task across multiple attempts."""

    task: Task
    attempts: list[AttemptResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.attempts:
            return 0.0
        return sum(1 for a in self.attempts if a.correct) / len(self.attempts)

    @property
    def any_correct(self) -> bool:
        return any(a.correct for a in self.attempts)


@dataclass
class BenchmarkResult:
    """Full benchmark run result."""

    name: str
    model: str
    tasks: list[TaskResult] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: time.time())

    @property
    def overall_score(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks if t.any_correct) / len(self.tasks)

    @property
    def total_usage(self) -> Usage:
        total = Usage()
        for task in self.tasks:
            for attempt in task.attempts:
                total.input += attempt.usage.input
                total.output += attempt.usage.output
                total.total_tokens += attempt.usage.total_tokens
        return total
