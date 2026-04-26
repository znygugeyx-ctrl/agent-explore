"""构造 HotpotQA 2K/4K/8K 嵌套 context pools。

从 013 已有的 bench_hotpotqa_raw.json 提取 gold docs，
从 HotpotQA 语料库采样 distractors，构造嵌套 pools。

Usage:
    python3 d2l_baseline/build_hotpotqa_pool.py \
        --raw results/hotpotqa_reproduction/bench_hotpotqa_raw.json \
        --corpus data/hotpotqa/mdata_hotpotqa.pkl \
        --output d2l_baseline/data/hotpotqa_pools.json \
        --num_questions 200
"""
import argparse
import json
import os
import pickle
import random
import sys

from transformers import AutoTokenizer

POOL_SIZES = {"2k": 2048, "4k": 4096, "8k": 8192}
PROMPT_RESERVE = 128  # tokens reserved for prompt template


def count_tokens(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def build_nested_pools(
    gold_docs: list[str],
    all_docs: list[str],
    gold_ids: list[int],
    tokenizer,
    rng: random.Random,
) -> dict | None:
    gold_tokens = sum(count_tokens(tokenizer, d) for d in gold_docs)
    budget_2k = POOL_SIZES["2k"] - PROMPT_RESERVE

    if gold_tokens > budget_2k * 0.75:
        return None

    gold_id_set = set(gold_ids)
    candidate_ids = [i for i in range(len(all_docs)) if i not in gold_id_set]
    rng.shuffle(candidate_ids)

    pools = {}
    current_docs = list(gold_docs)
    current_tokens = gold_tokens
    distractor_idx = 0

    for size_name in ["2k", "4k", "8k"]:
        budget = POOL_SIZES[size_name] - PROMPT_RESERVE
        skips = 0
        while current_tokens < budget and distractor_idx < len(candidate_ids):
            did = candidate_ids[distractor_idx]
            doc = all_docs[did]
            doc_tokens = count_tokens(tokenizer, doc)
            distractor_idx += 1
            if current_tokens + doc_tokens > budget:
                skips += 1
                if skips > 20:
                    break
                continue
            current_docs.append(doc)
            current_tokens += doc_tokens
            skips = 0

        pool_docs = list(current_docs)
        rng.shuffle(pool_docs)
        pools[size_name] = {
            "docs": pool_docs,
            "num_docs": len(pool_docs),
            "total_tokens": sum(count_tokens(tokenizer, d) for d in pool_docs),
        }

    return pools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, help="bench_hotpotqa_raw.json path")
    parser.add_argument("--corpus", required=True, help="mdata_hotpotqa.pkl path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--num_questions", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tokenizer", default="Qwen/Qwen3-4B-Instruct-2507")
    args = parser.parse_args()

    print(f"Loading tokenizer: {args.tokenizer}")
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    print(f"Loading corpus: {args.corpus}")
    with open(args.corpus, "rb") as f:
        all_docs = pickle.load(f)
    print(f"  {len(all_docs)} documents")

    print(f"Loading raw results: {args.raw}")
    with open(args.raw, encoding="utf-8") as f:
        raw_data = json.load(f)

    records = raw_data["hotpotqa"]["precision"]["record_list"]
    print(f"  {len(records)} questions")

    rng = random.Random(args.seed)
    rng.shuffle(records)

    results = []
    skipped = 0

    for rec in records:
        if len(results) >= args.num_questions:
            break

        gold_ids = rec["labels_id"]
        gold_docs = [all_docs[gid] for gid in gold_ids]

        pools = build_nested_pools(gold_docs, all_docs, gold_ids, tokenizer, rng)
        if pools is None:
            skipped += 1
            continue

        results.append({
            "question": rec["question"],
            "answer": rec["true_answer"],
            "gold_doc_ids": gold_ids,
            "pools": pools,
        })

    print(f"\nBuilt {len(results)} questions (skipped {skipped} due to gold doc length)")

    for size_name in ["2k", "4k", "8k"]:
        tokens = [r["pools"][size_name]["total_tokens"] for r in results]
        docs = [r["pools"][size_name]["num_docs"] for r in results]
        print(f"  {size_name}: avg {sum(tokens)/len(tokens):.0f} tokens, "
              f"avg {sum(docs)/len(docs):.0f} docs")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
