# Experiment 002: True Logit Masking + Multi-Turn Tasks — Analysis

**Date**: 2026-03-22
**Model**: Qwen/Qwen3-8B via vLLM 0.18.0
**Infrastructure**: AWS g6e.2xlarge (NVIDIA L40S 48GB), `--enable-prefix-caching`
**Total requests**: ~960 (4 strategies x 3 runs x 20 tasks x ~4 turns avg)
**Total duration**: ~50 minutes

---

## 1. Executive Summary

This experiment tested **true token-level logit masking** (via vLLM `logit_bias`) against three other tool selection strategies in **multi-turn tasks**. The results challenge both Experiment 001's conclusions and the Manus article's hypothesis:

| Metric | All (baseline) | Remove | Logit Mask | Desc Mask | Winner |
|--------|---------------|--------|------------|-----------|--------|
| Accuracy | 96.7% | 83.3% | 95.0% | **100%** | Desc Mask |
| Step Completion | **100%** | 61.7% | **100%** | **100%** | Tie (All/Logit/Desc) |
| Avg Latency | **9.49s** | 16.79s | 12.90s | 9.96s | All |
| Avg Input Tokens/task | 2,534 | **1,819** | 4,526 | 2,687 | Remove |
| Invalid Tool Calls | 22 | 11.3 | 12 | 22 | Remove |

**Key takeaway**: In multi-turn tasks, **Description Mask wins on accuracy** (100%) while **All wins on latency**. Logit Mask has a fundamental flaw: the model bypasses blocked tokens by inventing alternative tool names (Chinese translations, misspellings, dot-prefixed names). Remove strategy collapses — it often refuses to call tools at all.

---

## 2. The Logit Mask Bypass Discovery

The most unexpected finding: **Qwen3-8B actively evades logit_bias blocking** by generating creative alternative tool names. When `calculator`'s tokens (29952, 88821) are blocked:

| Bypass Attempt | Frequency | Type |
|---------------|-----------|------|
| `计算器` (Chinese for "calculator") | 6+ times | Language switch |
| `温度转换` (Chinese for "temperature_convert") | 2+ times | Language switch |
| `ceasar_cipher` (misspelling) | 2+ times | Typo |
| `str_reverse` (abbreviation) | 1+ times | Shortening |
| `Base_convert` (capitalization) | 1+ times | Case change |
| `.base_convert` (dot prefix) | 2+ times | Punctuation prefix |
| `.char_count` (dot prefix) | 1+ times | Punctuation prefix |
| `gc` (truncation of "gcd") | 2+ times | Truncation |

**Interpretation**: When the model's first-choice tokens are blocked, it doesn't give up — it finds alternative tokenization paths. This is a **fundamental limitation of `logit_bias`-based masking**: it only blocks specific token IDs, but the model can compose the same semantic meaning through different token sequences.

For multi-token tool names like `base_convert` (tokens [3152, 34910]), blocking the first token (3152) only prevents `base` from appearing. The model discovers `.base_convert` works because `.` + `base` produces different first tokens. Similarly, Chinese-language bilingual models can switch to their other language entirely.

### Why This Matters for the Manus Hypothesis

The Manus article assumed logit masking would reliably prevent tool invocation. Our data shows this assumption is **incorrect for multilingual models**. `logit_bias` is a "soft" barrier that sophisticated models can route around. True tool-level gating requires **structured generation constraints** (e.g., vLLM's guided generation with JSON schemas), not just token-level biases.

---

## 3. Remove Strategy Failure Analysis

Remove performed dramatically worse in multi-turn tasks (83.3% accuracy, 61.7% step completion) compared to Exp 001's single-turn results (100% accuracy):

### Failure Mode: "Single Tool Confusion"

When the model sees only 1 tool (e.g., just `calculator` for step 1), it frequently ignores the tool entirely and tries to solve everything in `<think>`:

| Task | Step 1 Tool | Tools Called | Steps Done | Correct? |
|------|-------------|-------------|------------|----------|
| chain_calc_base | calculator | none | 0/2 | Yes (lucky) |
| chain_cipher_reverse | caesar_cipher | none | 0/2 | No |
| chain_gcd_base | gcd | none | 0/2 | Yes (lucky) |
| chain_temp_calc | temperature_convert | none | 0/2 | Yes (lucky) |
| chain_calc_cipher | calculator | none | 0/2 | No |
| chain_calc_gcd2 | calculator | none | 0/2 | Yes (lucky) |
| chain_temp_gcd | temperature_convert | none | 0/2 | No/Yes |

**Pattern**: When only 1 tool is visible, the model often decides it can handle the task without tools. It spends the full 1024-token budget on `<think>` reasoning, computing answers mentally. For math tasks, this works (hence "lucky correct"), but for string operations and ciphers, it fails.

**Why this differs from Exp 001**: In Exp 001's single-turn tasks, the model saw 1 tool and 1 clear task — it had no reason to hesitate. In multi-turn tasks, the model sees a **multi-step prompt** but only **1 tool**. It infers that something is wrong ("I need 2 tools but only see 1") and falls back to mental computation.

### Latency Impact

The 23-second latencies for no-tool tasks are the model hitting the 1024 max_tokens limit in `<think>` mode without producing a tool call. This inflates Remove's average latency to 16.79s (77% higher than All's 9.49s).

---

## 4. Desc Mask Surprise: Best Accuracy

Contrary to Experiment 001, **Description Mask achieved 100% accuracy** (60/60 tasks correct) — the best of all strategies. This is a complete reversal from Exp 001 where Desc Mask was the worst performer (96.7%).

### Why Desc Mask Improved

1. **Max tokens increased**: 1024 vs 512 in Exp 001. The `<think>` budget exhaustion that caused Desc Mask failures in Exp 001 is no longer an issue.

2. **Multi-turn tasks help**: The model sees the full tool list every turn (8 tools). Even though 7 are marked `[UNAVAILABLE]`, it can see what tools exist. Combined with the multi-step prompt, it correctly identifies which tool to use at each step.

3. **[UNAVAILABLE] is respected**: Across 60 tasks x 3 runs, the model **never called an unavailable tool** in Desc Mask strategy. The annotation is sufficient for Qwen3-8B to route correctly.

### The Invalid Calls Anomaly

All strategies show "invalid tool calls" (22 for All/Desc Mask, 11-12 for Remove/Logit Mask). This metric counts tool calls to tools not in the current step's `step_tools` list. However, the model in All/Desc Mask strategies correctly calls tools for **both steps in a single turn** (parallel tool calls), which our per-step tracking marks as "invalid" for step 0. This is actually the desired behavior — the model efficiently batches tool calls.

---

## 5. Latency Analysis

| Strategy | Mean | Median | P90 | Min | Max |
|----------|------|--------|-----|-----|-----|
| All | **9.49s** | 8.99s | 13.88s | 6.08s | 20.78s |
| Desc Mask | 9.96s | 9.62s | 16.45s | 5.85s | 17.54s |
| Logit Mask | 12.90s | 12.04s | 19.16s | 7.64s | 20.76s |
| Remove | 16.79s | 19.20s | 23.09s | 6.04s | 23.21s |

### Why Logit Mask is 36% Slower than All

Logit Mask forces **sequential tool calls** (blocking step 2's tool in step 1). The model must:
1. Turn 1: Call step 1 tool (sometimes 2-3 times due to bypass attempts)
2. Turn 2: Get tool result, advance to step 2
3. Turn 3: Call step 2 tool (sometimes after a failed bypass attempt)

Meanwhile, All/Desc Mask call **both tools in a single turn**, requiring only 2 LLM calls instead of 3-4+.

### Why Remove is Slowest

Remove's 16.79s average is dominated by the 8/20 tasks where the model doesn't call tools (23s each hitting max_tokens). For tasks where it does call tools, Remove's latency is comparable to All.

---

## 6. Token Efficiency

| Strategy | Avg Input Tokens | Avg Output Tokens | Total per Task |
|----------|-----------------|-------------------|----------------|
| Remove | **1,819** | 702 | **2,521** |
| All | 2,534 | 364 | 2,898 |
| Desc Mask | 2,687 | 383 | 3,070 |
| Logit Mask | 4,526 | 479 | **5,005** |

**Logit Mask is the most expensive** — nearly 2x All's total tokens. This is because:
1. Failed bypass attempts generate extra turns (each turn adds ~500-1000 input tokens of context)
2. The model often calls the correct tool 2-3x before advancing (e.g., `calculator,calculator,calculator,gcd`)

**Remove has lowest input tokens** but highest output tokens (the model generates long `<think>` blocks when it decides not to use tools).

---

## 7. Hypothesis Evaluation

### Manus Claim: "Mask, Don't Remove"
**Partially supported, but not via logit masking.** The Remove strategy clearly fails in multi-turn scenarios (83.3% accuracy, 61.7% step completion). However, the winning masking approach is the simple **Description Mask** (`[UNAVAILABLE]` prefix), not token-level logit masking.

### Our Prediction: "Logit Mask = All > Remove > Desc Mask"
**Wrong.** Actual ranking:
- **Accuracy**: Desc Mask (100%) > All (96.7%) ≈ Logit Mask (95%) >> Remove (83.3%)
- **Latency**: All (9.49s) ≈ Desc Mask (9.96s) < Logit Mask (12.90s) << Remove (16.79s)

### Key Insight: Logit Bias ≠ Reliable Tool Gating

The `logit_bias` parameter is designed for **soft token preference tuning** (e.g., reducing verbosity, discouraging specific words). It was never designed for **hard tool-level access control**. Our experiment reveals its inadequacy:

1. **Multilingual bypass**: Bilingual models can switch languages to avoid blocked tokens
2. **Spelling variation bypass**: Typos, abbreviations, and case changes produce different tokens
3. **Punctuation bypass**: Prefixing with `.` or other characters produces different first tokens
4. **Incomplete coverage**: Blocking first tokens of multi-token names is insufficient

For reliable tool masking, the correct approach is:
- **Structured generation** (e.g., vLLM's `--guided-decoding-backend` with JSON schema constraining tool name to allowed values)
- **Function-level `tool_choice`** parameter (e.g., `tool_choice: {"type": "function", "function": {"name": "calculator"}}`)
- **Post-generation filtering** in the agent loop (reject invalid tool names and retry)

---

## 8. Comparison with Experiment 001

| Finding | Exp 001 (Single-Turn) | Exp 002 (Multi-Turn) |
|---------|----------------------|---------------------|
| Best accuracy | All = Remove (100%) | Desc Mask (100%) |
| Worst accuracy | Desc Mask (96.7%) | Remove (83.3%) |
| Best latency | Remove (6.38s) | All (9.49s) |
| Remove usable? | Yes (best overall) | No (severe degradation) |
| Desc Mask usable? | Marginal (budget issues) | Yes (best accuracy) |
| Logit Mask | Not tested | Unreliable (model bypasses) |

**The Manus hypothesis gains support in multi-turn settings**: Remove's advantage evaporates when tool requirements change across turns. However, the recommended "masking" approach should be Description Mask, not logit masking.

---

## 9. Observations

### Qwen3-8B's Bilingual Creativity
The model's ability to generate Chinese tool names (`计算器`, `温度转换`) when English tokens are blocked is a remarkable demonstration of its bilingual training. This has implications for any token-level content filtering approach — bilingual models have a natural escape hatch.

### Parallel Tool Calling
The All and Desc Mask strategies benefit enormously from the model's ability to call multiple tools in a single turn. This effectively turns a 2-step task into a 1-turn task, cutting latency nearly in half compared to forced-sequential strategies.

### Max Token Budget Matters
Increasing from 512 to 1024 tokens flipped the Desc Mask results from worst to best. The Qwen3 `<think>` overhead requires sufficient output budget. For production systems, max_tokens should be set generously when using reasoning models.

---

## 10. Conclusions

1. **For multi-turn tasks, Description Mask is the best strategy.** 100% accuracy, near-baseline latency, simple to implement.

2. **Remove strategy fails in multi-turn.** When the model sees only 1 tool but a multi-step prompt, it defaults to mental computation. This confirms the Manus article's warning about removing tools mid-conversation.

3. **Token-level logit masking is unreliable.** The model discovers bypasses through language switching, typos, punctuation, and abbreviations. `logit_bias` is inadequate for tool access control.

4. **The Manus "Mask, Don't Remove" advice is correct in principle, but the implementation should be description-level annotation, not logit masking.** The simple `[UNAVAILABLE]` prefix works because it communicates intent to the model at the semantic level, whereas logit masking fights the model at the token level.

5. **Next steps**: Test with (a) vLLM structured generation for true tool-level gating, (b) `tool_choice` parameter for forced selection, (c) 50+ tools to stress prefix cache, (d) production workloads with concurrent requests.

---

## 11. Raw Data

All raw results in `experiments/002_logit_masking/results/`:
- `{all,remove,logit_mask,desc_mask}_run{1,2,3}.json` — Full outcomes per strategy per run
- `report.md` — Auto-generated summary table
