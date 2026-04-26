"""下载 HotpotQA 语料库并准备数据。

在 EC2 上运行：
    python3 ~/d2l_baseline/prepare_data.py
"""
import json
import os
import pickle

from datasets import load_dataset


def download_hotpotqa():
    """Download HotpotQA corpus and test set from EverMind-AI."""
    out_dir = os.path.expanduser("~/data/hotpotqa")
    os.makedirs(out_dir, exist_ok=True)

    corpus_path = os.path.join(out_dir, "mdata_hotpotqa.pkl")
    if os.path.exists(corpus_path):
        print(f"Corpus already exists: {corpus_path}")
        with open(corpus_path, "rb") as f:
            docs = pickle.load(f)
        print(f"  {len(docs)} documents")
        return

    print("Downloading MSA-RAG-BENCHMARKS from HuggingFace...")
    ds = load_dataset("EverMind-AI/MSA-RAG-BENCHMARKS", "hotpotqa")

    # Extract memory corpus (documents)
    memory_data = ds.get("memory") or ds.get("train")
    if memory_data is None:
        print("Available splits:", list(ds.keys()))
        print("Columns:", ds[list(ds.keys())[0]].column_names if ds else "none")
        return

    print(f"Memory split: {len(memory_data)} entries")
    print(f"Columns: {memory_data.column_names}")

    # Build doc list (pickle format same as MSA uses)
    docs = []
    for row in memory_data:
        if "text" in row:
            docs.append(row["text"])
        elif "content" in row:
            docs.append(row["content"])
        elif "document" in row:
            docs.append(row["document"])
        else:
            docs.append(str(row))

    with open(corpus_path, "wb") as f:
        pickle.dump(docs, f)
    print(f"Saved {len(docs)} docs to {corpus_path}")

    # Also save test questions if available
    test_data = ds.get("test") or ds.get("validation")
    if test_data:
        test_path = os.path.join(out_dir, "test_questions.json")
        test_data.to_json(test_path)
        print(f"Saved test questions to {test_path}")


def main():
    download_hotpotqa()


if __name__ == "__main__":
    main()
