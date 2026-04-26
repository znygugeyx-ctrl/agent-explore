"""Experiment 013: MSA Novel Memory — Automated evaluation (方案A).

Sends a batch of QA pairs to the MSA server and collects results.
Requires the MSA server to be running (bash start_server.sh on EC2).

Usage:
    python experiments/013_msa_novel_memory/run.py \
        --qa_file experiments/013_msa_novel_memory/tasks/qa_pairs.json \
        --url http://localhost:8080 \
        --output experiments/013_msa_novel_memory/results/eval_results.json
"""
import argparse
import json
import time
import urllib.request


def post_json(url: str, data: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa_file", required=True, help="JSON file with QA pairs")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch_size", type=int, default=4)
    args = parser.parse_args()

    with open(args.qa_file) as f:
        qa_pairs = json.load(f)
    print(f"Loaded {len(qa_pairs)} QA pairs")

    results = []
    for i in range(0, len(qa_pairs), args.batch_size):
        batch = qa_pairs[i : i + args.batch_size]
        questions = [item["question"] for item in batch]
        resp = post_json(f"{args.url}/batch", {"questions": questions})

        for item, result in zip(batch, resp["results"]):
            results.append({
                "question": item["question"],
                "expected_answer": item.get("answer", ""),
                "msa_answer": result["answer"],
                "cited_docs": result["cited_docs"],
                "latency_ms": result["latency_ms"],
            })
        print(f"  {min(i + args.batch_size, len(qa_pairs))}/{len(qa_pairs)} done")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
