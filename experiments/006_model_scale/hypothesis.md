# Experiment 006: Guided Decoding × Model Scale

## Background

Experiment 005 tested guided decoding (xgrammar via vLLM `response_format: json_schema`) vs
prompt-only vs free generation on Qwen3-8B. Key finding: guided decoding **hurts** semantic
accuracy on enum fields — B1 role accuracy was 0% (guided) vs 75% (prompt).

But Qwen3-8B has strong instruction-following ability. The interesting question is:

> For smaller models where prompt-only JSON compliance is unreliable, does guided decoding's
> structural guarantee outweigh its enum bias penalty?

This is a direct test of paper hypothesis H2: "the reliability benefit of strong constraints
reverses in the presence of weak instruction-following ability."

## Hypotheses

### H1: Smaller models have lower prompt parse success rates
Qwen3-0.6B and 1.7B will fail to produce valid JSON with prompt-only strategy more often
than 8B. Guided decoding will maintain 100% parse success across all sizes.

**Prediction**: prompt parse rate: 0.6B < 1.7B < 4B < 8B (100%)

### H2: Guided decoding benefit (vs prompt) is larger for smaller models
For very small models, guided decoding's parse success guarantee provides enough lift to
offset its semantic penalty. The net "guided benefit" (guided accuracy - prompt accuracy)
should be highest (least negative or positive) for 0.6B.

**Prediction**: guided_benefit_B1_role: 0.6B > 1.7B > 4B > 8B (where 8B = -75pp)

### H3: Enum bias is model-size-independent
The xgrammar enum bias (tendency toward high-frequency tokens like `designer`) is a
property of the token distribution, not model reasoning capacity. All models will show
similar enum bias under guided decoding on ambiguous fields.

**Falsifiable**: If 0.6B guided > 0.6B prompt on B1 role despite ambiguity, H3 is false.

### H4: Hallucination rates under guided decoding are constant across model sizes
For required fields with missing information (Group C), both prompt and guided will
hallucinate at near-100% regardless of model size, because the schema forces non-null values.

## Design

### Models
| Model       | Params | Status       |
|-------------|--------|--------------|
| Qwen3-0.6B  | 0.6B   | needs download |
| Qwen3-1.7B  | 1.7B   | needs download |
| Qwen3-4B    | 4B     | needs download |
| Qwen3-8B    | 8B     | reused from 005 |

### Tasks
Identical to Experiment 005: 30 tasks × 3 strategies × 3 runs = 270 LLM calls per model.
Task groups: A (clear), B1 (role ambiguity), B2 (available ambiguity), B3 (age ambiguity),
C1 (missing age), C2 (missing available).

### Strategies
- **free**: no schema constraint (establishes baseline failure rate per model)
- **prompt**: schema in system prompt, no guided decoding
- **guided**: `response_format: json_schema` with xgrammar enforcement

### Key Metric
`guided_benefit = guided_field_accuracy - prompt_field_accuracy`

Positive = guided helps; Negative = guided hurts.
Computed per field, per subgroup, per model.

## Predictions vs Actuals

| Model | prompt parse (pred) | prompt parse (actual) | guided_benefit B1 role (pred) | guided_benefit B1 role (actual) |
|-------|--------------------|-----------------------|-------------------------------|----------------------------------|
| 0.6B  | ~30-60%             | **0%**                | possibly positive              | N/A (no baseline)                |
| 1.7B  | ~70-85%             | **100%**              | near zero                      | **-50pp**                        |
| 4B    | ~90-95%             | **100%**              | slightly negative              | **-50pp**                        |
| 8B    | 100%                | 100%                  | -75pp                          | -75pp ✓                          |
| 14B   | (not predicted)     | 100%                  | (not predicted)                | **-25pp** (best result)          |

Key surprises: 0.6B had 0% prompt parse (not even ~30%), and 14B showed the least enum bias of all models.

## Limitations

1. Single schema design — enum fields may not generalize
2. /no_think may not work uniformly across model sizes (0.6B may not support it)
3. xgrammar enum bias analysis is inferred — direct logit inspection not available
4. 3 runs × 30 tasks gives modest statistical power; effect sizes must be large to be reliable
