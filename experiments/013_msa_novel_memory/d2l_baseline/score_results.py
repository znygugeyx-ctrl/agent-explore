"""给所有 RAG/MSA 结果做 LLM Judge 评分并输出初步分析。

Usage:
    python3 score_results.py
"""
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import boto3
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def build_prompt(gold, pred, query):
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


def load_and_normalize(filepath):
    """Load result file and normalize to common format."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # RAG format: flat list
        if not data:
            return []
        first = data[0]
        pred_key = None
        for k in ("rag_answer", "d2l_answer", "msa_answer", "pred_answer"):
            if k in first:
                pred_key = k
                break
        if pred_key:
            return [
                {
                    "question": r["question"],
                    "answer": r["answer"],
                    "pred": r.get(pred_key, ""),
                    "difficulty": r.get("difficulty"),
                    "category": r.get("category"),
                    "latency_ms": r.get("latency_ms"),
                }
                for r in data
            ]
    elif isinstance(data, dict):
        # MSA format
        key = list(data.keys())[0]
        records = data[key]["precision"]["record_list"]
        return [
            {
                "question": r["question"],
                "answer": r["true_answer"],
                "pred": r["pred_answer"],
                "difficulty": None,
                "category": None,
                "latency_ms": None,
            }
            for r in records
        ]
    return []


def enrich_with_metadata(records, metadata_file, dataset_type):
    """Add difficulty/category from original pool files (for novel only)."""
    if dataset_type != "novel":
        return records
    with open(metadata_file, encoding="utf-8") as f:
        meta = json.load(f)
    q_to_meta = {r["question"]: r for r in meta}
    for r in records:
        if r["question"] in q_to_meta:
            m = q_to_meta[r["question"]]
            r["difficulty"] = m.get("difficulty")
            r["category"] = m.get("category")
    return records


def score_records(records):
    prompts = [build_prompt(r["answer"], r["pred"], r["question"]) for r in records]
    with ThreadPoolExecutor(max_workers=8) as ex:
        scores = list(ex.map(judge, prompts))
    for r, s in zip(records, scores):
        r["score"] = s
    return scores


def compute_stats(records):
    scores = [r["score"] for r in records]
    out = {
        "n": len(scores),
        "mean": float(np.mean(scores)),
        "distribution": dict(sorted(Counter(scores).items())),
    }
    for diff in ["easy", "medium", "hard"]:
        subset = [r["score"] for r in records if r.get("difficulty") == diff]
        if subset:
            out[diff] = {"n": len(subset), "mean": float(np.mean(subset))}
    by_cat = defaultdict(list)
    for r in records:
        c = r.get("category")
        if c:
            by_cat[c].append(r["score"])
    if by_cat:
        out["by_category"] = {c: float(np.mean(s)) for c, s in by_cat.items()}
    return out


def main():
    files = [
        ("RAG-HotpotQA-2k", "hotpotqa_rag_2k.json", "hotpotqa"),
        ("RAG-HotpotQA-4k", "hotpotqa_rag_4k.json", "hotpotqa"),
        ("RAG-HotpotQA-8k", "hotpotqa_rag_8k.json", "hotpotqa"),
        ("RAG-Novel-8k", "novel_rag_8k.json", "novel"),
        ("MSA-HotpotQA-2k", "hotpotqa_msa_2k.json", "hotpotqa"),
        ("MSA-HotpotQA-4k", "hotpotqa_msa_4k.json", "hotpotqa"),
        ("MSA-HotpotQA-8k", "hotpotqa_msa_8k.json", "hotpotqa"),
        ("MSA-Novel-8k", "novel_msa_8k.json", "novel"),
        ("D2L-HotpotQA-2k", "hotpotqa_d2l_2k.json", "hotpotqa"),
        ("D2L-HotpotQA-4k", "hotpotqa_d2l_4k.json", "hotpotqa"),
        ("D2L-HotpotQA-8k", "hotpotqa_d2l_8k.json", "hotpotqa"),
        ("D2L-Novel-8k", "novel_d2l_8k.json", "novel"),
    ]

    novel_meta = os.path.join(
        os.path.dirname(SCRIPT_DIR),
        "d2l_baseline", "data", "novel_8k_pools.json"
    )

    all_stats = {}

    for name, fname, dstype in files:
        path = os.path.join(RESULTS_DIR, fname)
        if not os.path.exists(path):
            print(f"SKIP {name}: {fname} not found")
            continue

        scored_path = path.replace(".json", "_scored.json")
        if os.path.exists(scored_path):
            print(f"Loading cached: {name}")
            with open(scored_path, encoding="utf-8") as f:
                records = json.load(f)
        else:
            print(f"Scoring {name}...")
            records = load_and_normalize(path)
            records = enrich_with_metadata(records, novel_meta, dstype)
            score_records(records)
            with open(scored_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

        stats = compute_stats(records)
        all_stats[name] = stats
        print(f"  {name}: mean={stats['mean']:.3f} (n={stats['n']})")

    # Save summary
    summary_path = os.path.join(RESULTS_DIR, "summary_partial.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)
    print(f"\nSummary saved to {summary_path}")


if __name__ == "__main__":
    main()
