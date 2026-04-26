"""基于 8K context windows 生成小说 QA 数据集。

确保所有难度（含 hard）的 gold context 都在 window 内。

Usage:
    python3 d2l_baseline/generate_novel_qa.py \
        --windows d2l_baseline/data/novel_windows.json \
        --output d2l_baseline/data/novel_8k_pools.json \
        --target 180
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

GENERATE_PROMPT = """你是一个中文小说阅读理解题目的生成专家。

以下是小说《蛊真人》中的连续段落（包含{num_sections}个章节片段，共约{total_tokens}字符）：

---
{context}
---

请根据以上内容，生成{num_questions}个问答对。严格要求：

1. 所有问题的答案**必须且仅需**以上文本即可回答（不需要小说其他部分的知识）
2. 答案要简洁精确（1-3句话）

难度要求（请尽量平均分配）：
- **easy** ({easy_count}题): 答案在某一段落中有明确直接的表述
- **medium** ({medium_count}题): 需要理解上下文或综合多处信息推断
- **hard** ({hard_count}题): 需要跨章节推理、因果分析或关系推断（但所需信息必须全在上面的文本中）

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
                inferenceConfig={"temperature": 0.7, "maxTokens": 4096},
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


def process_window(window: dict, questions_per_window: int) -> list:
    easy_count = questions_per_window // 3
    hard_count = questions_per_window // 3
    medium_count = questions_per_window - easy_count - hard_count

    prompt = GENERATE_PROMPT.format(
        num_sections=window["num_sections"],
        total_tokens=window["total_tokens"],
        context=window["context_text"],
        num_questions=questions_per_window,
        easy_count=easy_count,
        medium_count=medium_count,
        hard_count=hard_count,
    )

    raw = call_claude(prompt)
    pairs = parse_qa_response(raw)

    results = []
    section_indices = [s["section_idx"] for s in window["sections"]]
    for p in pairs:
        if "question" not in p or "answer" not in p:
            continue
        results.append({
            "question": p["question"],
            "answer": p["answer"],
            "difficulty": p.get("difficulty", "medium"),
            "category": p.get("category", "event"),
            "window_start": window["start_section_idx"],
            "window_end": window["end_section_idx"],
            "window_sections": section_indices,
            "window_tokens": window["total_tokens"],
            "context_text": window["context_text"],
        })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", required=True, help="novel_windows.json path")
    parser.add_argument("--output", required=True, help="Output QA dataset path")
    parser.add_argument("--target", type=int, default=180)
    parser.add_argument("--questions_per_window", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    print(f"Loading windows: {args.windows}")
    with open(args.windows, encoding="utf-8") as f:
        windows = json.load(f)
    print(f"  {len(windows)} windows")

    # Resume support
    all_qa = []
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            existing = json.load(f)
        all_qa = existing
        done_windows = {(r["window_start"], r["window_end"]) for r in existing}
        windows = [w for w in windows
                    if (w["start_section_idx"], w["end_section_idx"]) not in done_windows]
        print(f"  Resuming: {len(existing)} existing QA, {len(windows)} windows remaining")

    if not windows:
        print("All windows processed.")
        return

    def process(w):
        return process_window(w, args.questions_per_window)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        batches = list(executor.map(process, windows))

    qa_id = len(all_qa) + 1
    for batch in batches:
        for item in batch:
            item["id"] = qa_id
            all_qa.append(item)
            qa_id += 1

    # Stats
    by_diff = {}
    for q in all_qa:
        by_diff[q["difficulty"]] = by_diff.get(q["difficulty"], 0) + 1

    print(f"\n生成 {len(all_qa)} 个 QA 对")
    print(f"  难度分布: {by_diff}")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_qa, f, ensure_ascii=False, indent=2)
    print(f"\n保存到 {args.output}")


if __name__ == "__main__":
    main()
