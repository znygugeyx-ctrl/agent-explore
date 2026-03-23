# Experiment 003: Prefix Cache Validation at 50-Tool Scale

## Hypothesis

At 50-tool scale (~5,000-10,000 tokens of tool definitions), the Manus "Mask, Don't Remove" strategy will show measurable benefits through prefix cache preservation:

1. **Logit Mask** (constant prefix) will achieve similar prefix cache hit rates as **All** (baseline)
2. **Remove** and **Desc Mask** (varying prefix) will show lower cache hit rates
3. Lower cache hit rates will manifest as higher TTFT (Time to First Token)
4. All strategies will maintain similar task accuracy

## Background

Experiment 002 (v2) showed no meaningful difference between strategies at 8-tool scale (~1,200 tokens). The Manus article argues that tool definition changes invalidate the KV prefix cache, increasing latency. This effect should be observable only when:
- Tool definitions are large enough to dominate the prefix
- TTFT is measured (reflects prefill latency, where cache hits matter)
- Conversations are long enough for cache reuse across turns

## Design

- **50 tools**: 10 filler (front of list, removal targets) + 40 active
- **20 tasks**: 4-6 step chains using 3-6 active tools each
- **4 strategies**: All, Remove (10 front tools), Logit Mask (same 10), Desc Mask (same 10)
- **Metrics**: TTFT per turn, vLLM prefix cache hit/miss rates, accuracy, latency

## Expected Outcomes

| Strategy | Prefix constant? | Expected TTFT | Expected cache hit rate |
|----------|-----------------|---------------|------------------------|
| All | Yes | Low | High |
| Logit Mask | Yes | Low | High |
| Desc Mask | No | Higher | Low |
| Remove | No | Higher | Low |

## Comparison with v2

This experiment directly extends 002 v2. Key differences:
- 50 tools (vs 8) — larger prefix, more cache-sensitive
- TTFT measurement — direct proxy for prefill latency
- vLLM cache metrics — ground truth for cache behavior
- 4-6 step tasks (vs 2-3) — more turns for cache reuse
