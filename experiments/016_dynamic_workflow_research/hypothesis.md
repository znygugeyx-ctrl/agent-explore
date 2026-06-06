# 016 — Dynamic Workflow Research: Cross-Model Comparison

## What we're testing

The same research question, the same `deep-research` dynamic-workflow script, run
under two different driver models (Claude Opus 4.8 vs Opus 4.7). We capture both
runs' full artifacts to compare how the orchestrating model affects the output of
a multi-agent deep-research workflow.

**Research question driven through the workflow:**

> 调研 Claude Code 最新的 dynamic workflow（动态工作流）功能：它是什么、能做什么、
> 如何使用、以及底层实现原理。重点关注 Anthropic 官方文档、博客、release notes，
> 以及该功能如何让 Claude 编排多个 subagent / 确定性控制流（loops、conditionals、fan-out）。

## Why

The `deep-research` workflow fans out web searches, fetches sources, runs 3-vote
adversarial verification per claim, and synthesizes a cited report. Holding the
script and the question fixed isolates the **driver model** as the variable:
how it decomposes the question into search angles, how aggressively its adversarial
verifiers kill claims, and how it synthesizes the final report.

This is also a real-world artifact of the very feature being researched — the
report's subject (dynamic workflows) was produced *by* a dynamic workflow.

## Setup

- **Workflow script:** `deep-research.js` (byte-identical across both runs)
- **Variable:** driver model — `opus_4.8/` vs `opus_4.7/`
- **Fixed:** question, script, verification harness (3-vote, 2/3 to refute)

## Observations to compare

| Dimension | Opus 4.8 | Opus 4.7 |
|---|---|---|
| Search angles | 6 | (see report) |
| Sources fetched | 19 | 21 |
| Claims extracted | 92 | 102 |
| Claims verified (3-vote) | 25 | 25 |
| Claims killed | 2 | 0 |
| Final findings | 13 | (report sections) |
| Agent calls | 102 | ~102 |

Notable qualitative difference: **4.8 killed 2 claims** (the building-effective-agents
workflow/agent dichotomy, and a changelog over-claim), while **4.7 confirmed all 25
with 0 kills** — and 4.7 went further on implementation internals (hooks,
`SubagentStart/Stop`, `additionalContext`, resume semantics, the `agent()/parallel()/
pipeline()/phase()` script API). The two reports are complementary rather than
contradictory.

## Caveat / asymmetry

The 4.7 run's structured findings JSON was not preserved (its /tmp task-output was
cleaned up before archival), so `opus_4.7/` has `report.md` but no `findings.json`.
The 4.8 run has both. See each model's `run_id.txt`.
