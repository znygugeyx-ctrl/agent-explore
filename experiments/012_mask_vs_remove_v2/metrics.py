"""Per-turn metrics and cost calculation for Experiment 012."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.types import ModelCost, Usage


@dataclass
class TurnMetrics:
    """Metrics collected for a single turn within a multi-turn task."""
    turn_idx: int
    ttft_seconds: float
    latency_seconds: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    tools_presented: int       # how many tools the model could see
    tools_available: int       # how many tools were "available" (in schedule)
    tool_called: str | None    # actual tool name called by model (None if no call)
    ground_truth_tool: str     # expected tool name from BFCL ground truth
    correct: bool              # tool_called == ground_truth_tool
    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_cache_read: float = 0.0
    cost_total: float = 0.0


@dataclass
class TaskOutcome:
    """Aggregated result for one task under one strategy."""
    task_id: str
    strategy: str
    model_name: str
    run_id: int
    turns: list[TurnMetrics] = field(default_factory=list)
    error: str | None = None

    @property
    def accuracy(self) -> float:
        if not self.turns:
            return 0.0
        return sum(1 for t in self.turns if t.correct) / len(self.turns)

    @property
    def total_cost(self) -> float:
        return sum(t.cost_total for t in self.turns)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_cache_read_tokens(self) -> int:
        return sum(t.cache_read_tokens for t in self.turns)

    @property
    def avg_ttft(self) -> float:
        ttfts = [t.ttft_seconds for t in self.turns if t.ttft_seconds > 0]
        return sum(ttfts) / len(ttfts) if ttfts else 0.0

    @property
    def num_turns(self) -> int:
        return len(self.turns)


def compute_turn_cost(usage: Usage, model_cost: ModelCost) -> tuple[float, float, float, float]:
    """Return (cost_input, cost_output, cost_cache_read, cost_total) in $."""
    cost_in = usage.input * model_cost.input / 1_000_000
    cost_out = usage.output * model_cost.output / 1_000_000
    cost_cr = usage.cache_read * model_cost.cache_read / 1_000_000
    cost_cw = usage.cache_write * model_cost.cache_write / 1_000_000
    return cost_in, cost_out, cost_cr, cost_in + cost_out + cost_cr + cost_cw


def summarize_outcomes(outcomes: list[TaskOutcome]) -> dict[str, Any]:
    """Aggregate outcomes across tasks for one (strategy, model, run) combination."""
    if not outcomes:
        return {}
    valid = [o for o in outcomes if o.error is None and o.turns]
    n = len(valid)
    if n == 0:
        return {"n": 0, "error": "all tasks failed"}

    accuracies = [o.accuracy for o in valid]
    costs = [o.total_cost for o in valid]
    input_toks = [o.total_input_tokens for o in valid]
    cache_reads = [o.total_cache_read_tokens for o in valid]
    ttfts = [t.ttft_seconds for o in valid for t in o.turns if t.ttft_seconds > 0]

    def mean(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    # Per-turn TTFT breakdown (turn 0, 1, 2, ...)
    max_turns = max((o.num_turns for o in valid), default=0)
    ttft_by_turn: dict[int, list[float]] = {i: [] for i in range(max_turns)}
    for o in valid:
        for t in o.turns:
            if t.ttft_seconds > 0:
                ttft_by_turn[t.turn_idx].append(t.ttft_seconds)
    avg_ttft_by_turn = {i: mean(v) for i, v in ttft_by_turn.items() if v}

    # Cache efficiency
    total_input = sum(input_toks)
    total_cache_read = sum(cache_reads)
    cache_rate = total_cache_read / total_input if total_input > 0 else 0.0

    return {
        "n": n,
        "accuracy_mean": mean(accuracies),
        "accuracy_per_task": accuracies,
        "cost_mean": mean(costs),
        "cost_total": sum(costs),
        "input_tokens_mean": mean(input_toks),
        "cache_read_tokens_mean": mean(cache_reads),
        "cache_read_rate": cache_rate,
        "ttft_mean": mean(ttfts),
        "ttft_by_turn": avg_ttft_by_turn,
    }
