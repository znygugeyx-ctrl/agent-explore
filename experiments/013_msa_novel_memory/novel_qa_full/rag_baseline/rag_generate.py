"""RAG 检索 + Qwen3-4B 生成。

在 EC2 上运行：
    python3 rag_baseline/rag_generate.py \
        --index_dir rag_baseline/novel_index \
        --qa_file qa_300.json \
        --output results/rag_results.json \
        --top_k 5
"""
import argparse
import json
import os
import pickle
import time

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM

EMBED_MODEL = "HIT-TMG/KaLM-embedding-multilingual-mini-instruct-v2"
GEN_MODEL = os.environ.get("RAG_GEN_MODEL", "ckpt/Qwen3-4B")

RAG_PROMPT_CN = """请根据以下参考文档回答问题。如果文档中没有足够信息，请说明无法回答。

参考文档：
{context}

问题：{question}

请简洁准确地回答："""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index_dir", required=True)
    parser.add_argument("--qa_file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    args = parser.parse_args()

    # Load index
    print(f"Loading index from {args.index_dir}")
    index = faiss.read_index(os.path.join(args.index_dir, "index.faiss"))
    with open(os.path.join(args.index_dir, "docs.pkl"), "rb") as f:
        docs = pickle.load(f)
    print(f"  {index.ntotal} vectors, {len(docs)} docs")

    # Load embedding model
    print(f"Loading embedding model: {EMBED_MODEL}")
    embed_model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)

    # Load generator
    print(f"Loading generator: {GEN_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
    gen_model = AutoModelForCausalLM.from_pretrained(
        GEN_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    gen_model.eval()

    # Load QA
    with open(args.qa_file, encoding="utf-8") as f:
        qa_pairs = json.load(f)
    print(f"Loaded {len(qa_pairs)} questions")

    # Process
    results = []
    for i, qa in enumerate(qa_pairs):
        t0 = time.time()
        question = qa["question"]

        # Retrieve
        q_emb = embed_model.encode([question], normalize_embeddings=True)
        scores, indices = index.search(q_emb.astype(np.float32), args.top_k)
        retrieved = [docs[idx] for idx in indices[0] if idx < len(docs)]

        # Truncate each retrieved doc
        retrieved_truncated = [d[:1500] for d in retrieved]
        context = "\n\n---\n\n".join(
            f"[文档{j+1}] {doc}" for j, doc in enumerate(retrieved_truncated)
        )

        # Generate
        prompt = RAG_PROMPT_CN.format(context=context, question=question)
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(gen_model.device)

        with torch.no_grad():
            output_ids = gen_model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                temperature=0.0,
                do_sample=False,
            )
        answer = tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        # Strip thinking tags if present
        if "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        latency = int((time.time() - t0) * 1000)

        retrieved_titles = [d.split("\n")[0] for d in retrieved]
        results.append({
            **qa,
            "rag_answer": answer,
            "retrieved_titles": retrieved_titles,
            "retrieval_scores": scores[0].tolist(),
            "latency_ms": latency,
        })

        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1}/{len(qa_pairs)}] {latency}ms Q: {question[:40]}...")

    # Save
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(results)} results to {args.output}")

    avg_latency = np.mean([r["latency_ms"] for r in results])
    print(f"Average latency: {avg_latency:.0f}ms")


if __name__ == "__main__":
    main()
