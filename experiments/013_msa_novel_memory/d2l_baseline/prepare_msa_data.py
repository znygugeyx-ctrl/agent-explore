"""准备 MSA 评测数据：从 pool 数据生成 MSA 兼容的 corpus.pkl + query.pkl。

MSA benchmark 需要：
- memory file (corpus.pkl): list of strings
- query file (query.pkl): list of {query, reference_list, answer}

策略：将所有题目的 pool docs 合并（去重）为一个 corpus，
MSA 的 router 自然路由到相关 docs。

Usage:
    python3 prepare_msa_data.py \
        --dataset hotpotqa_pools.json \
        --dataset_type hotpotqa \
        --pool_size 8k \
        --output_corpus /tmp/msa_corpus.pkl \
        --output_query /tmp/msa_query.pkl
"""
import argparse
import json
import pickle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--dataset_type", choices=["hotpotqa", "novel"], required=True)
    parser.add_argument("--pool_size", default="8k")
    parser.add_argument("--output_corpus", required=True)
    parser.add_argument("--output_query", required=True)
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records")

    doc_set = {}
    queries = []

    for rec in records:
        if args.dataset_type == "hotpotqa":
            pool = rec["pools"][args.pool_size]
            docs = pool["docs"]
        else:
            docs = [rec["context_text"]]

        gold_indices = []
        for doc_text in docs:
            key = doc_text[:200]
            if key not in doc_set:
                doc_set[key] = (len(doc_set), doc_text)
            gold_indices.append(doc_set[key][0])

        queries.append({
            "query": rec["question"],
            "reference_list": [doc_set[docs[i][:200]][1] for i in range(min(2, len(docs)))],
            "answer": rec["answer"],
        })

    corpus = [""] * len(doc_set)
    for key, (idx, text) in doc_set.items():
        corpus[idx] = text

    print(f"Corpus: {len(corpus)} unique docs")
    print(f"Queries: {len(queries)}")

    with open(args.output_corpus, "wb") as f:
        pickle.dump(corpus, f)
    with open(args.output_query, "wb") as f:
        pickle.dump(queries, f)
    print(f"Saved to {args.output_corpus} and {args.output_query}")


if __name__ == "__main__":
    main()
