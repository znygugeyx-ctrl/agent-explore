# Experiment 013: MSA Novel Memory

## Background

Memory Sparse Attention (MSA, EverMind-AI) is an end-to-end trainable sparse latent-memory framework
that claims to handle up to 100M token contexts. It fuses retrieval into attention layers — documents
are compressed into KV cache via chunk-mean pooling and stored in CPU DRAM, with routing keys on GPU.
At query time, a learned router selects top-k relevant documents and loads their KV for generation.

We deploy MSA-4B (Qwen3-4B backbone) on g6e.12xlarge (4×L40S, 384GB RAM) and test it on a
6.34M character Chinese web novel (蛊真人, 2345 sections, ~5.89M tokens).

## Hypotheses

### H1: MSA can memorize and retrieve from a single large novel
Given the full novel as memory, MSA should be able to answer factual questions about characters,
events, and relationships by retrieving the correct sections.

### H2: Retrieval quality degrades for cross-section reasoning
Questions requiring information from multiple non-adjacent sections (multi-hop) will have lower
accuracy than single-section factual lookups, since top-k=16 may not cover all relevant sections.

### H3: MSA outperforms naive RAG on novel QA
Compared to a standard RAG pipeline (embedding + vector search + LLM), MSA's end-to-end learned
routing should better handle the novel's narrative structure and implicit references.

## Method

### Phase 1: Manual Testing (方案B)
- Deploy MSA as a persistent FastAPI service with encoding cache
- Interactive CLI for manual question-answering
- Qualitative assessment of retrieval and answer quality

### Phase 2: Automated Evaluation (方案A, future)
- Generate 100+ QA pairs from the novel using LLM (factual, multi-hop, character relations)
- Run batch evaluation via /batch endpoint
- Score with LLM judge
- Compare with RAG baseline

## Infrastructure
- Instance: g6e.12xlarge (4×L40S 48GB each, 384GB RAM)
- Model: MSA-4B (Qwen3-4B-Instruct backbone, fine-tuned with curriculum SFT)
- Encoding time: ~2.5 min for 5.89M tokens (with disk cache for subsequent runs)
- Memory footprint: ~92K chunks, ~2.3% of theoretical GPU capacity
