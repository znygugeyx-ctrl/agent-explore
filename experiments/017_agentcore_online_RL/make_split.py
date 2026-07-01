"""Stratified 80/20 train/test split for OfficeBench (exp 017 officebench).

Split is by task_id (not subtask) to avoid leakage — subtasks of one task share
a testbed and are highly homogeneous. Stratified by category (1/2/3) so train and
test keep the same difficulty distribution. Known ground-truth-bug tasks are dropped.

Output: results/officebench_split.json
  {
    "seed": 42,
    "dropped": ["1-10", "1-14"],          # tasks with known GT bugs (subtask-level noted)
    "train": {"task_ids": [...], "subtasks": [{"task_id","subtask_id"}, ...]},
    "test":  {"task_ids": [...], "subtasks": [...]},
    "stats": {...}
  }

Usage:
    python make_split.py --officebench_dir /tmp/OfficeBench
"""

import argparse
import json
import os
import random
from collections import defaultdict
from pathlib import Path

# Known ground-truth bugs (README §Known Issues). These subtasks always fail
# regardless of agent capability. We drop the whole task_id to be safe.
BUG_TASKS = {"1-10", "1-14"}

TEST_FRAC = 0.20
SEED = 42


def collect(officebench_dir: str):
    tasks_dir = os.path.join(officebench_dir, "tasks")
    by_cat = defaultdict(list)  # category -> [task_id]
    subtasks = defaultdict(list)  # task_id -> [subtask_id]
    for task_id in sorted(os.listdir(tasks_dir)):
        sd = os.path.join(tasks_dir, task_id, "subtasks")
        if not os.path.isdir(sd):
            continue
        subs = sorted(f.removesuffix(".json") for f in os.listdir(sd) if f.endswith(".json"))
        if not subs:
            continue
        cat = task_id.split("-")[0]
        by_cat[cat].append(task_id)
        subtasks[task_id] = subs
    return by_cat, subtasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--officebench_dir", required=True)
    ap.add_argument("--out", default=str(Path(__file__).parent / "results" / "officebench_split.json"))
    args = ap.parse_args()

    rng = random.Random(SEED)
    by_cat, subtasks = collect(args.officebench_dir)

    train_ids, test_ids = [], []
    for cat in sorted(by_cat):
        ids = [t for t in by_cat[cat] if t not in BUG_TASKS]
        rng.shuffle(ids)
        n_test = round(len(ids) * TEST_FRAC)
        test_ids.extend(sorted(ids[:n_test]))
        train_ids.extend(sorted(ids[n_test:]))

    train_ids.sort()
    test_ids.sort()

    def expand(ids):
        return [{"task_id": t, "subtask_id": s} for t in ids for s in subtasks[t]]

    train_sub = expand(train_ids)
    test_sub = expand(test_ids)

    def cat_counts(ids):
        c = defaultdict(int)
        for t in ids:
            c[t.split("-")[0]] += 1
        return dict(sorted(c.items()))

    out = {
        "seed": SEED,
        "test_frac": TEST_FRAC,
        "dropped_bug_tasks": sorted(BUG_TASKS),
        "train": {"task_ids": train_ids, "subtasks": train_sub},
        "test": {"task_ids": test_ids, "subtasks": test_sub},
        "stats": {
            "train_tasks": len(train_ids),
            "test_tasks": len(test_ids),
            "train_subtasks": len(train_sub),
            "test_subtasks": len(test_sub),
            "train_tasks_by_cat": cat_counts(train_ids),
            "test_tasks_by_cat": cat_counts(test_ids),
        },
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

    print(json.dumps(out["stats"], indent=2))
    print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()
