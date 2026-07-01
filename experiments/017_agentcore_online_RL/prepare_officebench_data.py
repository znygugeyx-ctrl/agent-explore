"""Prepare OfficeBench dataset for AgentCore office agent training (exp 017).

Registers train/test datasets where each sample is the payload that the
officebench rl_app.py expects — {task_uri, testbed_uri} — plus task_id/subtask_id
for grouping. The training side sends each task dict verbatim as the AgentCore
invocation payload (see rllm engine/remote_runtime/agentcore_runtime.py: payload=sub.task).

Train/test membership comes from officebench_split.json (stratified 80/20 by
task_id, produced by make_split.py).

Usage:
    python -m examples.agentcore_office.prepare_officebench_data \
        --split /path/to/officebench_split.json \
        --s3_bucket agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1 \
        --s3_prefix officebench
"""

import argparse

from datasets import Dataset

from rllm.data.dataset import DatasetRegistry


def build_rows(split_entries, bucket, prefix):
    rows = []
    for i, e in enumerate(split_entries):
        task_id = e["task_id"]
        subtask_id = e["subtask_id"]
        rows.append(
            {
                "idx": i,
                "task_id": task_id,
                "subtask_id": subtask_id,
                # payload contract for officebench rl_app.py InvocationRequest
                "task_uri": f"s3://{bucket}/{prefix}/{task_id}/{subtask_id}/config.json",
                "testbed_uri": f"s3://{bucket}/{prefix}/{task_id}/testbed.tar.gz",
                "data_source": "officebench",
            }
        )
    return rows


def main():
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, help="Path to officebench_split.json")
    ap.add_argument("--s3_bucket", default="agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1")
    ap.add_argument("--s3_prefix", default="officebench")
    ap.add_argument("--category", default=None, choices=["1", "2", "3"],
                    help="Curriculum: only register subtasks of this category (e.g. 1=single-app, easy)")
    ap.add_argument("--name_suffix", default="", help="Suffix for dataset name, e.g. _c1")
    args = ap.parse_args()

    with open(args.split) as f:
        split = json.load(f)

    def cat_filter(subtasks):
        if not args.category:
            return subtasks
        return [s for s in subtasks if s["task_id"].split("-")[0] == args.category]

    train_subs = cat_filter(split["train"]["subtasks"])
    test_subs = cat_filter(split["test"]["subtasks"])
    train_rows = build_rows(train_subs, args.s3_bucket, args.s3_prefix)
    test_rows = build_rows(test_subs, args.s3_bucket, args.s3_prefix)

    train_name = "officebench_train" + args.name_suffix
    test_name = "officebench_test" + args.name_suffix
    train_ds = DatasetRegistry.register_dataset(
        train_name,
        Dataset.from_list(train_rows),
        "train",
        source="OfficeBench",
        description=f"OfficeBench train (cat={args.category or 'all'}) for AgentCore office agent",
        category="tool_use",
    )
    test_ds = DatasetRegistry.register_dataset(
        test_name,
        Dataset.from_list(test_rows),
        "test",
        source="OfficeBench",
        description=f"OfficeBench test (cat={args.category or 'all'}) for AgentCore office agent",
        category="tool_use",
    )

    print(f"Train: {len(train_ds)} subtasks")
    print(f"Test:  {len(test_ds)} subtasks")
    print(f"Sample: {train_ds[0]}")


if __name__ == "__main__":
    main()
