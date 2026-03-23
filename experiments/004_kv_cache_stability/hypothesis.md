# Experiment 004: KV Cache Stability

## Background

The Manus "Context Engineering for AI Agents" article's "Design Around KV Cache" section
identifies three practices for maximizing prefix cache hit rate:

1. **Stable prefix**: A single token change at position N invalidates all tokens after N.
   Avoid timestamps (especially second-precision) in system prompts.
2. **Append-only context**: Never modify or truncate prior turns. Ensure deterministic
   JSON serialization (key ordering matters).
3. **Explicit cache breakpoints**: For providers without automatic incremental caching.

Previous experiments (001-003) varied *which tools to show the model* while assuming
stable context. This experiment directly validates claims 1 and 2 by measuring TTFT
(time-to-first-token) as a proxy for prefix cache hit rate.

## Hypotheses

- **H1 (stable)**: TTFT decreases across sequential tasks as the vLLM prefix cache
  warms up. By task 5, the system prompt + 50-tool definitions (~11K tokens) are cached,
  so turn 1 of subsequent tasks hits the cache → lower TTFT.

- **H2 (timestamp_s)**: Second-precision timestamp prepended to system prompt causes full
  prefix cache miss on virtually every LLM call (the second changes between turns in a
  multi-turn task). TTFT stays flat/high regardless of task ordering.

- **H3 (truncate)**: Keeping only the last 2 assistant-step groups breaks the append-only
  invariant. At turn 3+, the message history is NOT a superset of the prior turn's history
  → prefix cache miss. TTFT spikes at truncation events, then partially recovers.

## Design

| Strategy    | Hook             | Mechanism                               | Expected TTFT pattern     |
|-------------|------------------|-----------------------------------------|---------------------------|
| stable      | none             | Static prompt, append-only messages     | Decreasing across turns   |
| timestamp_s | before_llm_call  | Second-precision timestamp at prompt[0] | Flat/high across turns    |
| truncate    | context_transform| Keep only last 2 step-groups            | Spikes at truncation turns |

**All strategies use all 50 tools** — tool selection is held constant. Only context
stability varies.

**Sequential execution**: Tasks run one-by-one within each strategy run (no parallelism).
This allows genuine cross-task prefix cache warmup for the `stable` strategy.

**Temperature 0.0**: Deterministic outputs reduce TTFT variance from output length.

## Tools and Tasks

- 50 tools imported from Experiment 003 (unchanged)
- 20 multi-step tasks (4-6 steps each) imported from Experiment 003

## Primary Metric

TTFT by turn number, aggregated across tasks — the 2D pattern is more informative than
any aggregate.

## Secondary Metrics

- vLLM prefix cache hit rate (from /metrics endpoint, before/after each strategy)
- Task accuracy (truncate may degrade for long chains; stable and timestamp_s should be similar)
- Input token count per turn
