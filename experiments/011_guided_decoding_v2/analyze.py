"""Experiment 011: 跨 Track 分析与中文报告生成.

读取 results/ 目录下所有 JSON 文件，生成中文 Markdown 报告。

Usage:
    python -m experiments.011_guided_decoding_v2.analyze
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
REPORT_PATH = RESULTS_DIR / "analysis.md"

DATASETS = ["gsm8k", "banking77", "fewnerd", "recipe"]
ENUM_COUNTS = {"gsm8k": 0, "banking77": 77, "fewnerd": 8, "recipe": 0}
SCHEMA_COMPLEXITY = {
    "gsm8k": "L1 单字段",
    "banking77": "L2 单enum",
    "fewnerd": "L3 对象数组+enum",
    "recipe": "L4 嵌套多字段",
}
DATASET_NAMES = {
    "gsm8k": "GSM8K (推理)",
    "banking77": "BANKING77 (77类意图)",
    "fewnerd": "Few-NERD (NER 8类实体)",
    "recipe": "Recipe (食谱解析)",
}
DIFFICULTIES = ["easy", "medium", "hard"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_results() -> dict[str, list[dict]]:
    """Load all results, keyed by dataset."""
    all_data: dict[str, list[dict]] = {}
    for dataset in DATASETS:
        ds_dir = RESULTS_DIR / dataset
        if not ds_dir.exists():
            continue
        records = []
        for path in sorted(ds_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    records.extend(data)
            except Exception:
                pass
        if records:
            all_data[dataset] = records
    return all_data


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _group_by(records: list[dict], *keys: str) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = tuple(r.get(k, "unknown") for k in keys)
        groups.setdefault(key, []).append(r)
    return groups


def _accuracy(records: list[dict]) -> tuple[float, int, int]:
    total = len(records)
    correct = sum(1 for r in records if r.get("correct"))
    return (correct / total if total else 0.0), correct, total


def _parse_rate(records: list[dict]) -> float:
    total = len(records)
    parsed = sum(1 for r in records if r.get("parse_success"))
    return parsed / total if total else 0.0


def _avg_latency(records: list[dict]) -> float:
    lats = [r["latency_s"] for r in records if r.get("latency_s")]
    return sum(lats) / len(lats) if lats else 0.0


def _avg_tokens(records: list[dict]) -> float:
    toks = [r["output_tokens"] for r in records if r.get("output_tokens")]
    return sum(toks) / len(toks) if toks else 0.0


def _pct(rate: float) -> str:
    return f"{rate:.1%}"


def _delta_pp(a: float, b: float) -> str:
    diff = (a - b) * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}pp"


def _structure_valid_rate(records: list[dict]) -> float:
    total = len(records)
    valid = sum(1 for r in records if r.get("structure_valid", r.get("parse_success", False)))
    return valid / total if total else 0.0


def _format_matrix(records: list[dict]) -> dict[str, int]:
    """Compute 2×2 format × content matrix."""
    full_success = 0
    semantic_failure = 0
    format_failure = 0
    total_failure = 0

    for r in records:
        sv = r.get("structure_valid", r.get("parse_success", False))
        # Content correct: use correct (from valid parse) or fallback
        cc = r.get("correct", False) or r.get("content_correct_fallback", False)

        if sv and cc:
            full_success += 1
        elif sv and not cc:
            semantic_failure += 1
        elif not sv and cc:
            format_failure += 1
        else:
            total_failure += 1

    return {
        "full_success": full_success,
        "semantic_failure": semantic_failure,
        "format_failure": format_failure,
        "total_failure": total_failure,
        "total": len(records),
    }


def _avg_entity_f1(records: list[dict]) -> float:
    f1s = [r["entity_f1"] for r in records if r.get("entity_f1") is not None]
    return sum(f1s) / len(f1s) if f1s else 0.0


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(all_data: dict[str, list[dict]]) -> str:
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# 实验 011：Guided Decoding — 任务复杂度 × Enum 规模 — 分析报告\n")
    lines.append(f"**生成时间**：{now}\n")

    # Collect models
    models = set()
    for records in all_data.values():
        for r in records:
            models.add(r.get("model", "unknown"))
    models_str = ", ".join(sorted(models))
    lines.append(f"**模型**：{models_str}\n")
    lines.append("---\n")

    # ===== Track 1: GSM8K =====
    if "gsm8k" in all_data:
        lines.append("## Track 1: GSM8K — 推理 × 约束\n")
        _report_gsm8k(lines, all_data["gsm8k"])

    # ===== Track 2: Classification =====
    track2_datasets = [ds for ds in ["banking77"] if ds in all_data]
    if track2_datasets:
        lines.append("## Track 2: 分类 — Enum 规模 × 约束\n")
        _report_classification(lines, all_data, track2_datasets)

    # ===== Track 3: NER =====
    if "fewnerd" in all_data:
        lines.append("## Track 3: Few-NERD NER — 复杂结构 × 约束\n")
        _report_ner(lines, all_data["fewnerd"])

    # ===== Track 4: Recipe =====
    if "recipe" in all_data:
        lines.append("## Track 4: Recipe — 嵌套多字段 × 约束\n")
        _report_recipe(lines, all_data["recipe"])

    # ===== 2×2 Format × Content Matrix =====
    lines.append("## 2×2 评估矩阵：Format × Content\n")
    _report_format_matrix(lines, all_data)

    # ===== Hypothesis verification =====
    lines.append("## 假设验证总结\n")
    _report_hypotheses(lines, all_data)

    return "\n".join(lines)


def _report_gsm8k(lines: list[str], records: list[dict]) -> None:
    by_model_cond = _group_by(records, "model", "condition")

    # Table 1: Overall by model × condition
    lines.append("### 总体结果\n")
    lines.append("| 模型 | 条件 | 准确率 | Parse率 | 平均延迟 | 平均输出token |")
    lines.append("|------|------|--------|---------|----------|--------------|")

    for (model, condition), group in sorted(by_model_cond.items()):
        acc, correct, total = _accuracy(group)
        parse = _parse_rate(group)
        lat = _avg_latency(group)
        tok = _avg_tokens(group)
        lines.append(
            f"| {model} | {condition} | {_pct(acc)} ({correct}/{total}) "
            f"| {_pct(parse)} | {lat:.2f}s | {tok:.0f} |"
        )
    lines.append("")

    # Table 2: By difficulty
    lines.append("### 按难度分级\n")
    lines.append("| 模型 | 条件 | Easy | Medium | Hard |")
    lines.append("|------|------|------|--------|------|")

    for (model, condition), group in sorted(by_model_cond.items()):
        by_diff = _group_by(group, "difficulty")
        cells = []
        for d in DIFFICULTIES:
            sub = by_diff.get((d,), [])
            if sub:
                acc, c, t = _accuracy(sub)
                cells.append(f"{_pct(acc)} ({c}/{t})")
            else:
                cells.append("N/A")
        lines.append(f"| {model} | {condition} | {' | '.join(cells)} |")
    lines.append("")

    # Key comparison: thinking value
    lines.append("### 关键对比\n")
    for model in sorted(set(r.get("model") for r in records)):
        model_records = [r for r in records if r.get("model") == model]
        by_cond = {c: [r for r in model_records if r["condition"] == c]
                   for c in ["prompt_nothink", "prompt_think", "guided_nothink"]}

        for cond_name, group in by_cond.items():
            if not group:
                continue

        pn = by_cond.get("prompt_nothink", [])
        pt = by_cond.get("prompt_think", [])
        gn = by_cond.get("guided_nothink", [])

        if pn and pt:
            pn_acc = _accuracy(pn)[0]
            pt_acc = _accuracy(pt)[0]
            lines.append(f"- **{model}** thinking 价值: {_delta_pp(pt_acc, pn_acc)} "
                         f"(prompt_think {_pct(pt_acc)} vs prompt_nothink {_pct(pn_acc)})")
        if pn and gn:
            pn_acc = _accuracy(pn)[0]
            gn_acc = _accuracy(gn)[0]
            lines.append(f"- **{model}** guided 代价: {_delta_pp(gn_acc, pn_acc)} "
                         f"(guided_nothink {_pct(gn_acc)} vs prompt_nothink {_pct(pn_acc)})")
    lines.append("")


def _report_classification(
    lines: list[str],
    all_data: dict[str, list[dict]],
    datasets: list[str],
) -> None:
    for dataset in datasets:
        records = all_data[dataset]
        ds_name = DATASET_NAMES[dataset]
        enum_count = ENUM_COUNTS[dataset]
        lines.append(f"### {ds_name} ({enum_count} enum)\n")

        by_model_cond = _group_by(records, "model", "condition")

        # Overall
        lines.append("| 模型 | 条件 | 准确率 | Parse率 | 平均延迟 |")
        lines.append("|------|------|--------|---------|----------|")
        for (model, condition), group in sorted(by_model_cond.items()):
            acc, c, t = _accuracy(group)
            parse = _parse_rate(group)
            lat = _avg_latency(group)
            lines.append(f"| {model} | {condition} | {_pct(acc)} ({c}/{t}) | {_pct(parse)} | {lat:.2f}s |")
        lines.append("")

        # By difficulty
        lines.append(f"**按难度分级**\n")
        lines.append("| 模型 | 条件 | Easy | Medium | Hard |")
        lines.append("|------|------|------|--------|------|")
        for (model, condition), group in sorted(by_model_cond.items()):
            by_diff = _group_by(group, "difficulty")
            cells = []
            for d in DIFFICULTIES:
                sub = by_diff.get((d,), [])
                if sub:
                    acc, c, t = _accuracy(sub)
                    cells.append(f"{_pct(acc)} ({c}/{t})")
                else:
                    cells.append("N/A")
            lines.append(f"| {model} | {condition} | {' | '.join(cells)} |")
        lines.append("")


def _report_enum_scale(
    lines: list[str],
    all_data: dict[str, list[dict]],
    datasets: list[str],
) -> None:
    lines.append("| 数据集 | Enum数 | 模型 | prompt准确率 | guided准确率 | Delta |")
    lines.append("|--------|--------|------|-------------|-------------|-------|")

    for dataset in datasets:
        records = all_data[dataset]
        enum_count = ENUM_COUNTS[dataset]
        ds_name = DATASET_NAMES[dataset]

        by_model = _group_by(records, "model")
        for (model,), model_records in sorted(by_model.items()):
            prompt_recs = [r for r in model_records if r["condition"] == "prompt_nothink"]
            guided_recs = [r for r in model_records if r["condition"] == "guided_nothink"]

            p_acc = _accuracy(prompt_recs)[0] if prompt_recs else 0
            g_acc = _accuracy(guided_recs)[0] if guided_recs else 0
            delta = _delta_pp(g_acc, p_acc)

            lines.append(
                f"| {ds_name} | {enum_count} | {model} "
                f"| {_pct(p_acc)} | {_pct(g_acc)} | {delta} |"
            )
    lines.append("")

    # Difficulty interaction (H4)
    lines.append("### 难度交互 (H4)\n")
    lines.append("| 数据集 | 难度 | 模型 | prompt Acc | guided Acc | Delta |")
    lines.append("|--------|------|------|-----------|------------|-------|")

    for dataset in datasets:
        records = all_data[dataset]
        by_model = _group_by(records, "model")
        for (model,), model_records in sorted(by_model.items()):
            for diff in DIFFICULTIES:
                prompt_sub = [r for r in model_records
                              if r["condition"] == "prompt_nothink" and r.get("difficulty") == diff]
                guided_sub = [r for r in model_records
                              if r["condition"] == "guided_nothink" and r.get("difficulty") == diff]
                if not prompt_sub and not guided_sub:
                    continue
                p_acc = _accuracy(prompt_sub)[0] if prompt_sub else 0
                g_acc = _accuracy(guided_sub)[0] if guided_sub else 0
                delta = _delta_pp(g_acc, p_acc)
                lines.append(
                    f"| {DATASET_NAMES[dataset]} | {diff} | {model} "
                    f"| {_pct(p_acc)} | {_pct(g_acc)} | {delta} |"
                )
    lines.append("")


def _report_ner(lines: list[str], records: list[dict]) -> None:
    by_model_cond = _group_by(records, "model", "condition")

    # Overall
    lines.append("### 总体结果\n")
    lines.append("| 模型 | 条件 | Entity F1 | 准确率(F1≥0.8) | 结构有效率 | Parse率 | 平均延迟 |")
    lines.append("|------|------|-----------|---------------|-----------|---------|----------|")
    for (model, condition), group in sorted(by_model_cond.items()):
        f1 = _avg_entity_f1(group)
        acc, c, t = _accuracy(group)
        sv = _structure_valid_rate(group)
        parse = _parse_rate(group)
        lat = _avg_latency(group)
        lines.append(
            f"| {model} | {condition} | {f1:.3f} | {_pct(acc)} ({c}/{t}) "
            f"| {_pct(sv)} | {_pct(parse)} | {lat:.2f}s |"
        )
    lines.append("")

    # By difficulty
    lines.append("### 按难度分级\n")
    lines.append("| 模型 | 条件 | Easy F1 | Medium F1 | Hard F1 |")
    lines.append("|------|------|---------|-----------|---------|")
    for (model, condition), group in sorted(by_model_cond.items()):
        by_diff = _group_by(group, "difficulty")
        cells = []
        for d in DIFFICULTIES:
            sub = by_diff.get((d,), [])
            if sub:
                f1 = _avg_entity_f1(sub)
                cells.append(f"{f1:.3f}")
            else:
                cells.append("N/A")
        lines.append(f"| {model} | {condition} | {' | '.join(cells)} |")
    lines.append("")


def _report_recipe(lines: list[str], records: list[dict]) -> None:
    by_model_cond = _group_by(records, "model", "condition")

    lines.append("### 总体结果\n")
    lines.append("| 模型 | 条件 | 准确率(≥0.7) | 结构有效率 | Parse率 | 平均延迟 | 平均输出token |")
    lines.append("|------|------|-------------|-----------|---------|----------|--------------|")
    for (model, condition), group in sorted(by_model_cond.items()):
        acc, c, t = _accuracy(group)
        sv = _structure_valid_rate(group)
        parse = _parse_rate(group)
        lat = _avg_latency(group)
        tok = _avg_tokens(group)
        lines.append(
            f"| {model} | {condition} | {_pct(acc)} ({c}/{t}) "
            f"| {_pct(sv)} | {_pct(parse)} | {lat:.2f}s | {tok:.0f} |"
        )
    lines.append("")

    # By difficulty
    lines.append("### 按难度分级\n")
    lines.append("| 模型 | 条件 | Easy | Medium | Hard |")
    lines.append("|------|------|------|--------|------|")
    for (model, condition), group in sorted(by_model_cond.items()):
        by_diff = _group_by(group, "difficulty")
        cells = []
        for d in DIFFICULTIES:
            sub = by_diff.get((d,), [])
            if sub:
                acc, c, t = _accuracy(sub)
                cells.append(f"{_pct(acc)} ({c}/{t})")
            else:
                cells.append("N/A")
        lines.append(f"| {model} | {condition} | {' | '.join(cells)} |")
    lines.append("")


def _report_format_matrix(lines: list[str], all_data: dict[str, list[dict]]) -> None:
    """Generate 2×2 format × content matrix for all datasets."""
    lines.append("每个单元格: Full Success / Semantic Failure / Format Failure / Total Failure\n")
    lines.append("| 数据集 | Schema复杂度 | 条件 | 模型 | FullSuccess | SemanticFail | FormatFail | TotalFail | 结构有效率 |")
    lines.append("|--------|-------------|------|------|-------------|-------------|------------|-----------|-----------|")

    for dataset in DATASETS:
        if dataset not in all_data:
            continue
        records = all_data[dataset]
        complexity = SCHEMA_COMPLEXITY[dataset]
        ds_name = DATASET_NAMES[dataset]
        by_model_cond = _group_by(records, "model", "condition")

        for (model, condition), group in sorted(by_model_cond.items()):
            m = _format_matrix(group)
            t = m["total"]
            sv_rate = (m["full_success"] + m["semantic_failure"]) / t if t else 0
            lines.append(
                f"| {ds_name} | {complexity} | {condition} | {model} "
                f"| {m['full_success']}/{t} | {m['semantic_failure']}/{t} "
                f"| {m['format_failure']}/{t} | {m['total_failure']}/{t} "
                f"| {_pct(sv_rate)} |"
            )
    lines.append("")

    # Cross-complexity summary
    lines.append("### 结构复杂度 × Format Failure 对比\n")
    lines.append("| Schema复杂度 | 数据集 | prompt结构有效率 | guided结构有效率 | prompt FormatFail率 |")
    lines.append("|-------------|--------|-----------------|-----------------|-------------------|")
    for dataset in DATASETS:
        if dataset not in all_data:
            continue
        records = all_data[dataset]
        complexity = SCHEMA_COMPLEXITY[dataset]
        ds_name = DATASET_NAMES[dataset]

        prompt_recs = [r for r in records if r["condition"] == "prompt_nothink"]
        guided_recs = [r for r in records if r["condition"] == "guided_nothink"]

        p_sv = _structure_valid_rate(prompt_recs) if prompt_recs else 0
        g_sv = _structure_valid_rate(guided_recs) if guided_recs else 0
        p_matrix = _format_matrix(prompt_recs) if prompt_recs else {"format_failure": 0, "total": 0}
        ff_rate = p_matrix["format_failure"] / p_matrix["total"] if p_matrix["total"] else 0

        lines.append(
            f"| {complexity} | {ds_name} | {_pct(p_sv)} | {_pct(g_sv)} | {_pct(ff_rate)} |"
        )
    lines.append("")


def _report_hypotheses(lines: list[str], all_data: dict[str, list[dict]]) -> None:
    lines.append("| 假设 | 内容 | 验证结果 |")
    lines.append("|------|------|----------|")
    lines.append("| H1 | 简单 schema（GSM8K integer）guided 无语义退化 | 待分析 |")
    lines.append("| H2 | thinking 显著提升推理准确率 | 待分析 |")
    lines.append("| H3 | enum 惩罚随 enum 数量递增（5→28→77） | 待分析 |")
    lines.append("| H4 | Hard 任务 guided 退化更严重 | 待分析 |")
    lines.append("| H5 | 14B guided 惩罚 < 8B | 待分析 |")
    lines.append("| H6 | 复杂 schema（NER 对象数组）prompt format failure 率显著高于简单 schema | 待分析 |")
    lines.append("| H7 | NER 上 guided 的 format 保障收益大于语义代价（net positive） | 待分析 |")
    lines.append("| H8 | format failure 中 >30% 任务答案本身正确（format_failure 类别） | 待分析 |")
    lines.append("")
    lines.append("*注：以上待分析项需根据实际数据填写。运行 analyze.py 查看表格后手动更新。*\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    all_data = load_all_results()
    if not all_data:
        print("No results found. Run the experiment first.")
        return

    for ds, records in all_data.items():
        print(f"[loaded] {ds}: {len(records)} records")

    report = generate_report(all_data)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")
    print("\n" + report)


if __name__ == "__main__":
    main()
