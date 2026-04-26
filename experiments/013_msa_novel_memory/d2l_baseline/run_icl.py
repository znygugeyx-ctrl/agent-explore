"""ICL (In-Context Learning) baseline — context 直接塞入 prompt。

Usage:
    # HotpotQA
    python3 d2l_baseline/run_icl.py \
        --dataset d2l_baseline/data/hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --pool_size 8k \
        --output d2l_baseline/results/hotpotqa_icl_qwen_8k.json

    # 小说 QA
    python3 d2l_baseline/run_icl.py \
        --dataset d2l_baseline/data/novel_8k_pools.json \
        --dataset_type novel \
        --output d2l_baseline/results/novel_icl_qwen_8k.json
"""
import argparse
import json
import os
import time

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

ICL_PROMPT_EN = """Answer the question based on the following documents. If the documents don't contain enough information, say so.

Documents:
{context}

Question: {question}

Answer concisely:"""

ICL_PROMPT_CN = """请根据以下参考文档回答问题。如果文档中没有足够信息，请说明无法回答。

参考文档：
{context}

问题：{question}

请简洁准确地回答："""


class ICLModel:
    def __init__(self, model_name: str, max_new_tokens: int = 256):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=torch.bfloat16, device_map="auto"
        )
        self.model.eval()
        self.max_new_tokens = max_new_tokens

    def ask(self, context: str, question: str, lang: str = "en") -> str:
        template = ICL_PROMPT_EN if lang == "en" else ICL_PROMPT_CN
        prompt = template.format(context=context, question=question)

        chat = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            output = self.model.generate(
                input_ids=chat,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        answer = self.tokenizer.decode(
            output[0][chat.shape[1]:], skip_special_tokens=True
        )
        if "</think>" in answer:
            answer = answer.split("</think>")[-1]
        return answer.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--pool_size", default="8k")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--enable_thinking", action="store_true", default=False)
    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")
    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)

    # Resume
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
    print(f"Loading model: {args.model}")
    model = ICLModel(args.model, max_new_tokens=args.max_new_tokens)

    lang = "cn" if args.dataset_type == "novel" else "en"
    results = []

    for i, rec in enumerate(records):
        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            context = "\n\n".join(pool["docs"])
        else:
            context = rec["context_text"]

        t0 = time.time()
        answer = model.ask(context, rec["question"], lang=lang)
        latency_ms = int((time.time() - t0) * 1000)

        result = {
            "question": rec["question"],
            "answer": rec["answer"],
            "icl_answer": answer,
            "latency_ms": latency_ms,
        }

        if args.dataset_type == "hotpotqa":
            result.update({
                "gold_doc_ids": rec["gold_doc_ids"],
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
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(records)}] latency={latency_ms}ms")

    all_results = existing + results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_results)} results to {args.output}")


if __name__ == "__main__":
    main()
