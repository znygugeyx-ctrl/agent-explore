# Experiment 015: Quantized Large Models vs Full-Precision Small Models

## Status: DESIGN (in discussion)

## Background

A fundamental deployment decision: given a fixed VRAM budget, should you run a larger model with aggressive quantization (AWQ-4bit) or a smaller model at full precision (FP16)? The answer likely depends on task type, architecture (Dense vs MoE), and the VRAM tier.

This experiment aims to map the **quality-efficiency Pareto frontier** across these dimensions on a single L40S (48GB) GPU.

## Core Question

> "Under equivalent VRAM usage, does a quantized large model outperform a full-precision small model? How does the answer change by task type, model architecture, and VRAM tier?"

## Hypotheses

**H1 (Knowledge tasks favor large+quantized):** On knowledge-intensive benchmarks (MMLU), larger quantized models retain more world knowledge than smaller FP16 models at the same VRAM footprint, because parameter count correlates with knowledge capacity.

**H2 (Reasoning may not favor either clearly):** On multi-step reasoning (GSM8K), the outcome is uncertain — quantization degrades numerical precision but larger models have stronger reasoning circuits. This is the most interesting empirical question.

**H3 (Simple tasks favor small+FP16):** On shallow extraction/classification tasks, small FP16 models match or beat quantized large models while being significantly faster.

**H4 (MoE is the Pareto winner):** MoE architectures (Qwen3-30B-A3B) combine large knowledge capacity with fast inference (low active params), potentially dominating both strategies across tasks.

**H5 (Throughput advantage of small models is consistent):** Small FP16 models always decode faster and handle more concurrent requests, because fewer parameters = less memory bandwidth consumed per token.

## Experimental Design

### Independent Variables

**Dimension 1: VRAM Tier (controls "budget")**

| Tier | VRAM Usage | Real-world analogy |
|------|-----------|-------------------|
| ~5GB | Ultra-light | Edge devices / multi-model coexistence |
| ~16-18GB | Medium | Consumer GPU (half of 4090) |
| ~28-40GB | Heavy | Full L40S utilization |

**Dimension 2: Strategy**

- Small model + FP16 (high precision, low parameters)
- Large model + AWQ-4bit (quantized, high parameters)
- MoE + AWQ-4bit (large knowledge, low active params) — where available

**Dimension 3: Architecture**

- Dense
- Mixture-of-Experts (MoE)

### Model Matrix

**Tier 1 (~5GB VRAM)**

| Role | Model | Precision | Params | Architecture | VRAM Est. |
|------|-------|-----------|--------|--------------|-----------|
| Small+FP16 | Qwen3-1.7B | FP16 | 1.7B | Dense | ~4GB |
| Large+Quantized | Qwen3-8B | AWQ-4bit | 8B | Dense | ~5GB |

**Tier 2 (~16-18GB VRAM)**

| Role | Model | Precision | Params | Architecture | VRAM Est. |
|------|-------|-----------|--------|--------------|-----------|
| Small+FP16 | Qwen3-8B | FP16 | 8B | Dense | ~16GB |
| Large+Quantized | Qwen3-32B | AWQ-4bit | 32B | Dense | ~18GB |
| Large+Quantized (MoE) | Qwen3-30B-A3B | AWQ-4bit | 30B (3B active) | MoE | ~17GB |

**Tier 3 (~28-40GB VRAM)**

| Role | Model | Precision | Params | Architecture | VRAM Est. |
|------|-------|-----------|--------|--------------|-----------|
| Small+FP16 | Qwen3-14B | FP16 | 14B | Dense | ~28GB |
| Large+Quantized | Qwen3-72B | AWQ-4bit | 72B | Dense | ~40GB |

### Dependent Variables

**Quality Metrics (Benchmark Performance):**

| Task Type | Benchmark | What it tests | Why chosen |
|-----------|-----------|---------------|------------|
| Knowledge/comprehension | MMLU (5-shot) | World knowledge breadth | Large models should excel (more knowledge compressed) |
| Mathematical reasoning | GSM8K | Multi-step reasoning | Quantization may hurt reasoning chains |
| Code generation | HumanEval | Programming ability | Practical + public baselines available |
| Simple extraction | TBD (NER/classification) | Shallow understanding | Expected: small models sufficient |

**Efficiency Metrics:**

| Metric | Method |
|--------|--------|
| Decode speed | Fixed prompt, single request, measure output tokens/sec |
| TTFT | Fixed prompt lengths (128/512/2048 tokens), measure first token latency |
| Concurrent throughput | Simultaneous 1/4/8/16 requests, measure total tokens/sec |
| Concurrent latency | Same as above, measure P50/P99 per-request latency |

**Composite Metrics (Core Output):**

- **Quality per VRAM** = benchmark_score / vram_used
- **Tokens per VRAM** = throughput / vram_used
- **Quality-adjusted throughput** = (normalized_score × tokens_per_sec) — the single number that captures "smart AND fast"

### Control Variables

- Hardware: single g6e.2xlarge instance (1× L40S 48GB) for all runs
- Software: vLLM with same version across all models
- Temperature: 0 for benchmarks (greedy decoding)
- Model family: all Qwen3 (controls for training data/architecture differences)
- Quantization method: AWQ-4bit consistently (not GPTQ/GGUF)

## Infrastructure

- Instance: g6e.2xlarge (1× L40S 48GB, ~$2.2/hr)
- All models fit within 48GB, tested sequentially on the same instance
- vLLM with Hermes tool-call parser
- For Tier 3 72B-AWQ (~40GB model weights), KV cache space will be limited — this is part of the measurement (concurrent capacity suffers)

## Open Design Questions (To Be Resolved)

### 1. VRAM equivalence tolerance

Tier 2: 8B-FP16 (16GB) vs 32B-AWQ (18GB) — 12% difference, acceptable.
Tier 3: 14B-FP16 (28GB) vs 72B-AWQ (40GB) — 43% difference.

Options:
- **Strict control**: Use vLLM `gpu_memory_utilization` to force equal VRAM → smaller model gets more KV cache → concurrency advantage
- **Natural comparison**: Each model uses optimal config, accept VRAM difference as "cost of choosing that model"

Leaning toward: natural comparison (more practical), but report the VRAM difference.

### 2. MoE classification

Qwen3-30B-A3B: 30B total params (VRAM ~17GB AWQ), 3B active params (compute speed).
Should it be classified as:
- "Large+Quantized" camp (30B params, AWQ)?
- A third strategy: "MoE = large knowledge + fast inference + moderate VRAM"?

Leaning toward: third strategy (3-way comparison where available).

### 3. Benchmark selection for "simple tasks"

Need a benchmark where small models are expected to be sufficient. Candidates:
- AG News classification
- Some NER dataset
- Simple QA extraction

### 4. Statistical design

- How many samples per benchmark? (MMLU has ~14K, GSM8K ~1.3K, HumanEval 164)
- Do we run full benchmarks or subsets?
- How many repetitions for throughput measurements?

## Expected Findings (Predictions)

If hypotheses are correct, we expect a pattern like:

```
Task Type        →  Knowledge(MMLU)   Reasoning(GSM8K)   Code(HumanEval)   Simple(NER)
                    ──────────────     ───────────────    ──────────────    ──────────
Large+Quantized     ★★★★              ★★★?               ★★★               ★★
Small+FP16          ★★                ★★★?               ★★                ★★★
MoE+Quantized       ★★★★              ★★★                ★★★               ★★★
```

Throughput (all tiers):
```
Small+FP16 >> MoE+Quantized > Large+Quantized (Dense)
```

The "killer finding" would be identifying the **crossover point**: at what task complexity does the quality advantage of large+quantized models justify their throughput penalty?

## Limitations

- Single GPU architecture (L40S) — results may differ on A100/H100 with different memory bandwidth
- Single model family (Qwen3) — architecture-specific quantization sensitivity may not generalize
- AWQ-4bit only — other quantization methods (GPTQ, GGUF, FP8) may shift the boundary
- Small sample for throughput measurements — real production load patterns are more complex
