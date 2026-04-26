"""MSA evaluation on restricted context pools.

MSA 正常编码大规模语料。这里限制到 2K/4K/8K pool，
为每题独立编码一个"迷你语料库"，然后 ask。

需要 MSA server 运行在 localhost:8080（或指定 --server_url）。
MSA server 需支持动态编码新 corpus（通过 /encode + /ask API）。

Usage:
    python3 d2l_baseline/run_msa_8k.py \
        --dataset d2l_baseline/data/hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --pool_size 8k \
        --output d2l_baseline/results/hotpotqa_msa_8k.json
"""
import argparse
import json
import os
import time

import requests

MSA_SERVER = "http://localhost:8080"


def msa_encode_and_ask(
    server_url: str, docs: list[str], question: str
) -> tuple[str, int, int]:
    """Encode a mini corpus and ask a question.

    Returns (answer, latency_ms, rounds).
    MSA API 可能需要调整 — 当前假设支持:
      POST /encode  {"docs": [...]}
      POST /ask     {"question": "..."}
    如果 MSA 不支持动态换 corpus，需要在此处 workaround。
    """
    t0 = time.time()

    # Step 1: encode mini corpus
    r = requests.post(f"{server_url}/encode", json={"docs": docs}, timeout=60)
    r.raise_for_status()

    # Step 2: ask
    r = requests.post(f"{server_url}/ask", json={"question": question}, timeout=120)
    r.raise_for_status()
    data = r.json()

    latency_ms = int((time.time() - t0) * 1000)
    return data.get("answer", ""), latency_ms, data.get("rounds", 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--pool_size", default="8k")
    parser.add_argument("--server_url", default=MSA_SERVER)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
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
    print(f"MSA server: {args.server_url}")

    results = []
    for i, rec in enumerate(records):
        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            docs = pool["docs"]
        else:
            docs = [rec["context_text"]]

        try:
            answer, latency_ms, rounds = msa_encode_and_ask(
                args.server_url, docs, rec["question"]
            )
        except Exception as e:
            print(f"  Error on question {i+1}: {e}")
            answer, latency_ms, rounds = "", 0, 0

        result = {
            "question": rec["question"],
            "answer": rec["answer"],
            "msa_answer": answer,
            "latency_ms": latency_ms,
            "rounds": rounds,
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
