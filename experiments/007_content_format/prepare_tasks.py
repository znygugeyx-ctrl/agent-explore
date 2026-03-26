"""Download GAIA benchmark and prepare tasks for experiment 007.

Filters GAIA validation set for tasks that don't require file attachments
(pure web-search questions), then selects a balanced subset across levels.

Usage:
    python -m experiments.007_content_format.prepare_tasks \
        --per-level 3 \
        --output experiments/007_content_format/tasks.jsonl

Requires: HF_TOKEN environment variable for HuggingFace access.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path


def load_gaia_validation(hf_token: str) -> list[dict]:
    """Load GAIA validation set from HuggingFace."""
    from datasets import load_dataset

    dataset = load_dataset(
        "gaia-benchmark/GAIA",
        name="2023_all",
        token=hf_token,
        split="validation",
    )
    return list(dataset)


def filter_web_search_tasks(tasks: list[dict]) -> list[dict]:
    """Filter for tasks that don't need file attachments (pure search tasks)."""
    filtered = []
    for t in tasks:
        # Skip tasks requiring file attachments
        if t.get("file_path") and t["file_path"].strip():
            continue
        filtered.append(t)
    return filtered


def select_balanced_subset(
    tasks: list[dict], per_level: int, seed: int = 42
) -> list[dict]:
    """Select per_level tasks from each level (1, 2, 3)."""
    by_level: dict[int, list[dict]] = {}
    for t in tasks:
        level = t.get("Level", t.get("level", 0))
        by_level.setdefault(level, []).append(t)

    rng = random.Random(seed)
    selected = []
    for level in sorted(by_level.keys()):
        pool = by_level[level]
        rng.shuffle(pool)
        chosen = pool[:per_level]
        selected.extend(chosen)
        print(f"  Level {level}: {len(pool)} available, selected {len(chosen)}")

    return selected


def convert_to_jsonl(tasks: list[dict]) -> list[dict]:
    """Convert GAIA tasks to agent-explore JSONL format."""
    records = []
    for t in tasks:
        level = t.get("Level", t.get("level", 0))
        record = {
            "id": t["task_id"],
            "prompt": t["Question"],
            "expected_answer": t["Final answer"],
            "metadata": {
                "level": level,
                "annotator_metadata": t.get("Annotator Metadata", {}),
            },
        }
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description="Prepare GAIA tasks for exp 007")
    parser.add_argument("--per-level", type=int, default=3, help="Tasks per level")
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/007_content_format/tasks.jsonl",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Print all filtered tasks (don't select subset)",
    )
    args = parser.parse_args()

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("Error: HF_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)

    print("Loading GAIA validation set...")
    all_tasks = load_gaia_validation(hf_token)
    print(f"  Total tasks: {len(all_tasks)}")

    print("Filtering for web-search tasks (no file attachments)...")
    filtered = filter_web_search_tasks(all_tasks)
    print(f"  Filtered: {len(filtered)} tasks")

    if args.show_all:
        for t in filtered:
            level = t.get("Level", "?")
            q = t["Question"][:100]
            a = t["Final answer"][:50]
            print(f"  L{level} | {t['task_id'][:8]}... | Q: {q}... | A: {a}")
        return

    print(f"Selecting {args.per_level} tasks per level...")
    selected = select_balanced_subset(filtered, args.per_level, args.seed)

    records = convert_to_jsonl(selected)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(records)} tasks to {output_path}")
    for r in records:
        level = r["metadata"]["level"]
        print(f"  L{level} | {r['id'][:12]}... | {r['prompt'][:80]}...")


if __name__ == "__main__":
    main()
