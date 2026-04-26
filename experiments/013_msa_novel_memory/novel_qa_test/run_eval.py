"""自动评估脚本：向 MSA 服务发送小说 QA 问题，收集回答并用 LLM Judge 评分。

Usage:
    python3 experiments/013_msa_novel_memory/novel_qa_test/run_eval.py [--url http://localhost:8080]
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import boto3
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QA_FILE = os.path.join(SCRIPT_DIR, "qa_pairs.json")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"


def post_json(url: str, data: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def build_score_prompt(gold_answer, model_answer, query):
    return f"""根据预测答案与真实答案在问题语境下的准确性、完整性和相关性，给出0到5的客观评分（5为最高，0为最低）。

评分标准：
5: 预测答案与真实答案完全一致，正确回答了问题。措辞差异不影响事实准确性。
4: 预测答案包含真实答案的所有核心信息，无错误，但有少量非关键冗余内容。
3: 预测答案抓住了核心信息，但在某些方面与真实答案有差异。略有不完整或不精确，但无错误。
2: 预测答案部分相关，但遗漏了大量信息或偏离了问题核心。
1: 预测答案尝试回答问题（与主题基本相关），但提供了事实错误的信息。
0: 预测答案与问题完全无关、是乱码，或是与真实答案毫无逻辑联系的幻觉。

问题：
{query}

真实答案：
{gold_answer}

预测答案：
{model_answer}

只输出一个数字（0、1、2、3、4或5）："""


def parse_score(text):
    for char in text.strip():
        if char.isdigit() and int(char) <= 5:
            return int(char)
    return 0


bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")


def judge(prompt):
    try:
        response = bedrock_client.converse(
            modelId=JUDGE_MODEL,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 16},
        )
        return response["output"]["message"]["content"][0]["text"]
    except Exception as e:
        print(f"  Judge error: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    with open(QA_FILE, encoding="utf-8") as f:
        qa_pairs = json.load(f)
    print(f"加载 {len(qa_pairs)} 个 QA 对")

    # Phase 1: 向 MSA 发送问题
    print(f"\n=== Phase 1: MSA 问答 ({base_url}) ===")
    for i, qa in enumerate(qa_pairs):
        try:
            result = post_json(f"{base_url}/ask", {"question": qa["question"]})
            qa["msa_answer"] = result["answer"]
            qa["cited_docs"] = result["cited_docs"]
            qa["latency_ms"] = result["latency_ms"]
            qa["rounds"] = result.get("rounds", -1)
            status = "OK" if qa["msa_answer"] else "EMPTY"
        except Exception as e:
            qa["msa_answer"] = ""
            qa["cited_docs"] = []
            qa["latency_ms"] = -1
            qa["rounds"] = -1
            status = f"ERR: {e}"
        print(f"  [{i+1}/{len(qa_pairs)}] {status} ({qa['latency_ms']}ms) Q: {qa['question'][:40]}...")

    # Phase 2: LLM Judge 评分
    print(f"\n=== Phase 2: LLM Judge ({JUDGE_MODEL}) ===")
    prompts = [
        build_score_prompt(qa["answer"], qa["msa_answer"], qa["question"])
        for qa in qa_pairs
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        raw_scores = list(executor.map(judge, prompts))
    for qa, raw in zip(qa_pairs, raw_scores):
        qa["score"] = parse_score(raw)

    # Phase 3: 统计和输出
    print("\n" + "=" * 60)
    print("  评估结果")
    print("=" * 60)

    scores = [qa["score"] for qa in qa_pairs]
    easy = [qa["score"] for qa in qa_pairs if qa["difficulty"] == "easy"]
    hard = [qa["score"] for qa in qa_pairs if qa["difficulty"] == "hard"]

    print(f"\n  整体 LLM Score: {np.mean(scores):.3f} (n={len(scores)})")
    print(f"  Easy:  {np.mean(easy):.3f} (n={len(easy)})")
    print(f"  Hard:  {np.mean(hard):.3f} (n={len(hard)})")

    # 按类别
    print("\n  按类别:")
    by_cat = defaultdict(list)
    for qa in qa_pairs:
        by_cat[qa["category"]].append(qa["score"])
    for cat in sorted(by_cat.keys()):
        s = by_cat[cat]
        print(f"    {cat:15s}: {np.mean(s):.3f} (n={len(s)})")

    # 分数分布
    from collections import Counter
    dist = Counter(scores)
    print(f"\n  分数分布: {dict(sorted(dist.items()))}")

    # 平均延迟
    latencies = [qa["latency_ms"] for qa in qa_pairs if qa["latency_ms"] > 0]
    if latencies:
        print(f"  平均延迟: {np.mean(latencies):.0f}ms")

    # 保存结果
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "eval_results.json")
    output = {
        "summary": {
            "overall_score": float(np.mean(scores)),
            "easy_score": float(np.mean(easy)),
            "hard_score": float(np.mean(hard)),
            "score_distribution": dict(sorted(dist.items())),
            "by_category": {cat: float(np.mean(s)) for cat, s in by_cat.items()},
            "avg_latency_ms": float(np.mean(latencies)) if latencies else -1,
            "judge_model": JUDGE_MODEL,
        },
        "records": qa_pairs,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存到 {out_path}")


if __name__ == "__main__":
    main()
