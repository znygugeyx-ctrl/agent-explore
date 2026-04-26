"""构建 KaLMv2 向量索引。

在 EC2 上运行：
    python3 rag_baseline/build_index.py --corpus mdata_novel.pkl --output rag_baseline/novel_index
    python3 rag_baseline/build_index.py --corpus data/hotpotqa/mdata_hotpotqa.pkl --output rag_baseline/hotpotqa_index
"""
import argparse
import os
import pickle
import sys
import time

import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

EMBED_MODEL = "HIT-TMG/KaLM-embedding-multilingual-mini-instruct-v2"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, help="Path to .pkl corpus file")
    parser.add_argument("--output", required=True, help="Output directory for index")
    parser.add_argument("--batch_size", type=int, default=64)
    args = parser.parse_args()

    print(f"Loading corpus from {args.corpus}")
    with open(args.corpus, "rb") as f:
        docs = pickle.load(f)
    print(f"  {len(docs)} documents")

    print(f"Loading embedding model: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL, trust_remote_code=True)

    print(f"Encoding {len(docs)} documents (batch_size={args.batch_size})...")
    t0 = time.time()
    embeddings = model.encode(
        docs,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    encode_time = time.time() - t0
    print(f"  Encoded in {encode_time:.1f}s, shape: {embeddings.shape}")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype(np.float32))
    print(f"  FAISS index: {index.ntotal} vectors, dim={dim}")

    os.makedirs(args.output, exist_ok=True)
    faiss.write_index(index, os.path.join(args.output, "index.faiss"))
    with open(os.path.join(args.output, "docs.pkl"), "wb") as f:
        pickle.dump(docs, f)
    with open(os.path.join(args.output, "meta.json"), "w") as f:
        import json
        json.dump({
            "corpus": args.corpus,
            "num_docs": len(docs),
            "embed_model": EMBED_MODEL,
            "dim": dim,
            "encode_time_sec": round(encode_time, 1),
        }, f, indent=2)

    print(f"Saved to {args.output}/")


if __name__ == "__main__":
    main()
