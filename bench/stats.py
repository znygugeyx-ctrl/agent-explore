"""Multi-run statistical aggregation for benchmark results."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def load_result(path: str | Path) -> dict[str, Any]:
    """Load a single benchmark result JSON file."""
    with open(path) as f:
        return json.loads(f.read())


def aggregate_runs(results_dir: str | Path) -> dict[str, Any]:
    """Aggregate multiple benchmark runs from a directory.

    Expects: results_dir/run_1/results.json, run_2/results.json, etc.
    Or: results_dir/*.json
    """
    results_dir = Path(results_dir)
    result_files = sorted(results_dir.glob("**/results.json"))
    if not result_files:
        result_files = sorted(results_dir.glob("*.json"))

    if not result_files:
        raise FileNotFoundError(f"No result files found in {results_dir}")

    scores: list[float] = []
    for f in result_files:
        data = load_result(f)
        scores.append(data.get("overall_score", 0.0))

    n = len(scores)
    mean = sum(scores) / n
    if n > 1:
        variance = sum((s - mean) ** 2 for s in scores) / (n - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0

    return {
        "num_runs": n,
        "scores": scores,
        "mean": mean,
        "std": std,
        "min": min(scores),
        "max": max(scores),
        "ci_95": 1.96 * std / math.sqrt(n) if n > 1 else 0.0,
    }


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare two aggregated results."""
    return {
        "a_mean": a["mean"],
        "b_mean": b["mean"],
        "difference": b["mean"] - a["mean"],
        "a_std": a["std"],
        "b_std": b["std"],
        "a_runs": a["num_runs"],
        "b_runs": b["num_runs"],
    }


def print_summary(stats: dict[str, Any], name: str = "Benchmark") -> None:
    """Pretty-print aggregation results."""
    print(f"\n{'=' * 50}")
    print(f"  {name}")
    print(f"{'=' * 50}")
    print(f"  Runs:       {stats['num_runs']}")
    print(f"  Mean:       {stats['mean']:.4f}")
    print(f"  Std Dev:    {stats['std']:.4f}")
    print(f"  Min:        {stats['min']:.4f}")
    print(f"  Max:        {stats['max']:.4f}")
    if stats["num_runs"] > 1:
        print(f"  95% CI:     +/- {stats['ci_95']:.4f}")
    print(f"  Scores:     {[f'{s:.4f}' for s in stats['scores']]}")
    print(f"{'=' * 50}\n")
