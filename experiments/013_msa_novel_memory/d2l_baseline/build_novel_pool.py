"""构造小说 8K context windows 并采样。

从小说 corpus 中均匀采样起始点，拼接连续 sections 到 ~8K tokens。
输出 windows 供 generate_novel_qa.py 生成 QA 数据集。

Usage:
    python3 d2l_baseline/build_novel_pool.py \
        --corpus mdata_novel.pkl \
        --output d2l_baseline/data/novel_windows.json \
        --num_windows 50
"""
import argparse
import json
import os
import pickle
import random

from transformers import AutoTokenizer

TARGET_TOKENS = 8192
PROMPT_RESERVE = 256  # reserve for QA prompt overhead


def count_tokens(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def build_window(
    docs: list[str],
    start_idx: int,
    tokenizer,
    max_tokens: int,
) -> dict:
    sections = []
    total_tokens = 0
    idx = start_idx

    while idx < len(docs) and total_tokens < max_tokens:
        section_text = docs[idx]
        section_tokens = count_tokens(tokenizer, section_text)

        if total_tokens + section_tokens > max_tokens:
            remaining = max_tokens - total_tokens
            if remaining > 200 and not sections:
                tokens = tokenizer.encode(section_text, add_special_tokens=False)
                truncated = tokenizer.decode(tokens[:remaining])
                sections.append({
                    "section_idx": idx,
                    "text": truncated,
                    "tokens": remaining,
                    "truncated": True,
                })
                total_tokens += remaining
            elif remaining > 200:
                tokens = tokenizer.encode(section_text, add_special_tokens=False)
                truncated = tokenizer.decode(tokens[:remaining])
                sections.append({
                    "section_idx": idx,
                    "text": truncated,
                    "tokens": remaining,
                    "truncated": True,
                })
                total_tokens += remaining
            break

        sections.append({
            "section_idx": idx,
            "text": section_text,
            "tokens": section_tokens,
            "truncated": False,
        })
        total_tokens += section_tokens
        idx += 1

    return {
        "start_section_idx": start_idx,
        "end_section_idx": sections[-1]["section_idx"] if sections else start_idx,
        "num_sections": len(sections),
        "total_tokens": total_tokens,
        "sections": sections,
        "context_text": "\n\n".join(s["text"] for s in sections),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, help="mdata_novel.pkl path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--num_windows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tokenizer", default="Qwen/Qwen3-4B-Instruct-2507")
    args = parser.parse_args()

    print(f"Loading tokenizer: {args.tokenizer}")
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)

    print(f"Loading corpus: {args.corpus}")
    with open(args.corpus, "rb") as f:
        docs = pickle.load(f)
    print(f"  {len(docs)} sections")

    rng = random.Random(args.seed)
    max_tokens = TARGET_TOKENS - PROMPT_RESERVE

    stride = len(docs) // args.num_windows
    start_indices = list(range(0, len(docs) - 3, stride))[:args.num_windows]
    rng.shuffle(start_indices)
    start_indices = sorted(start_indices[:args.num_windows])

    windows = []
    for start_idx in start_indices:
        window = build_window(docs, start_idx, tokenizer, max_tokens)
        if window["total_tokens"] >= 1000:
            windows.append(window)

    print(f"\nBuilt {len(windows)} windows")
    tokens = [w["total_tokens"] for w in windows]
    sections = [w["num_sections"] for w in windows]
    print(f"  Tokens: min={min(tokens)}, avg={sum(tokens)/len(tokens):.0f}, max={max(tokens)}")
    print(f"  Sections: min={min(sections)}, avg={sum(sections)/len(sections):.1f}, max={max(sections)}")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(windows, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
