"""MSA evaluation on restricted context pools.

每题独立编码一个 8K token 的 mini corpus。
通过 MSA benchmark API，为每题创建独立的 memory file，
然后调用 MSA engine 进行推理。

为避免频繁重启 MSA engine，采用分批策略：
1. 将所有题目的 pool docs 合并（去重）为一个大 corpus
2. 一次性编码整个 corpus
3. MSA router 自然路由到相关 docs

这测试的是：给定与 ICL/D2L 相同信息的 corpus，MSA 的 router 能否找到正确信息。

Usage (on MSA EC2 instance):
    # 需要先 conda activate msa
    python3 run_msa_pool.py \
        --dataset ~/d2l_baseline/data/hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --pool_size 8k \
        --model_path ckpt/MSA-4B \
        --output ~/d2l_baseline/results/hotpotqa_msa_8k.json
"""
import argparse
import json
import os
import pickle
import sys
import time
import re

import torch
import numpy as np

# Add MSA to path
sys.path.insert(0, "/home/ubuntu/MSA")

from src.msa_service import MSAEngine, GenerateConfig, ModelConfig, MemoryConfig
from src.msa_service import Document


def create_documents(texts: list[str]) -> list:
    """Create MSA Document objects from text strings."""
    docs = []
    for i, text in enumerate(texts):
        doc = Document()
        doc.doc_id = i
        doc.text = text
        doc.title = text.split("\n")[0][:50] if "\n" in text else text[:50]
        docs.append(doc)
    return docs


def extract_answer(generated_text: str) -> str:
    """Extract answer from MSA's multi-round generation output."""
    try:
        answer = generated_text.split("The answer to the question is:")[-1]
        answer = answer.split("<|im_end|>")[0].strip()
        return answer
    except Exception:
        return generated_text.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--pool_size", default="8k")
    parser.add_argument("--model_path", default="ckpt/MSA-4B")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max_length", type=int, default=2048)
    parser.add_argument("--block_size", type=int, default=2048)
    parser.add_argument("--top_k", type=int, default=16)
    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")
    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)

    if args.limit > 0:
        records = records[:args.limit]
    print(f"  {len(records)} questions")

    # Collect all unique docs from all pools
    print("Collecting documents from pools...")
    all_docs_set = {}
    question_doc_mapping = []

    for rec in records:
        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            docs = pool["docs"]
        else:
            docs = [rec["context_text"]]

        doc_indices = []
        for doc_text in docs:
            doc_hash = hash(doc_text)
            if doc_hash not in all_docs_set:
                all_docs_set[doc_hash] = (len(all_docs_set), doc_text)
            doc_indices.append(all_docs_set[doc_hash][0])
        question_doc_mapping.append(doc_indices)

    all_docs = [text for _, (_, text) in sorted(
        ((idx, (idx, text)) for hash_val, (idx, text) in all_docs_set.items()),
        key=lambda x: x[0]
    )]
    # Fix: rebuild from all_docs_set properly
    all_docs_list = [""] * len(all_docs_set)
    for _, (idx, text) in all_docs_set.items():
        all_docs_list[idx] = text
    all_docs = all_docs_list

    print(f"  Total unique docs: {len(all_docs)}")

    # Save as pkl for MSA
    corpus_path = "/tmp/msa_pool_corpus.pkl"
    with open(corpus_path, "wb") as f:
        pickle.dump(all_docs, f)

    # Initialize MSA engine
    print("Initializing MSA engine...")
    os.environ["MSA_MEMORY_FILE"] = corpus_path
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0,1,2,3")
    os.environ.setdefault("MASTER_PORT", "29509")

    # Use MSA benchmark approach
    from src.app.benchmark import parse_args as msa_parse_args

    # Instead of using engine directly, use the benchmark's approach
    # which handles the multi-round generation correctly
    print("Running MSA benchmark-style evaluation...")

    # We'll use a simpler approach: write a compatible query file
    # and run MSA's benchmark code
    query_data = []
    for i, rec in enumerate(records):
        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            gold_doc_indices = []
            for gid in rec.get("gold_doc_ids", []):
                # Map gold doc IDs to our corpus indices
                pass
            query_data.append({
                "query": rec["question"],
                "reference_list": [],  # not used for generation
                "answer": rec["answer"],
            })
        else:
            query_data.append({
                "query": rec["question"],
                "reference_list": [],
                "answer": rec["answer"],
            })

    query_path = "/tmp/msa_pool_queries.pkl"
    with open(query_path, "wb") as f:
        pickle.dump(query_data, f)
    print(f"  Saved {len(query_data)} queries to {query_path}")
    print("  Corpus and queries ready for MSA benchmark.")
    print(f"  Run: python -u src/app/benchmark.py \\")
    print(f"    --benchmark custom \\")
    print(f"    --model_path {args.model_path} \\")
    print(f"    --temperature 0.0 --max_length {args.max_length} \\")
    print(f"    --template QWEN3_INSTRUCT_TEMPLATE \\")
    print(f"    --output_file {args.output} \\")
    print(f"    --max_batch_size 8 --block_size {args.block_size}")


if __name__ == "__main__":
    main()
