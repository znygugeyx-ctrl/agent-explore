"""Experiment 006: Cross-model analysis of guided decoding vs prompt-only.

Reads results from experiments/006_model_scale/results/<model>/*.json and generates
a Chinese cross-model comparison report.

Usage:
    python3 experiments/006_model_scale/analyze.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
REPORT_PATH = RESULTS_DIR / "report.md"

MODEL_ORDER = ["qwen3-0.6b", "qwen3-1.7b", "qwen3-4b", "qwen3-8b", "qwen3-14b"]
MODEL_PARAMS = {
    "qwen3-0.6b": "0.6B", "qwen3-1.7b": "1.7B", "qwen3-4b": "4B",
    "qwen3-8b": "8B", "qwen3-14b": "14B",
}
STRATEGIES = ["free", "prompt", "guided"]
SUBGROUPS = {
    "clear": "A 清晰",
    "role_ambiguity": "B1 role歧义",
    "available_ambiguity": "B2 available歧义",
    "age_ambiguity": "B3 age近似",
    "missing_age": "C1 缺失age",
    "missing_available": "C2 缺失available",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_model_results(model_dir: Path) -> list[dict]:
    """Load all run JSON files for a model directory."""
    records = []
    for path in sorted(model_dir.glob("*.json")):
        if path.name == "report.md":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                records.extend(data)
        except Exception:
            pass
    return records


@dataclass
class FieldStats:
    correct: int = 0
    total: int = 0

    @property
    def rate(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def pct(self) -> str:
        if self.total == 0:
            return "N/A"
        return f"{self.rate:.0%} ({self.correct}/{self.total})"


@dataclass
class StrategyStats:
    parse_ok: int = 0
    schema_ok: int = 0
    total: int = 0
    latency_sum: float = 0.0
    tokens_sum: int = 0
    # field accuracy per subgroup
    subgroup_fields: dict[str, dict[str, FieldStats]] = field(default_factory=dict)

    @property
    def parse_rate(self) -> float:
        return self.parse_ok / self.total if self.total else 0.0

    @property
    def schema_rate(self) -> float:
        return self.schema_ok / self.total if self.total else 0.0

    @property
    def avg_latency(self) -> float:
        return self.latency_sum / self.total if self.total else 0.0

    @property
    def avg_tokens(self) -> float:
        return self.tokens_sum / self.total if self.total else 0.0


def aggregate(records: list[dict]) -> dict[str, StrategyStats]:
    """Aggregate records by strategy."""
    stats: dict[str, StrategyStats] = {s: StrategyStats() for s in STRATEGIES}

    for r in records:
        strategy = r.get("strategy", "")
        if strategy not in stats:
            continue
        s = stats[strategy]
        s.total += 1
        s.parse_ok += 1 if r.get("parse_success") else 0
        s.schema_ok += 1 if r.get("schema_valid") else 0
        s.latency_sum += r.get("latency_s", 0.0)
        s.tokens_sum += r.get("output_tokens", 0)

        subgroup = r.get("subgroup", "unknown")
        if subgroup not in s.subgroup_fields:
            s.subgroup_fields[subgroup] = {}

        fields_eval = r.get("field_results", {})
        for fname, fdata in fields_eval.items():
            if fname not in s.subgroup_fields[subgroup]:
                s.subgroup_fields[subgroup][fname] = FieldStats()
            fs = s.subgroup_fields[subgroup][fname]
            fs.total += 1
            correct = fdata.get("correct") if isinstance(fdata, dict) else fdata
            if correct is True:
                fs.correct += 1

    return stats


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def fmt_pct(num: int, denom: int) -> str:
    if denom == 0:
        return "N/A"
    return f"{num/denom:.0%} ({num}/{denom})"


def compute_guided_benefit(
    guided_stats: StrategyStats,
    prompt_stats: StrategyStats,
    subgroup: str,
    field_name: str,
) -> str:
    """Compute guided - prompt accuracy difference for a field in a subgroup."""
    guided_sg = guided_stats.subgroup_fields.get(subgroup, {})
    prompt_sg = prompt_stats.subgroup_fields.get(subgroup, {})
    gf = guided_sg.get(field_name)
    pf = prompt_sg.get(field_name)
    if gf is None or pf is None or gf.total == 0 or pf.total == 0:
        return "N/A"
    diff = gf.rate - pf.rate
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.0%}"


def generate_report(all_model_stats: dict[str, dict[str, StrategyStats]]) -> str:
    lines = []
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# 实验 006：Guided Decoding × 模型规模 — 跨模型对比报告")
    lines.append(f"\n生成时间：{now}\n")
    lines.append("模型：Qwen3 系列（0.6B / 1.7B / 4B / 8B），复用实验 005 的 30 个任务 + 3 个策略\n")
    lines.append("---\n")

    # H1: Parse success rates across models
    lines.append("## H1：结构正确性 vs 模型规模\n")
    header = "| 模型 | 策略 | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |"
    sep    = "|------|------|----------------|------------------|----------|----------------|"
    lines.append(header)
    lines.append(sep)
    for model in MODEL_ORDER:
        if model not in all_model_stats:
            continue
        params = MODEL_PARAMS[model]
        for strategy in STRATEGIES:
            s = all_model_stats[model].get(strategy)
            if s is None or s.total == 0:
                lines.append(f"| {params} | {strategy} | N/A | N/A | N/A | N/A |")
            else:
                lines.append(
                    f"| {params} | {strategy} "
                    f"| {fmt_pct(s.parse_ok, s.total)} "
                    f"| {fmt_pct(s.schema_ok, s.total)} "
                    f"| {s.avg_latency:.2f}s "
                    f"| {s.avg_tokens:.0f} |"
                )
    lines.append("")

    # H2: Guided benefit on B1 role (key metric)
    lines.append("## H2：Guided 净收益（guided - prompt 准确率差）\n")
    lines.append("正数 = guided 更好；负数 = guided 更差\n")

    benefit_fields = [
        ("role_ambiguity", "role", "B1 role 歧义"),
        ("clear", "role", "A role 清晰"),
        ("age_ambiguity", "age", "B3 age 近似"),
        ("available_ambiguity", "available", "B2 available 歧义"),
    ]
    header2 = "| 模型 | " + " | ".join(label for _, _, label in benefit_fields) + " |"
    sep2 = "|------|" + "|".join("---" for _ in benefit_fields) + "|"
    lines.append(header2)
    lines.append(sep2)
    for model in MODEL_ORDER:
        if model not in all_model_stats:
            continue
        params = MODEL_PARAMS[model]
        row = [params]
        for subgroup, fname, _ in benefit_fields:
            guided = all_model_stats[model].get("guided", StrategyStats())
            prompt = all_model_stats[model].get("prompt", StrategyStats())
            row.append(compute_guided_benefit(guided, prompt, subgroup, fname))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Per-model subgroup accuracy
    lines.append("## 各模型分组字段准确率\n")
    for model in MODEL_ORDER:
        if model not in all_model_stats:
            continue
        params = MODEL_PARAMS[model]
        lines.append(f"### {params}\n")

        for subgroup, sg_label in SUBGROUPS.items():
            # Collect all fields that appear in this subgroup across strategies
            all_fields: set[str] = set()
            for strategy in ["prompt", "guided"]:
                s = all_model_stats[model].get(strategy)
                if s:
                    all_fields.update(s.subgroup_fields.get(subgroup, {}).keys())
            if not all_fields:
                continue

            sorted_fields = sorted(all_fields)
            lines.append(f"**{sg_label}**\n")
            header3 = "| 策略 | " + " | ".join(sorted_fields) + " |"
            sep3 = "|------|" + "|".join("---" for _ in sorted_fields) + "|"
            lines.append(header3)
            lines.append(sep3)
            for strategy in STRATEGIES:
                s = all_model_stats[model].get(strategy)
                if s is None:
                    continue
                sg = s.subgroup_fields.get(subgroup, {})
                if not sg and strategy == "free":
                    row_vals = ["N/A"] * len(sorted_fields)
                else:
                    row_vals = []
                    for fn in sorted_fields:
                        fs = sg.get(fn)
                        row_vals.append(fs.pct() if fs else "N/A")
                lines.append("| " + strategy + " | " + " | ".join(row_vals) + " |")
            lines.append("")

    # Summary
    lines.append("---\n")
    lines.append("## 总结\n")
    lines.append("### 核心发现\n")

    # Parse rate progression
    lines.append("**结构正确性（prompt parse 率）**\n")
    for model in MODEL_ORDER:
        if model not in all_model_stats:
            continue
        params = MODEL_PARAMS[model]
        p = all_model_stats[model].get("prompt")
        g = all_model_stats[model].get("guided")
        p_str = fmt_pct(p.parse_ok, p.total) if p and p.total else "N/A"
        g_str = fmt_pct(g.parse_ok, g.total) if g and g.total else "N/A"
        lines.append(f"- {params}: prompt={p_str}, guided={g_str}")
    lines.append("")

    lines.append("**B1 role 歧义准确率（guided 净收益趋势）**\n")
    for model in MODEL_ORDER:
        if model not in all_model_stats:
            continue
        params = MODEL_PARAMS[model]
        guided = all_model_stats[model].get("guided", StrategyStats())
        prompt = all_model_stats[model].get("prompt", StrategyStats())
        benefit = compute_guided_benefit(guided, prompt, "role_ambiguity", "role")
        g_sg = guided.subgroup_fields.get("role_ambiguity", {}).get("role")
        p_sg = prompt.subgroup_fields.get("role_ambiguity", {}).get("role")
        g_str = g_sg.pct() if g_sg else "N/A"
        p_str = p_sg.pct() if p_sg else "N/A"
        lines.append(f"- {params}: prompt={p_str}, guided={g_str}, benefit={benefit}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    all_model_stats: dict[str, dict[str, StrategyStats]] = {}

    for model in MODEL_ORDER:
        model_dir = RESULTS_DIR / model
        if not model_dir.exists():
            print(f"[skip] {model}: directory not found")
            continue
        records = load_model_results(model_dir)
        if not records:
            print(f"[skip] {model}: no records found")
            continue
        stats = aggregate(records)
        all_model_stats[model] = stats
        total = stats["prompt"].total + stats["guided"].total
        print(f"[loaded] {model}: {len(records)} records ({total} prompt+guided calls)")

    if not all_model_stats:
        print("No results found. Run run_all.sh first.")
        return

    report = generate_report(all_model_stats)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {REPORT_PATH}")
    print("\n" + report)


if __name__ == "__main__":
    main()
