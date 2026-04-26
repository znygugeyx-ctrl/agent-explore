"""MSA 评估脚本 — 向 MSA server 发送 QA 并收集回答。

Usage:
    python3 novel_qa_full/run_msa.py --qa_file novel_qa_full/qa_300.json --output novel_qa_full/results/msa_en_results.json
"""
import argparse
import json
import os
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def post_json(url, data, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa_file", default=os.path.join(SCRIPT_DIR, "qa_300.json"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()

    with open(args.qa_file, encoding="utf-8") as f:
        qa_pairs = json.load(f)
    print(f"Loaded {len(qa_pairs)} questions, server: {args.url}")

    results = []
    for i, qa in enumerate(qa_pairs):
        try:
            result = post_json(f"{args.url}/ask", {"question": qa["question"]})
            qa_out = {**qa, "msa_answer": result["answer"], "cited_docs": result["cited_docs"],
                      "latency_ms": result["latency_ms"], "rounds": result.get("rounds", -1)}
        except Exception as e:
            qa_out = {**qa, "msa_answer": "", "cited_docs": [], "latency_ms": -1, "rounds": -1}
            print(f"  [{i+1}] ERROR: {e}")
        results.append(qa_out)
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1}/{len(qa_pairs)}] {qa_out['latency_ms']}ms")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
