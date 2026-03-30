"""Experiment 012 analysis: aggregate results and generate report.

Usage:
    python -m experiments.012_mask_vs_remove_v2.analyze
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_all_results() -> list[dict]:
    """Load all result JSON files from results/."""
    results = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        with open(path) as f:
            results.append(json.load(f))
    return results


def group_by_strategy_model(results: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group results by (strategy, model) across runs."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        key = (r["strategy"], r["model"])
        groups[key].append(r)
    return dict(groups)


# ── Statistics ────────────────────────────────────────────────────────────────

def mean(lst: list[float]) -> float:
    return sum(lst) / len(lst) if lst else 0.0


def aggregate_across_runs(run_results: list[dict]) -> dict:
    """Aggregate summary stats across multiple runs for one (strategy, model)."""
    summaries = [r["summary"] for r in run_results if r.get("summary")]
    if not summaries:
        return {}

    accuracies = [s["accuracy_mean"] for s in summaries if "accuracy_mean" in s]
    costs = [s["cost_mean"] for s in summaries if "cost_mean" in s]
    cache_rates = [s["cache_read_rate"] for s in summaries if "cache_read_rate" in s]
    ttfts = [s["ttft_mean"] for s in summaries if "ttft_mean" in s]
    input_toks = [s["input_tokens_mean"] for s in summaries if "input_tokens_mean" in s]

    # Per-turn TTFT across runs
    ttft_by_turn: dict[int, list[float]] = defaultdict(list)
    for s in summaries:
        for turn_str, val in s.get("ttft_by_turn", {}).items():
            ttft_by_turn[int(turn_str)].append(val)
    avg_ttft_by_turn = {k: mean(v) for k, v in sorted(ttft_by_turn.items())}

    # Cache metrics from run results
    cache_metrics_list = [r.get("cache_metrics", {}) for r in run_results]
    hit_rates = [c["hit_rate"] for c in cache_metrics_list if c.get("hit_rate") is not None]

    return {
        "n_runs": len(run_results),
        "accuracy_mean": mean(accuracies),
        "cost_mean": mean(costs),
        "input_tokens_mean": mean(input_toks),
        "cache_read_rate_mean": mean(cache_rates),
        "vllm_cache_hit_rate": mean(hit_rates) if hit_rates else None,
        "ttft_mean": mean(ttfts),
        "ttft_by_turn": avg_ttft_by_turn,
    }


# ── Report generation ─────────────────────────────────────────────────────────

def fmt_pct(v: float | None) -> str:
    return f"{v:.1%}" if v is not None else "—"

def fmt_f(v: float | None, decimals: int = 4) -> str:
    return f"{v:.{decimals}f}" if v is not None else "—"

def fmt_ms(v: float | None) -> str:
    return f"{v * 1000:.0f}ms" if v is not None else "—"


def generate_report(results: list[dict]) -> str:
    groups = group_by_strategy_model(results)
    aggregated = {k: aggregate_across_runs(v) for k, v in groups.items()}

    # Group by model for separate tables
    models = sorted({model for _, model in aggregated.keys()})
    strategies_order = ["all", "remove_static", "remove_dynamic", "mask_desc", "mask_logit"]

    lines = [
        "# Experiment 012: Mask vs Remove v2 — Results",
        "",
        f"Generated from {len(results)} result files",
        "",
    ]

    for model in models:
        lines += [f"## Model: {model}", ""]
        model_data = {strat: agg for (strat, m), agg in aggregated.items() if m == model}

        # Summary table
        lines += [
            "| Strategy | Runs | Accuracy | Cost/Task | Input Tokens | Cache Read Rate | TTFT |",
            "|----------|------|----------|-----------|--------------|-----------------|------|",
        ]
        for strat in strategies_order:
            if strat not in model_data:
                continue
            a = model_data[strat]
            lines.append(
                f"| {strat:15s} | {a['n_runs']:4d} "
                f"| {fmt_pct(a.get('accuracy_mean'))} "
                f"| ${fmt_f(a.get('cost_mean'), 5)} "
                f"| {fmt_f(a.get('input_tokens_mean'), 0)} "
                f"| {fmt_pct(a.get('cache_read_rate_mean'))} "
                f"| {fmt_ms(a.get('ttft_mean'))} |"
            )
        lines.append("")

        # vLLM cache hit rates (if available)
        vllm_rates = {s: a["vllm_cache_hit_rate"] for s, a in model_data.items()
                      if a.get("vllm_cache_hit_rate") is not None}
        if vllm_rates:
            lines += ["### vLLM Prefix Cache Hit Rates", ""]
            lines += [f"| {s:15s} | {fmt_pct(r)} |" for s, r in vllm_rates.items()]
            lines.append("")

        # Per-turn TTFT
        has_ttft = any(a.get("ttft_by_turn") for a in model_data.values())
        if has_ttft:
            max_turn = max(
                (max(int(k) for k in a["ttft_by_turn"].keys()) for a in model_data.values()
                 if a.get("ttft_by_turn")),
                default=0,
            )
            lines += ["### TTFT by Turn", ""]
            header = "| Strategy " + "".join(f"| Turn {i} " for i in range(max_turn + 1)) + "|"
            sep = "|----------" + "|--------" * (max_turn + 1) + "|"
            lines += [header, sep]
            for strat in strategies_order:
                if strat not in model_data:
                    continue
                ttft_map = model_data[strat].get("ttft_by_turn", {})
                row = f"| {strat:8s} " + "".join(f"| {fmt_ms(ttft_map.get(i))} " for i in range(max_turn + 1)) + "|"
                lines.append(row)
            lines.append("")

    # Key findings
    lines += [
        "## Key Findings",
        "",
        "### H1: Cache Economics (Claude)",
        "- TODO: compare all vs remove_dynamic cost/task on claude_haiku",
        "",
        "### H2: Dynamic Tool Change Effect",
        "- TODO: compare TTFT by turn: mask_logit vs remove_dynamic on vLLM",
        "",
        "### H3: Model Confusion",
        "- TODO: compare accuracy: all vs remove_dynamic",
        "",
        "### H4: Model Scale",
        "- TODO: compare 8B vs 14B across strategies",
    ]

    return "\n".join(lines)


def main() -> None:
    results = load_all_results()
    if not results:
        print("[error] No result files found in results/")
        return

    print(f"[analyze] Loaded {len(results)} result files")
    report = generate_report(results)

    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"[saved] {report_path}")
    print("\n" + report[:2000])


if __name__ == "__main__":
    main()
