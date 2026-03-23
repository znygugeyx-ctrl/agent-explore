# Experiment 001: Mask vs Remove Tools

## Hypothesis

From the Manus article "Context Engineering for AI Agents":

> When dynamically managing which tools an LLM agent can use, **masking** tools
> (keeping them in the tool list but marking as unavailable) performs better than
> **removing** tools from the list entirely.

Two claimed mechanisms:

1. **KV-cache preservation**: Tool definitions are part of the prompt prefix.
   Removing tools changes the prefix, breaking prefix caching in inference
   engines (vLLM `--enable-prefix-caching`). Masking keeps the prefix stable.

2. **Schema consistency**: The model "expects" a stable tool schema. Removing
   tools mid-conversation can cause hallucinated tool calls or schema violations.

## Experimental Design

### Independent Variable: Tool selection strategy

Three conditions:

| Strategy | Description |
|----------|-------------|
| **All** (baseline) | All 8 tools always visible. No filtering. |
| **Remove** | Only task-relevant tools included in tool list. Others removed entirely. |
| **Mask** | All 8 tools included, but irrelevant tools marked as `[UNAVAILABLE]` in description. |

### Dependent Variables

1. **Accuracy**: Did the model call the correct tool with correct arguments?
2. **Latency**: Wall-clock time per request (proxy for KV-cache efficiency).
3. **Token usage**: Input + output tokens (removing tools reduces input tokens).
4. **Invalid tool calls**: Did the model call a tool it shouldn't have?
   - For "All": called any tool not in `relevant_tools`
   - For "Remove": N/A (irrelevant tools not available)
   - For "Mask": called a tool marked `[UNAVAILABLE]`

### Controls

- Same model: Qwen3-8B via vLLM with `--enable-prefix-caching`
- Same system prompt (except tool definitions differ per strategy)
- Same task set: 20 tasks across 8 tool domains
- Sequential execution: tasks run in same order, allowing prefix cache to warm
- Temperature: 0.0 (deterministic for reproducibility)
- Multiple runs (3) per strategy for statistical significance

### Tools (8 total)

1. `calculator` - math expression evaluation
2. `string_reverse` - reverse a string
3. `char_count` - count character occurrences
4. `base_convert` - number base conversion
5. `caesar_cipher` - Caesar cipher encode/decode
6. `temperature_convert` - temperature unit conversion
7. `gcd` - greatest common divisor
8. `word_count` - count words in text

### Tasks

20 tasks, 2-3 per tool. Each task specifies which tools are relevant.
Tasks are designed to have clear, deterministic answers for automated verification.

## Predictions

If the Manus article is correct:
- **Accuracy**: Mask >= All > Remove (Remove may cause wrong tool selection)
- **Latency**: Mask ≈ All < Remove (Remove breaks prefix cache)
- **Token usage**: Remove < Mask ≈ All (Remove has fewer input tokens)
- **Invalid calls**: Mask < All (Mask explicitly discourages unavailable tools)

## Infrastructure

- Model: Qwen/Qwen3-8B
- Server: vLLM 0.18.0 on AWS g6e.2xlarge (L40S 48GB)
- Flags: `--enable-prefix-caching --enable-auto-tool-choice --tool-call-parser hermes`
- Access: SSH tunnel localhost:8000
