# Experiment 010: Qwen3-30B-A3B-Thinking-2507 (base) vs MiroThinker-1.7-mini (fine-tuned)

## Background

Experiment 008 tested MiroThinker-1.7-mini (38.9% on 9 GAIA tasks, 256K context).
MiroThinker is a fine-tune of **Qwen/Qwen3-30B-A3B-Thinking-2507**.

This experiment runs the exact base model with the same tools and tasks, to isolate how much
the search-specific fine-tuning actually contributes.

## Research Question

**Does MiroThinker's fine-tuning improve GAIA search accuracy over its own base model
(Qwen3-30B-A3B-Thinking-2507)?**

If base ≈ fine-tuned: fine-tuning adds little value over a capable thinking MoE model.
If base << fine-tuned: fine-tuning genuinely teaches better search behavior.

## Model

**Qwen3-30B-A3B-Thinking-2507**
- Architecture: MoE, 30B total params, **3B active params** per token
- Base model that MiroThinker-1.7-mini was fine-tuned from
- Tool calling: standard JSON (hermes parser) — unlike MiroThinker's XML/MCP format
- Context window: 131072 (128K)

## Design

| Axis | Qwen3-30B-A3B-Thinking (this) | MiroThinker-1.7-mini (008) |
|------|-------------------------------|---------------------------|
| Model | Base (no search fine-tune) | Fine-tuned for search |
| Architecture | Same MoE 30B/3B active | Same (based on this) |
| Tool calling | JSON (hermes) | XML/MCP (custom) |
| Context | 131072 | 262144 |
| Framework | core.agent | custom loop |
| Thinking | /no_think (disabled) | enabled (competing tokens) |

Note: /no_think is used to give this model a fair chance — without it, 3B-active MoE
thinking traces can consume the token budget similar to MiroThinker's issue.

## Hypotheses

**H1**: Qwen3-30B-A3B-Thinking base ≥ MiroThinker accuracy (38.9%), because:
- Standard JSON tool calling is more reliable than custom XML
- /no_think avoids token budget competition
- Base Qwen3 instruction following is strong

**H2**: MiroThinker > base model, showing fine-tuning genuinely helps search tasks.

## Tasks

Same 9 GAIA tasks as 007/008.
