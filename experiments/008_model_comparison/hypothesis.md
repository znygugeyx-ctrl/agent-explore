# Experiment 008: Model Comparison — MiroThinker-1.7-mini vs Claude Haiku 4.5

## Background

Experiment 007 benchmarked Claude Haiku 4.5 on 9 GAIA tasks (3×L1, 3×L2, 3×L3) using 4
content-format strategies. The `text_only` strategy performed best on accuracy.

MiroThinker-1.7-mini is a 30B reasoning model fine-tuned by MiroMind for agentic web search.
It claims GAIA-Val-165 = 82.7% accuracy. Unlike Claude, it uses XML/MCP-style tool calling
(`<use_mcp_tool>` blocks) rather than standard OpenAI function calling.

## Research Questions

1. How does a purpose-built 30B search agent (MiroThinker) compare to a general-purpose 3B model
   (Claude Haiku 4.5) on the same GAIA tasks?
2. Does the XML tool-calling format affect the quality of tool use vs standard function calling?
3. What is the latency and cost trade-off (MiroThinker on vLLM vs Claude on Bedrock)?

## Hypotheses

**H1 (Accuracy)**: MiroThinker outperforms Claude Haiku 4.5 on GAIA tasks (especially L2/L3)
due to its larger size and search-focused fine-tuning.

**H2 (Tool use)**: MiroThinker makes more targeted search queries with fewer wasted fetches,
consistent with its fine-tuning on search tasks.

**H3 (Latency)**: MiroThinker has significantly higher per-task latency due to 30B model size
and reasoning tokens, despite vLLM's efficiency.

## Design

| Model | Provider | Tool Format | Content Format | Strategy |
|-------|----------|-------------|----------------|----------|
| MiroThinker-1.7-mini (30B) | vLLM (EC2 g6e.12xlarge, TP=4) | XML/MCP | text_only | custom loop |
| Claude Haiku 4.5 | Bedrock | JSON function calling | text_only | 007 baseline |

**Custom agent loop** for MiroThinker:
- Send messages as plain chat (no tools parameter)
- Describe tools in XML format in system prompt
- Parse `<use_mcp_tool>` blocks from responses
- Return results as `<tool_result>` user messages

## Tasks

Same 9 GAIA validation tasks as experiment 007:
- 3× Level 1 (factual lookup)
- 3× Level 2 (multi-step reasoning)
- 3× Level 3 (complex multi-hop)

## Metrics

- Accuracy (correct / total, by level)
- Average latency per task
- Average turns (assistant messages)
- Average tool calls (web_search + fetch_page)
- Average input tokens
- Thinking tokens (MiroThinker only)

## Predictions

If H1 is correct: MiroThinker L1 ≥ 90%, L2 ≥ 60%, L3 > Claude
If H1 is wrong: Similar or lower accuracy due to XML format friction

## Limitations

1. Only 9 tasks — high variance at low sample size
2. MiroThinker uses reasoning tokens which add latency; Claude Haiku 4.5 does not
3. Different deployment (vLLM vs Bedrock) makes cost/latency comparison imperfect
4. MiroThinker is compared against Claude Haiku 4.5 text_only results from 007, not re-run
5. Temperature 1.0 for MiroThinker (recommended) vs 0.0 for 007 Claude runs
