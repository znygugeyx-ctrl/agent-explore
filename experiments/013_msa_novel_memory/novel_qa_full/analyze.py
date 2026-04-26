"""分析所有实验结果，生成对比报告。

Usage:
    python3 novel_qa_full/analyze.py
"""
import json
import os
import sys
from collections import Counter, defaultdict

import boto3
import numpy as np
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
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
    """Score a list of records using LLM judge."""
    prompts = [build_score_prompt(r["answer"], r.get(answer_key, ""), r["question"]) for r in records]
    with ThreadPoolExecutor(max_workers=8) as ex:
        scores = list(ex.map(judge, prompts))
    for r, s in zip(records, scores):
        r["score"] = s
    return scores


def print_analysis(name, records, score_key="score"):
    scores = [r[score_key] for r in records]
    easy = [r[score_key] for r in records if r.get("difficulty") == "easy"]
    medium = [r[score_key] for r in records if r.get("difficulty") == "medium"]
    hard = [r[score_key] for r in records if r.get("difficulty") == "hard"]

    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    print(f"  Overall: {np.mean(scores):.3f} (n={len(scores)})")
    if easy: print(f"  Easy:    {np.mean(easy):.3f} (n={len(easy)})")
    if medium: print(f"  Medium:  {np.mean(medium):.3f} (n={len(medium)})")
    if hard: print(f"  Hard:    {np.mean(hard):.3f} (n={len(hard)})")

    by_cat = defaultdict(list)
    for r in records:
        by_cat[r.get("category", "unknown")].append(r[score_key])
    print(f"\n  By category:")
    for cat in sorted(by_cat):
        print(f"    {cat:15s}: {np.mean(by_cat[cat]):.3f} (n={len(by_cat[cat])})")

    dist = Counter(scores)
    print(f"\n  Distribution: {dict(sorted(dist.items()))}")

    return {
        "overall": float(np.mean(scores)),
        "easy": float(np.mean(easy)) if easy else None,
        "medium": float(np.mean(medium)) if medium else None,
        "hard": float(np.mean(hard)) if hard else None,
        "by_category": {cat: float(np.mean(s)) for cat, s in by_cat.items()},
        "distribution": dict(sorted(dist.items())),
        "n": len(scores),
    }


def main():
    conditions = {}

    # Load each result file if it exists
    for name, filename, answer_key in [
        ("MSA-EN", "msa_en_results.json", "msa_answer"),
        ("MSA-CN", "msa_cn_results.json", "msa_answer"),
        ("RAG-CN", "rag_results.json", "rag_answer"),
    ]:
        path = os.path.join(RESULTS_DIR, filename)
        if not os.path.exists(path):
            print(f"Skipping {name}: {filename} not found")
            continue

        print(f"\nScoring {name}...")
        with open(path, encoding="utf-8") as f:
            records = json.load(f)

        scores = score_results(records, answer_key)
        summary = print_analysis(name, records)
        conditions[name] = summary

        # Save scored version
        scored_path = path.replace(".json", "_scored.json")
        with open(scored_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    # Generate comparison report
    if conditions:
        report = generate_report(conditions)
        report_path = os.path.join(RESULTS_DIR, "report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to {report_path}")

    # Save summary
    summary_path = os.path.join(RESULTS_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(conditions, f, ensure_ascii=False, indent=2)


def generate_report(conditions):
    lines = ["# 全量小说 QA 实验报告\n"]
    lines.append("## 整体对比\n")
    lines.append("| 条件 | Overall | Easy | Medium | Hard | N |")
    lines.append("|---|---|---|---|---|---|")
    for name, s in conditions.items():
        easy = f"{s['easy']:.3f}" if s.get('easy') is not None else "—"
        med = f"{s['medium']:.3f}" if s.get('medium') is not None else "—"
        hard = f"{s['hard']:.3f}" if s.get('hard') is not None else "—"
        lines.append(f"| {name} | **{s['overall']:.3f}** | {easy} | {med} | {hard} | {s['n']} |")

    lines.append("\n## 按类别对比\n")
    all_cats = set()
    for s in conditions.values():
        all_cats.update(s.get("by_category", {}).keys())
    header = "| Category |" + "|".join(f" {name} " for name in conditions) + "|"
    sep = "|---|" + "|".join(["---"] * len(conditions)) + "|"
    lines.append(header)
    lines.append(sep)
    for cat in sorted(all_cats):
        row = f"| {cat} |"
        for name, s in conditions.items():
            val = s.get("by_category", {}).get(cat)
            row += f" {val:.3f} |" if val is not None else " — |"
        lines.append(row)

    lines.append("\n## 分数分布\n")
    for name, s in conditions.items():
        lines.append(f"**{name}**: {s.get('distribution', {})}\n")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
