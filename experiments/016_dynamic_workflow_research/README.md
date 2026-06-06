# 016 — Dynamic Workflow Research (Cross-Model)

Same research question + same `deep-research` workflow script, run under two driver
models. Captures full artifacts per model to compare how the orchestrating model
shapes a multi-agent deep-research run.

> Meta note: the topic researched is Claude Code's **dynamic workflows** feature —
> and the reports here were produced *by* that feature.

## Layout

```
016_dynamic_workflow_research/
  README.md          # this file
  hypothesis.md      # what/why + cross-model comparison table
  .gitignore         # excludes */raw_traces/
  opus_4.8/
    deep-research.js # workflow script (byte-identical across both models)
    report.md        # final synthesized report
    findings.json    # structured verified findings + refuted + open questions
    run_id.txt       # run id + stats
    raw_traces/      # 205 per-agent jsonl (gitignored, local only)
  opus_4.7/
    deep-research.js # same script
    report.md        # final synthesized report
    run_id.txt       # run id + stats
    raw_traces/      # 209 per-agent jsonl (gitignored, local only)
```

## Runs

| | Opus 4.8 | Opus 4.7 |
|---|---|---|
| run_id | `wf_c176b43e-bd5` | `wf_f887e51a-9f8` |
| date | 2026-05-31 | 2026-05-31 |
| sources fetched | 19 | 21 |
| claims extracted | 92 | 102 |
| claims verified | 25 | 25 |
| claims killed | 2 | 0 |
| findings.json | ✅ | ❌ (output cleaned up before archival) |

## Key qualitative difference

- **4.8** was more skeptical — killed 2 claims in adversarial verification (the
  building-effective-agents workflow/agent dichotomy as the framing basis; a
  changelog over-claim). Its report emphasizes that Anthropic does **not** publish
  the low-level control-flow primitive internals.
- **4.7** confirmed all 25 claims (0 kills) and dug deeper into implementation
  internals: lifecycle hooks, `SubagentStart/Stop`, `additionalContext` injection,
  resume semantics, and named the `agent()/parallel()/pipeline()/phase()` script API
  (flagging that those names aren't in the public docs).

The two reports are complementary. Read both `report.md` files together.

## Reproducing

The workflow is invoked from within Claude Code:

```
Workflow({ name: "deep-research", args: "<the question, see hypothesis.md>" })
```

`deep-research.js` is the exact script that ran. `raw_traces/` (gitignored) holds
every subagent's full jsonl transcript for offline analysis.
