"""D2L evaluation runner — 通用，支持 HotpotQA 和小说 QA。

Usage:
    # HotpotQA (三档)
    python3 d2l_baseline/run_d2l.py \
        --dataset d2l_baseline/data/hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --checkpoint checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin \
        --pool_size 8k \
        --output d2l_baseline/results/hotpotqa_d2l_qwen_8k.json

    # 小说 QA
    python3 d2l_baseline/run_d2l.py \
        --dataset d2l_baseline/data/novel_8k_pools.json \
        --dataset_type novel \
        --checkpoint checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin \
        --output d2l_baseline/results/novel_d2l_qwen_8k.json
"""
import argparse
import json
import os
import time

import torch

from d2l_wrapper import D2LModel


def _save(path: str, data: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def run_hotpotqa(model: D2LModel, records: list, pool_size: str, output: str, existing: list) -> list:
    results = list(existing)
    for i, rec in enumerate(records):
        pool = rec["pools"][pool_size]
        context = "\n\n".join(pool["docs"])

        t0 = time.time()
        answer = model.ask(context, rec["question"])
        latency_ms = int((time.time() - t0) * 1000)

        results.append({
            "question": rec["question"],
            "answer": rec["answer"],
            "gold_doc_ids": rec["gold_doc_ids"],
            "d2l_answer": answer,
            "latency_ms": latency_ms,
            "pool_size": pool_size,
            "pool_tokens": pool["total_tokens"],
            "pool_docs": pool["num_docs"],
        })

        if (i + 1) % 5 == 0 or i == len(records) - 1:
            _save(output, results)
            print(f"  [{i+1}/{len(records)}] latency={latency_ms}ms saved", flush=True)

    return results


def run_novel(model: D2LModel, records: list, output: str, existing: list) -> list:
    results = list(existing)
    for i, rec in enumerate(records):
        context = rec["context_text"]

        t0 = time.time()
        answer = model.ask(context, rec["question"])
        latency_ms = int((time.time() - t0) * 1000)

        results.append({
            "question": rec["question"],
            "answer": rec["answer"],
            "difficulty": rec["difficulty"],
            "category": rec["category"],
            "d2l_answer": answer,
            "latency_ms": latency_ms,
            "window_tokens": rec["window_tokens"],
            "window_sections": rec["window_sections"],
            "id": rec["id"],
        })

        if (i + 1) % 5 == 0 or i == len(records) - 1:
            _save(output, results)
            print(f"  [{i+1}/{len(records)}] latency={latency_ms}ms saved", flush=True)

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--pool_size", default="8k", help="For hotpotqa: 2k/4k/8k")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0, help="Limit questions (0=all)")
    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")
    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)

    # Resume support
    done_ids = set()
    existing = []
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            existing = json.load(f)
        if args.dataset_type == "novel":
            done_ids = {r["id"] for r in existing}
        else:
            done_ids = {r["question"] for r in existing}
        print(f"  Resuming: {len(existing)} done, {len(records) - len(done_ids)} remaining")

    if args.dataset_type == "novel":
        records = [r for r in records if r["id"] not in done_ids]
    else:
        records = [r for r in records if r["question"] not in done_ids]

    if args.limit > 0:
        records = records[:args.limit]

    if not records:
        print("All questions already processed.")
        return

    print(f"  {len(records)} questions to process")
    print(f"Loading D2L model: {args.checkpoint}")
    model = D2LModel(args.checkpoint, max_new_tokens=args.max_new_tokens)
    print(f"  Base model: {model.base_model_name}")

    if args.dataset_type == "hotpotqa":
        all_results = run_hotpotqa(model, records, args.pool_size, args.output, existing)
    else:
        all_results = run_novel(model, records, args.output, existing)

    _save(args.output, all_results)
    print(f"\nSaved {len(all_results)} results to {args.output}")


if __name__ == "__main__":
    main()
