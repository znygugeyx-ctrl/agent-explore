# Experiment 001: Mask vs Remove Tools — Analysis

**Date**: 2026-03-22
**Model**: Qwen/Qwen3-8B via vLLM 0.18.0
**Infrastructure**: AWS g6e.2xlarge (NVIDIA L40S 48GB), `--enable-prefix-caching`
**Total requests**: 180 (3 strategies × 3 runs × 20 tasks)
**Total duration**: ~23 minutes

---

## 1. Executive Summary

The Manus article's "Mask, Don't Remove" hypothesis is **NOT supported** by this experiment. In fact, the **Remove** strategy outperformed both alternatives across all metrics:

| Metric | All (baseline) | Remove | Mask | Winner |
|--------|---------------|--------|------|--------|
| Accuracy (corrected) | **100%** | **100%** | 96.7% | All = Remove |
| Avg Latency | 8.15s | **6.38s** | 7.95s | Remove |
| Avg Input Tokens/task | 2,262 | **793** | 2,423 | Remove |
| Avg Output Tokens/task | 304 | **228** | 295 | Remove |
| Invalid Tool Calls | 0 | 0 | 0 | Tie |

**Key takeaway**: Removing irrelevant tools yielded the fastest, most token-efficient, and equally accurate results. Masking tools added overhead without benefit.

---

## 2. Accuracy Analysis

### Raw Results (before correction)

| Strategy | Run 1 | Run 2 | Run 3 | Mean |
|----------|-------|-------|-------|------|
| All      | 95.0% | 95.0% | 95.0% | 95.0% |
| Remove   | 95.0% | 95.0% | 100%  | 98.3% |
| Mask     | 95.0% | 90.0% | 90.0% | 91.7% |

### Data Quality Issue

Task `char_03` ("How many 'e' in 'experimentation'?") had **incorrect expected answer** (2 instead of 3). The model correctly answered 3 every time. After correction:

| Strategy | Run 1 | Run 2 | Run 3 | Mean |
|----------|-------|-------|-------|------|
| All      | 100%  | 100%  | 100%  | **100%** |
| Remove   | 100%  | 100%  | 100%  | **100%** |
| Mask     | 100%  | 95.0% | 95.0% | **96.7%** |

### Mask Strategy Failure Mode

The Mask strategy's 2 failures (both on `char_02`) share the same pattern:
- The model **did not call any tool** — it tried to answer in its `<think>` block
- Qwen3's thinking consumed the entire 512-token output budget
- No final answer was produced outside the `<think>` block
- The longer masked tool descriptions (8 tools × "[UNAVAILABLE]" prefix) added ~160 extra input tokens, giving the model more "context to reason over"

**Interpretation**: With 8 tool descriptions visible (including 7 marked unavailable), the model spent more reasoning tokens deciding which tool to use, occasionally exceeding the output budget without completing.

---

## 3. Latency Analysis

| Strategy | Mean | Median | P90 | Min | Max |
|----------|------|--------|-----|-----|-----|
| All      | 8.15s | 7.28s | 11.98s | 4.27s | 14.78s |
| Remove   | **6.38s** | **5.91s** | **9.25s** | **4.22s** | 11.88s |
| Mask     | 7.95s | 7.15s | 12.71s | 4.30s | 17.23s |

Remove is **22% faster** than All and **20% faster** than Mask.

### Why Remove is Faster (contradicting the KV-cache hypothesis)

The Manus article predicted Remove would break prefix caching, making it slower. Our data shows the opposite. Likely reasons:

1. **Input token reduction dominates**: Remove uses ~793 input tokens/task vs ~2,262 for All. With only 1 tool definition instead of 8, the prompt is 65% smaller. This reduction in prefill computation far outweighs any prefix cache benefits.

2. **Prefix cache benefit is marginal at this scale**: With 8 simple tools, the shared prefix (system prompt + tool definitions) is ~1,000 tokens. vLLM's prefix caching operates on 16-token blocks. The cache savings of ~1,000 tokens is small relative to the 1,500 extra tokens that All/Mask strategies must process.

3. **Different tool sets share partial prefix**: Even in Remove mode, consecutive tasks using the same tool type (e.g., calc_01, calc_02, calc_03) share the same prefix. Only cross-domain transitions (calc → rev → char) cause full cache misses.

4. **Output generation is the bottleneck**: With more tools visible, the model generates longer `<think>` blocks reasoning about tool selection, increasing output tokens and latency.

### Cache Warmup Effect

Checking first-5 vs last-5 task latencies:

| Strategy | First 5 avg | Last 5 avg | Trend |
|----------|-------------|------------|-------|
| All      | 4.48s | 13.75s | Increasing |
| Remove   | 4.25s | 10.60s | Increasing |
| Mask     | 4.48s | 15.19s | Increasing |

**Surprising**: Latency increases over the sequence, not decreases. This is because later tasks (gcd, word_count) trigger longer thinking chains, not because of cache effects. The task ordering (by tool type) means later tasks happen to be harder.

---

## 4. Token Efficiency

| Strategy | Avg Input/task | Avg Output/task | Total/task |
|----------|---------------|----------------|-----------|
| All      | 2,262 | 304 | 2,566 |
| Remove   | **793** | **228** | **1,021** |
| Mask     | 2,423 | 295 | 2,718 |

Remove uses **60% fewer total tokens** than All and **62% fewer** than Mask.

Mask is slightly MORE expensive than All because:
- "[UNAVAILABLE - do not use this tool]" prefix adds ~7 tokens per masked tool
- 7 masked tools × 7 tokens = ~49 extra tokens per request

---

## 5. Tool Selection Accuracy

All three strategies achieved **0 invalid tool calls** across 180 requests. The model always selected the correct tool (when it selected a tool at all).

This suggests that for Qwen3-8B with clear task descriptions:
- Having extra tools visible does NOT confuse the model
- The "[UNAVAILABLE]" annotation in Mask is unnecessary — the model doesn't try unavailable tools
- With only 8 tools, tool selection is trivially easy regardless of strategy

---

## 6. Hypothesis Evaluation

### Manus Claim 1: "Removing tools breaks KV-cache"
**Not supported.** Remove was faster, not slower. At this scale (8 tools, single-turn), the prefix cache benefit is overwhelmed by the input token reduction benefit.

### Manus Claim 2: "Masking preserves schema consistency"
**Not supported.** Masking performed worse on accuracy (96.7% vs 100%) due to output budget exhaustion. The longer masked descriptions actually harmed performance.

### Caveats — When Mask Might Still Win

This experiment tests a narrow scenario. The Manus hypothesis may hold under different conditions:

1. **Many more tools (50-100+)**: With a very large tool set, the shared prefix becomes substantial. Removing vs keeping 100 tool definitions would have a much larger prefix cache impact. Our 8 tools are too few to show this effect.

2. **Multi-turn conversations**: Our tasks are single-turn. In multi-turn agent loops where the model has already "seen" a tool and built expectations, removing it mid-conversation could cause confusion. Our design doesn't test this.

3. **High-concurrency serving**: Prefix caching benefits increase with concurrent requests sharing the same prefix. Our sequential, single-user experiment doesn't stress this path.

4. **Longer system prompts**: If the system prompt is very long (10K+ tokens), the cache benefit of keeping it stable becomes more significant.

5. **Logit masking (not tested)**: The Manus article's strongest claim is about **token-level logit masking** during decoding (preventing the model from generating certain tool names), not just description-level "[UNAVAILABLE]" annotations. This requires access to the decoding process (e.g., vLLM's guided generation), which we did not implement. Our Mask strategy only modifies descriptions, which is a weaker form of masking.

---

## 7. Interesting Observations

### Qwen3 Thinking Overhead
Qwen3-8B's `<think>` blocks are a significant factor. The model routinely spends 50-150 tokens "thinking" before acting. With more visible tools, thinking tends to be longer:
- Remove avg output: 228 tokens
- All avg output: 304 tokens (+33%)
- Mask avg output: 295 tokens (+29%)

This suggests **tool list complexity directly increases reasoning overhead**.

### Deterministic Behavior at temperature=0
Despite temperature=0, we observed slight variation across runs:
- `char_02`: sometimes uses tool, sometimes answers directly
- `cipher_02`: occasionally doesn't call tool
- `calc_01` in All: Run 1 used 2 turns (2,509 tokens), Run 2 used 3 turns (5,724 tokens)

This non-determinism at temperature=0 likely comes from floating-point non-determinism in GPU computations and vLLM's scheduling.

---

## 8. Conclusions

1. **For small tool sets (≤10), Remove is the best strategy.** It's faster, cheaper, and equally accurate.

2. **Mask is the worst strategy in this setting.** The added description overhead increases thinking time and can cause output budget exhaustion.

3. **The Manus "Mask, Don't Remove" advice likely applies to larger-scale scenarios** (50+ tools, multi-turn, high concurrency) where prefix caching and schema stability matter more than prompt size.

4. **Token budget management matters.** The Mask failures were not tool selection errors but output budget problems. If using Mask, increase max_tokens to compensate for the longer thinking.

5. **Next steps**: Test with (a) 50+ tools, (b) multi-turn tasks, (c) actual logit masking via vLLM guided generation, (d) concurrent requests to stress prefix cache, (e) larger model (Qwen3-32B).

---

## 9. Raw Data

All raw results are in `experiments/001_mask_vs_remove/results/`:
- `all_run{1,2,3}.json` — Full outcomes for each All strategy run
- `remove_run{1,2,3}.json` — Full outcomes for each Remove strategy run
- `mask_run{1,2,3}.json` — Full outcomes for each Mask strategy run
- `report.md` — Auto-generated summary table
