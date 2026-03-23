# Experiment 002: True Logit Masking + Multi-Turn Tasks

## Background

Experiment 001 tested the Manus article's "Mask, Don't Remove" hypothesis but had two critical limitations:

1. **Description-level masking only**: Added `[UNAVAILABLE]` prefix to tool descriptions, which is a weak form of masking that actually added token overhead and confused the model.
2. **Single-turn tasks**: Each task required only 1 tool call, so there was no opportunity for KV-cache effects to manifest across turns.

## Hypothesis

True token-level logit masking (via vLLM's `logit_bias` parameter) combined with multi-turn tasks will show different results from Experiment 001:

- **Logit Mask** should maintain accuracy equal to All/Remove (no description confusion) while preserving KV-cache stability across turns.
- **Remove** strategy may show higher latency in multi-turn tasks because the tool list changes each turn, causing prefix cache misses.
- **Description Mask** (control) should still underperform due to extra token overhead.

## Key Differences from Experiment 001

| Aspect | Exp 001 | Exp 002 |
|--------|---------|---------|
| Masking method | `[UNAVAILABLE]` in description | `logit_bias: {token_id: -100}` |
| Task type | Single-turn (1 tool call) | Multi-turn (2-3 tool calls) |
| Tool relevance | Fixed per task | Changes per turn |
| Strategies | All, Remove, Desc Mask | All, Remove, Logit Mask, Desc Mask |

## Predictions

1. **Accuracy**: All = Logit Mask = Remove > Desc Mask
2. **Latency (multi-turn)**: Logit Mask <= All < Desc Mask < Remove (if KV-cache matters)
3. **Token efficiency**: Remove < Logit Mask = All < Desc Mask

## Design

- 20 multi-step tasks, each requiring 2-3 tool calls with different tools per step
- 4 strategies compared across 3 runs each
- Per-turn metrics tracked (latency, tokens, tool accuracy)
- vLLM prefix cache metrics captured pre/post each strategy run

## Model

Qwen/Qwen3-8B via vLLM 0.18.0 with `--enable-prefix-caching --enable-auto-tool-choice --tool-call-parser hermes`
