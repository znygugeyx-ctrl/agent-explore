"""统一评分 + 对比报告生成。

复用 013 的 LLM Judge 逻辑，支持多方案 × 多档位的对比。

Usage:
    python3 d2l_baseline/analyze.py --results_dir d2l_baseline/results/
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import boto3
import numpy as np

JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def build_score_prompt(gold, pred, query):
    return f"""根据预测答案与真实答案在问题语境下的准确性、完整性和相关性，给出0到5的客观评分。

评分标准：
5: 完全一致，正确回答。
4: 核心信息正确，略有冗余。
3: 基本正确但有偏差或不完整。
2: 部分相关，遗漏重要信息。
1: 方向正确但事实错误。
0: 完全不相关或幻觉。

问题：{query}
真实答案：{gold}
预测答案：{pred}

只输出一个数字（0-5）："""


def judge(prompt):
    try:
        r = bedrock.converse(
            modelId=JUDGE_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 16},
        )
        text = r["output"]["message"]["content"][0]["text"].strip()
        for c in text:
            if c.isdigit() and int(c) <= 5:
                return int(c)
    except Exception as e:
        print(f"  Judge error: {e}")
    return 0


def score_results(records, answer_key):
    prompts = [
        build_score_prompt(r["answer"], r.get(answer_key, ""), r["question"])
        for r in records
    ]
    with ThreadPoolExecutor(max_workers=8) as ex:
        scores = list(ex.map(judge, prompts))
    for r, s in zip(records, scores):
        r["score"] = s
    return scores


def compute_stats(records, score_key="score"):
    scores = [r[score_key] for r in records]
    result = {
        "overall": float(np.mean(scores)),
        "n": len(scores),
        "distribution": dict(sorted(Counter(scores).items())),
    }

    for difficulty in ["easy", "medium", "hard"]:
        subset = [r[score_key] for r in records if r.get("difficulty") == difficulty]
        if subset:
            result[difficulty] = float(np.mean(subset))
            result[f"{difficulty}_n"] = len(subset)

    by_cat = defaultdict(list)
    for r in records:
        cat = r.get("category")
        if cat:
            by_cat[cat].append(r[score_key])
    if by_cat:
        result["by_category"] = {cat: float(np.mean(s)) for cat, s in by_cat.items()}

    return result


def find_answer_key(records):
    for key in ["d2l_answer", "icl_answer", "msa_answer", "rag_answer"]:
        if key in records[0]:
            return key
    raise ValueError(f"No answer key found in record keys: {list(records[0].keys())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results_dir", required=True)
    parser.add_argument("--force_rescore", action="store_true")
    args = parser.parse_args()

    result_files = sorted(
        f for f in os.listdir(args.results_dir)
        if f.endswith(".json") and not f.endswith("_scored.json")
        and not f.startswith("sanity_check") and f != "summary.json"
    )

    all_stats = {}

    for filename in result_files:
        path = os.path.join(args.results_dir, filename)
        scored_path = path.replace(".json", "_scored.json")

        if os.path.exists(scored_path) and not args.force_rescore:
            print(f"Loading scored: {filename}")
            with open(scored_path, encoding="utf-8") as f:
                records = json.load(f)
        else:
            print(f"Scoring: {filename}")
            with open(path, encoding="utf-8") as f:
                records = json.load(f)
            if not records:
                continue
            answer_key = find_answer_key(records)
            score_results(records, answer_key)
            with open(scored_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

        name = filename.removesuffix(".json")
        stats = compute_stats(records)
        all_stats[name] = stats

        print(f"  {name}: overall={stats['overall']:.3f} (n={stats['n']})")
        for d in ["easy", "medium", "hard"]:
            if d in stats:
                print(f"    {d}: {stats[d]:.3f} (n={stats.get(f'{d}_n', '?')})")

    # Generate report
    report = generate_report(all_stats)
    report_path = os.path.join(args.results_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport: {report_path}")

    summary_path = os.path.join(args.results_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)


def generate_report(all_stats):
    lines = ["# D2L Baseline 对比报告\n"]

    # Group by dataset
    hotpotqa = {k: v for k, v in all_stats.items() if "hotpotqa" in k}
    novel = {k: v for k, v in all_stats.items() if "novel" in k}

    if hotpotqa:
        lines.append("## HotpotQA\n")
        lines.append("| Condition | Overall | N |")
        lines.append("|---|---|---|")
        for name, s in sorted(hotpotqa.items()):
            lines.append(f"| {name} | **{s['overall']:.3f}** | {s['n']} |")

    if novel:
        lines.append("\n## 小说 QA\n")
        lines.append("| Condition | Overall | Easy | Medium | Hard | N |")
        lines.append("|---|---|---|---|---|---|")
        for name, s in sorted(novel.items()):
            easy = f"{s['easy']:.3f}" if "easy" in s else "—"
            med = f"{s['medium']:.3f}" if "medium" in s else "—"
            hard = f"{s['hard']:.3f}" if "hard" in s else "—"
            lines.append(
                f"| {name} | **{s['overall']:.3f}** | {easy} | {med} | {hard} | {s['n']} |"
            )

        all_cats = set()
        for s in novel.values():
            all_cats.update(s.get("by_category", {}).keys())
        if all_cats:
            lines.append("\n### 按类别\n")
            header = "| Category |" + "|".join(f" {n} " for n in sorted(novel)) + "|"
            sep = "|---|" + "|".join(["---"] * len(novel)) + "|"
            lines.append(header)
            lines.append(sep)
            for cat in sorted(all_cats):
                row = f"| {cat} |"
                for name in sorted(novel):
                    val = novel[name].get("by_category", {}).get(cat)
                    row += f" {val:.3f} |" if val is not None else " — |"
                lines.append(row)

    return "\n".join(lines)


if __name__ == "__main__":
    main()
