"""RAG baseline — 复用 013 的 RAG 方案，适配新数据集格式。

对每题的 context pool：
1. 构建临时 FAISS 索引（从 pool docs）
2. 用 embedding model 检索 top-k docs
3. 用 Qwen3-4B 生成答案

Usage:
    # HotpotQA
    python3 d2l_baseline/run_rag.py \
        --dataset d2l_baseline/data/hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --pool_size 8k \
        --output d2l_baseline/results/hotpotqa_rag_8k.json

    # 小说 QA
    python3 d2l_baseline/run_rag.py \
        --dataset d2l_baseline/data/novel_8k_pools.json \
        --dataset_type novel \
        --output d2l_baseline/results/novel_rag_8k.json
"""
import argparse
import json
import os
import time

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM

EMBED_MODEL = os.environ.get(
    "RAG_EMBED_MODEL", "Qwen/Qwen3-Embedding-4B"
)
GEN_MODEL = os.environ.get("RAG_GEN_MODEL", "Qwen/Qwen3-4B")

RAG_PROMPT_EN = """Answer the question based on the following documents. If the documents don't contain enough information, say so.

Documents:
{context}

Question: {question}

Answer concisely:"""

RAG_PROMPT_CN = """请根据以下参考文档回答问题。如果文档中没有足够信息，请说明无法回答。

参考文档：
{context}

问题：{question}

请简洁准确地回答："""


def build_temp_index(embed_model, docs):
    embeddings = embed_model.encode(
        docs, batch_size=64, normalize_embeddings=True, show_progress_bar=False
    )
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype(np.float32))
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--pool_size", default="8k")
    parser.add_argument("--output", required=True)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--enable_thinking", action="store_true", default=False)
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
        print(f"  Resuming: {len(existing)} done")

    if args.dataset_type == "novel":
        records = [r for r in records if r["id"] not in done_ids]
    else:
        records = [r for r in records if r["question"] not in done_ids]

    if args.limit > 0:
        records = records[:args.limit]

    if not records:
        print("All done.")
        return

    print(f"  {len(records)} questions to process")

    print(f"Loading embedding model: {EMBED_MODEL}")
    embed_model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)

    print(f"Loading generator: {GEN_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
    gen_model = AutoModelForCausalLM.from_pretrained(
        GEN_MODEL, torch_dtype=torch.bfloat16, device_map="auto",
        attn_implementation="sdpa",
    )
    gen_model.eval()

    lang = "cn" if args.dataset_type == "novel" else "en"
    prompt_template = RAG_PROMPT_CN if lang == "cn" else RAG_PROMPT_EN
    results = []

    for i, rec in enumerate(records):
        t0 = time.time()

        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            pool_docs = pool["docs"]
        else:
            # Novel: chunk the 8K context into ~500-char chunks for RAG
            ctx = rec["context_text"]
            chunk_size = 500
            pool_docs = [
                ctx[i:i + chunk_size]
                for i in range(0, len(ctx), chunk_size)
            ]

        question = rec["question"]

        # Build temp index from pool docs and retrieve
        if len(pool_docs) > args.top_k:
            index = build_temp_index(embed_model, pool_docs)
            q_emb = embed_model.encode(
                [question], normalize_embeddings=True
            ).astype(np.float32)
            scores, indices = index.search(q_emb, args.top_k)
            retrieved = [pool_docs[idx] for idx in indices[0]]
            retrieval_scores = scores[0].tolist()
        else:
            retrieved = pool_docs
            retrieval_scores = [1.0] * len(pool_docs)

        retrieved_truncated = [d[:1500] for d in retrieved]
        if lang == "cn":
            context = "\n\n---\n\n".join(
                f"[文档{j+1}] {doc}" for j, doc in enumerate(retrieved_truncated)
            )
        else:
            context = "\n\n---\n\n".join(
                f"[Doc {j+1}] {doc}" for j, doc in enumerate(retrieved_truncated)
            )

        prompt = prompt_template.format(context=context, question=question)
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to(gen_model.device)

        with torch.no_grad():
            output_ids = gen_model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                temperature=0.0,
                do_sample=False,
            )
        answer = tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        if "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        latency_ms = int((time.time() - t0) * 1000)

        result = {
            "question": rec["question"],
            "answer": rec["answer"],
            "rag_answer": answer,
            "retrieved_titles": [d.split("\n")[0][:50] for d in retrieved],
            "retrieval_scores": retrieval_scores,
            "latency_ms": latency_ms,
        }

        if args.dataset_type == "hotpotqa":
            result.update({
                "gold_doc_ids": rec.get("gold_doc_ids"),
                "pool_size": args.pool_size,
                "pool_tokens": pool["total_tokens"],
            })
        else:
            result.update({
                "difficulty": rec["difficulty"],
                "category": rec["category"],
                "window_tokens": rec["window_tokens"],
                "id": rec["id"],
            })

        results.append(result)
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1}/{len(records)}] {latency_ms}ms")

    all_results = existing + results
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_results)} results to {args.output}")


if __name__ == "__main__":
    main()
