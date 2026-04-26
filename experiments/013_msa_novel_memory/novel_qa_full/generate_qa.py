"""从小说随机采样段落，用 Claude Sonnet 4.6 生成 300 个 QA 对。

Usage:
    scp mdata_novel.pkl from EC2 first, or point --pkl to the remote copy.
    python3 experiments/013_msa_novel_memory/novel_qa_full/generate_qa.py
"""
import argparse
import json
import os
import pickle
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "qa_300.json")

JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# Volume boundaries (section indices)
VOLUMES = [
    ("第一卷", 0, 199),
    ("第二三卷", 200, 649),
    ("第四五卷", 650, 1968),
    ("第六卷", 1969, 2345),
]

VOLUME_TARGETS = {
    "第一卷": 50,
    "第二三卷": 60,
    "第四五卷": 100,
    "第六卷": 90,
}

CATEGORIES = [
    "character", "item", "event", "location",
    "relationship", "reasoning", "temporal", "quote",
]

DIFFICULTY_TARGETS = {"easy": 120, "medium": 100, "hard": 80}

GENERATE_PROMPT = """你是一个中文小说阅读理解题目的生成专家。

以下是小说《蛊真人》中的一个段落（第{section_idx}节）：

---
{text}
---

请根据这段内容，生成{num_questions}个问答对。要求：

1. 问题和答案必须都是中文
2. 答案必须能从给定段落或小说常识中推断出来
3. 答案要简洁精确（通常1-3句话）
4. 每个问答对指定难度和类别

难度定义：
- easy: 答案在本段中有明确直接的表述
- medium: 需要理解上下文或综合本段多处信息
- hard: 需要跨段落的推理、因果分析或与小说其他部分的关联

可选类别: character, item, event, location, relationship, reasoning, temporal, quote

请严格按以下 JSON 格式输出（不要输出其他内容）：
[
  {{
    "question": "问题文本",
    "answer": "答案文本",
    "difficulty": "easy|medium|hard",
    "category": "类别"
  }}
]"""


def call_claude(prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            response = bedrock.converse(
                modelId=JUDGE_MODEL,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"temperature": 0.7, "maxTokens": 2048},
            )
            return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Claude error after {max_retries} retries: {e}")
                return "[]"


def parse_qa_response(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return []


def get_volume(section_idx: int) -> str:
    for name, start, end in VOLUMES:
        if start <= section_idx <= end:
            return name
    return "第六卷"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pkl", default="/tmp/mdata_novel.pkl")
    parser.add_argument("--target", type=int, default=300)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    if not os.path.exists(args.pkl):
        print(f"需要先下载小说数据: scp -i ~/.ssh/vllm-experiment-key.pem ubuntu@<IP>:/home/ubuntu/MSA/mdata_novel.pkl /tmp/")
        sys.exit(1)

    with open(args.pkl, "rb") as f:
        docs = pickle.load(f)
    print(f"加载 {len(docs)} 个段落")

    random.seed(42)

    # 按卷次采样段落
    all_samples = []
    for vol_name, vol_start, vol_end in VOLUMES:
        target = VOLUME_TARGETS[vol_name]
        num_samples = (target + 1) // 2  # 每段生成 ~2 题
        vol_indices = list(range(vol_start, min(vol_end + 1, len(docs))))
        selected = random.sample(vol_indices, min(num_samples, len(vol_indices)))
        for idx in selected:
            all_samples.append((idx, docs[idx], vol_name))

    print(f"采样 {len(all_samples)} 个段落，目标 {args.target} 题")

    # 生成 QA
    all_qa = []
    qa_id = 1

    def process_sample(sample):
        idx, text, vol_name = sample
        if len(text) > 3000:
            text = text[:3000]
        prompt = GENERATE_PROMPT.format(section_idx=idx, text=text, num_questions=2)
        raw = call_claude(prompt)
        pairs = parse_qa_response(raw)
        results = []
        for p in pairs:
            if "question" in p and "answer" in p:
                title = text.split("\n")[0]
                results.append({
                    "question": p["question"],
                    "answer": p["answer"],
                    "difficulty": p.get("difficulty", "easy"),
                    "category": p.get("category", "event"),
                    "source_section": title,
                    "section_idx": idx,
                    "volume": vol_name,
                })
        return results

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = list(executor.map(process_sample, all_samples))

    for batch in futures:
        for item in batch:
            item["id"] = qa_id
            all_qa.append(item)
            qa_id += 1

    # 截断到目标数量
    if len(all_qa) > args.target:
        all_qa = all_qa[:args.target]

    # 统计
    by_diff = {}
    by_cat = {}
    by_vol = {}
    for q in all_qa:
        by_diff[q["difficulty"]] = by_diff.get(q["difficulty"], 0) + 1
        by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
        by_vol[q["volume"]] = by_vol.get(q["volume"], 0) + 1

    print(f"\n生成 {len(all_qa)} 个 QA 对")
    print(f"  难度分布: {by_diff}")
    print(f"  类别分布: {by_cat}")
    print(f"  卷次分布: {by_vol}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_qa, f, ensure_ascii=False, indent=2)
    print(f"\n保存到 {OUTPUT_FILE}")

    # 抽样展示
    print("\n=== 随机抽样 5 题 ===")
    for q in random.sample(all_qa, min(5, len(all_qa))):
        print(f"  [{q['difficulty']}|{q['category']}] Q: {q['question']}")
        print(f"    A: {q['answer'][:80]}")
        print()


if __name__ == "__main__":
    main()
