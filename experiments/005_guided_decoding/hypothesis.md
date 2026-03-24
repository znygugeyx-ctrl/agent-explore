# Experiment 005: Guided Decoding — Structural Guarantee vs Semantic Quality

## Background

Prior experiments (001–004) focused on tool gating and KV cache engineering.
This experiment shifts to a different form of constraint: **output structure enforcement
via vLLM guided decoding** (`response_format: json_schema`).

The motivating question from `paper/logit-mask-experiment.md` (Layer 1 / H1 / H7):

> Does constraining output structure improve reliability without degrading semantic quality?
> Or does it produce "valid but wrong" outputs?

### Key technical finding from exploratory probes

vLLM 0.18.0 supports `response_format: {type: "json_schema", json_schema: {...}}`.
Internally, xgrammar compiles the schema into a CFG and applies a **hard token mask**
at every decode step — all tokens not matching the current grammar state get logit → -∞.

Critical side effect: `<think>` blocks are impossible under guided decoding (the `<`
character is not valid JSON). This suppresses Qwen3-8B's chain-of-thought reasoning.

To isolate the effect of structure enforcement from the thinking suppression, all
conditions use `/no_think` in the user message.

## Hypotheses

**H1 (structural guarantee):**
`guided` achieves 100% JSON parse success and schema validity across all groups.
`free` and `prompt` will have measurable failure rates, especially on complex/ambiguous tasks.

**H2 (semantic parity on clear cases):**
On Group A (unambiguous info), `guided` and `prompt` achieve equivalent field accuracy.
Structural enforcement does not degrade quality when the answer is obvious.

**H3 (semantic degradation on ambiguous enums):**
On Group B1 (role ambiguity), `guided` makes more incorrect enum choices than `prompt`.
Without reasoning, the model defaults to high-frequency enum values rather than
mapping the text's intent to the best-fit option.

**H4 (boolean pressure):**
On Group B2 (availability ambiguity), `guided` forces a binary `true/false` where
`prompt` could express nuance (e.g. "passively looking" → both strategies pick `true`,
but `guided` may differ on genuinely ambiguous phrasings).

**H5 (hallucination on missing fields):**
On Group C (missing info), `guided` hallucinates plausible integers for missing `age`
(since `integer` is required and schema disallows null). `prompt` also hallucinates
but may be more conservative (e.g. output `0` or refuse to guess).

**H6 (latency — no meaningful difference):**
With `/no_think`, latency for `guided` and `prompt` are within 0.5s of each other.
The xgrammar mask computation overhead is negligible vs transformer forward pass.

## Design

### Schema (shared across all tasks)

```json
{
  "type": "object",
  "required": ["name", "age", "role", "location", "skills", "available"],
  "properties": {
    "name":      {"type": "string"},
    "age":       {"type": "integer"},
    "role":      {"type": "string", "enum": ["engineer", "designer", "manager", "analyst", "other"]},
    "location":  {"type": "string"},
    "skills":    {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    "available": {"type": "boolean"}
  }
}
```

### Conditions

| Strategy | schema in system prompt | `response_format: json_schema` | `/no_think` |
|----------|------------------------|-------------------------------|-------------|
| `free`   | ❌                      | ❌                             | ✅           |
| `prompt` | ✅                      | ❌                             | ✅           |
| `guided` | ❌                      | ✅                             | ✅           |

`free`: no schema, no constraint — establishes baseline failure rate.
`prompt` vs `guided`: the core comparison. Same task, same no-think budget.

### Task Groups (30 tasks total)

| Group | n  | What varies                  | Primary metric          |
|-------|----|------------------------------|-------------------------|
| A     | 10 | Nothing — all info clear     | Exact match all fields  |
| B1    | 4  | Role title not in enum       | `role` field accuracy   |
| B2    | 4  | Availability phrasing vague  | `available` accuracy    |
| B3    | 4  | Age given approximately      | `age` field accuracy    |
| C1    | 4  | Age not mentioned at all     | Hallucination rate (age)|
| C2    | 4  | Availability not mentioned   | Hallucination rate (available)|

### Primary Metrics

- **parse_success**: response is valid JSON (0/1 per task)
- **schema_valid**: all required fields present with correct types and enum values (0/1)
- **field_accuracy**: per-field exact match or LLM judge (Group A: exact; Group B/C: LLM judge)
- **hallucination_rate**: Group C — did the model invent a value for a field with no source?
- **latency_s**: wall-clock time per call

### Verifier Strategy

- Group A: exact match on all 6 fields (ground truth is unambiguous)
- Group B: LLM judge per-field: "Given the source text and the extracted value, is this
  a reasonable extraction? Answer yes/no."
- Group C: for missing fields, LLM judge: "The source text does not mention X.
  Did the model hallucinate a specific value, or handle the gap appropriately?"

## Predictions

If H1–H6 all hold:
- `free`: ~50-70% parse success (no schema → freeform text output)
- `prompt`: ~85-95% parse success, ~85% field accuracy on Group B
- `guided`: 100% parse success, ~95% field accuracy on Group A, ~70-80% on Group B
- Group C: both `prompt` and `guided` hallucinate age ~80% of the time (integer required)
- Latency: all three within 0.5s of each other with `/no_think`

The most informative outcome would be **Group B showing `prompt` > `guided` on semantic
accuracy**, confirming H3 and supporting H7 from the paper:
"Strong constraints are reliability enhancers, not capability enhancers."

## Limitations

1. Single model (Qwen3-8B) — results may not generalize to stronger models
2. Single schema — different schema shapes may produce different patterns
3. `/no_think` mode may not fully eliminate reasoning; short think blocks still appear
4. LLM judge for Group B/C introduces its own error rate
5. 30 tasks × 3 runs = 90 data points per strategy — modest statistical power
