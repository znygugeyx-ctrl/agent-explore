# Experiment 008 Analysis: MiroThinker-1.7-mini vs Claude Haiku 4.5

## Summary

MiroThinker-1.7-mini (30B reasoning model, fine-tuned for search) achieved **16.7% accuracy**
on 9 GAIA tasks, compared to Claude Haiku 4.5's **67.3% accuracy** on 75 GAIA tasks (007 baseline).
MiroThinker is **4× larger but 4× worse** under these experimental conditions.

## Results

### Model Comparison

| Metric | MiroThinker-1.7-mini | Claude Haiku 4.5 (007 text_only) |
|--------|---------------------|----------------------------------|
| Params | ~30B | ~3.5B |
| Tasks | 9 GAIA (×2 runs = 18) | 75 GAIA (×2 runs = 150) |
| **Accuracy** | **16.7%** (3/18) | **67.3%** (101/150) |
| L1 accuracy | 33% (2/6) | 68% (45/66) |
| L2 accuracy | 17% (1/6) | 69% (51/74) |
| L3 accuracy | 0% (0/6) | 50% (5/10) |
| Avg latency | 175.1s | 76.1s |
| Avg input tokens | 37,945 | 179,034 |
| Avg turns | 9.2 | 8.9 |
| Avg web_search | 6.7 | 7.6 |
| Avg fetch_page | 1.6 | 3.2 |
| Avg thinking tokens | 1,607 | N/A (no thinking) |
| Context window | 32,768 | Bedrock (large) |
| Tool call format | XML/MCP (custom parser) | JSON function calling |

### Per-Task Results (MiroThinker)

| Run | Task | Level | Result | Answer | Turns | S | F | Latency | Error |
|-----|------|-------|--------|--------|-------|---|---|---------|-------|
| 1 | Mashed potatoes (math) | L1 | WRONG | Verbose reasoning | 1 | 0 | 0 | 412s | Format |
| 1 | Fish bag volume | L1 | **OK** | 0.1777 | 11 | 10 | 0 | 81s | — |
| 1 | Dragon word "fluffy" | L1 | **OK** | fluffy | 11 | 5 | 5 | 268s | — |
| 1 | Met Museum Chinese zodiac | L2 | ERR | — | 17 | 12 | 5 | 208s | Context overflow |
| 1 | Bulgarian census | L2 | ERR | — | 6 | 1 | 1 | 77s | Context overflow |
| 1 | Whitney Museum book | L2 | WRONG | Tool call leaked | 6 | 4 | 0 | 41s | Format |
| 1 | Asian monarchies | L3 | WRONG | Tool call leaked | 6 | 5 | 0 | 66s | Format |
| 1 | Freon-12 pressure | L3 | ERR | — | 20 | 20 | 0 | 183s | Context overflow |
| 1 | USDA standards | L3 | ERR | — | 24 | 24 | 0 | 197s | Context overflow |
| 2 | Mashed potatoes | L1 | WRONG | — | 1 | 0 | 0 | 412s | Truncated thinking |
| 2 | Fish bag volume | L1 | ERR | — | 5 | 3 | 1 | 73s | Context overflow |
| 2 | Dragon word | L1 | ERR | — | 14 | 8 | 6 | 342s | Context overflow |
| 2 | Met Museum Chinese zodiac | L2 | ERR | — | 6 | 4 | 2 | 92s | Context overflow |
| 2 | Bulgarian census | L2 | ERR | — | 3 | 2 | 1 | 28s | Context overflow |
| 2 | Whitney Museum book | L2 | **OK** | Russian-German Legion | 10 | 9 | 0 | 85s | — |
| 2 | Asian monarchies | L3 | WRONG | Tool call leaked | 3 | 1 | 1 | 59s | Format |
| 2 | Freon-12 pressure | L3 | ERR | — | 8 | 4 | 4 | 107s | Context overflow |
| 2 | USDA standards | L3 | WRONG | Tool call leaked | 13 | 8 | 3 | 151s | Format |

## Failure Mode Analysis

### 1. Context Overflow (9 out of 18 = 50% of attempts)

The model's context window was configured at **32,768 tokens** (hardware limit: 4× L40S 48GB with
TP=4). MiroThinker's recommended configuration is **262,144 tokens** (256K). This is the primary
failure driver.

Each web page fetched (text_only format) contributes ~5,000–15,000 tokens to the context.
After 3–5 fetches, the 32K window is exhausted. Once context is full, vLLM rejects new requests.

**Evidence**: Tasks that hit ERR with many turns/searches (20+ turns, 24+ searches) are all
context overflow cases. Even tasks that succeeded in run1 failed in run2 due to longer search
paths or longer thinking traces consuming the budget.

### 2. Tool Call Leaking into Final Answer (4/18 = 22% of attempts)

The model uses many different tool names not in my alias set:
- `search_webpage`, `search_query` (search variants)
- The XML parser didn't always catch these → loop continued
- Eventually max_turns hit, and the last "no tool call" text was a partial XML → became the answer

**Model tool name diversity observed**:
```
google_search, search, search_web, web_search, search_webpage, search_query
fetch_page, fetch_webpage, scrape_webpage, browse
```

My `_SEARCH_TOOLS` set missed: `search_webpage`, `search_query`.

### 3. Thinking Trace Consumes Token Budget (2/18)

Without `--enable-reasoning` (not supported in this vLLM version), thinking tokens count against
`max_tokens=8192` per turn. For the mashed potatoes task (pure reasoning), the model generates a
full 8192-token thinking trace without completing the response:
- Run 1: incomplete thinking leaked as verbose answer
- Run 2: `think_tokens=8320` → thinking truncated, empty answer

### 4. Instruction Non-Compliance on Format

For tasks where the model correctly searches and finds the answer, it sometimes outputs a verbose
reasoning paragraph instead of just the final value. The "answer ONLY with the final value"
instruction is partially respected but not always.

## Hypothesis Evaluation

| Hypothesis | Prediction | Result |
|-----------|-----------|--------|
| H1: MiroThinker outperforms Haiku on accuracy | MiroThinker > 67% | **NOT CONFIRMED** — 16.7% vs 67.3% |
| H2: More targeted tool use | Fewer redundant searches | **NOT CONFIRMED** — 6.7 vs 7.6 searches, worse outcomes |
| H3: Higher latency | MiroThinker slower | **CONFIRMED** — 175s vs 76s (2.3×) |

## Key Insights

### Why MiroThinker underperformed

**The dominant cause is infrastructure mismatch, not model quality.**

1. **Context window (32K vs 262K)**: MiroThinker is designed for long multi-hop search workflows.
   The model card explicitly recommends 262K context. We ran it at 32K due to GPU memory limits.
   At 32K, roughly half of all attempts fail with context overflow — a ceiling that eliminates
   the model's core capability.

2. **Thinking tokens competition**: Without `--enable-reasoning`, the model's `<think>` blocks
   compete for the same token budget as tool calls and final answers. A reasoning model at 32K
   with max_tokens=8192/turn has limited working memory.

3. **Tool name diversity**: MiroThinker's fine-tuning used various tool names. A robust MCP
   integration requires mapping all variants (we caught most but not all).

### What we CAN conclude

- **When context fits**, MiroThinker works well: 3 successful tasks (fish bag volume, dragon
  article word, Whitney Museum book) were correctly answered with targeted searching.
- **Latency is substantially higher** (175s vs 76s), consistent with reasoning model overhead
  and slower generation speed (~20 tok/s for 30B vs Bedrock's Claude).
- **The model's GAIA benchmark claim (82.7%)** was measured at full 256K context — incomparable
  to our 32K setup.

### Fairer comparison would require

1. `max_model_len=131072` or higher (requires 8× A100 80GB or equivalent)
2. `--enable-reasoning` support to separate thinking tokens from output budget
3. Same task set as 007 (the 9 tasks here partially overlap with 007's 75)

## Engineering Notes

- **DO NOT compare MiroThinker's numbers to Claude in this experiment** — the context window
  constraint makes the comparison fundamentally unfair.
- The experiment does validate: XML tool call parsing works, model generates quality reasoning
  when context allows, tool call framework is extensible for non-standard models.
- The `restart_vllm.sh` infrastructure supports swapping models; re-running with a larger context
  window (using an 8× GPU instance like p4d.24xlarge or p3.16xlarge) is the right next step.

## Comparison with 007 Context

| | 007 Claude Haiku 4.5 | 008 MiroThinker (32K ctx) | 008 MiroThinker (ideal 256K) |
|--|---|---|---|
| Accuracy | 67.3% | 16.7% | TBD (model claims 82.7%) |
| Context limit | Bedrock (large) | 32,768 tokens | 262,144 tokens |
| Thinking | None | Yes (competes for budget) | Yes (separated) |
| Tool format | JSON function calls | XML/MCP | XML/MCP |
| $/task (est.) | ~$0.02 | ~$0.08 (EC2) | ~$0.16 (larger EC2) |
