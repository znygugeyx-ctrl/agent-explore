# Experiment 012: Mask vs Remove v2 — Results

Generated from 8 result files

## Model: Claude-Haiku-4.5

| Strategy | Runs | Accuracy | Cost/Task | Input Tokens | Cache Read Rate | TTFT |
|----------|------|----------|-----------|--------------|-----------------|------|
| all             |    1 | 95.0% | $0.01050 | 11993 | 0.0% | 0ms |
| remove_dynamic  |    1 | 100.0% | $0.00307 | 2672 | 0.0% | 0ms |
| mask_desc       |    1 | 95.0% | $0.01142 | 13148 | 0.0% | 0ms |

## Model: Qwen3-8B

| Strategy | Runs | Accuracy | Cost/Task | Input Tokens | Cache Read Rate | TTFT |
|----------|------|----------|-----------|--------------|-----------------|------|
| all             |    1 | 95.0% | $0.00000 | 10711 | 0.0% | 693ms |
| remove_static   |    1 | 100.0% | $0.00000 | 1708 | 0.0% | 600ms |
| remove_dynamic  |    1 | 100.0% | $0.00000 | 1069 | 0.0% | 587ms |
| mask_desc       |    1 | 95.0% | $0.00000 | 11722 | 0.0% | 663ms |
| mask_logit      |    1 | 83.3% | $0.00000 | 10896 | 0.0% | 620ms |

### TTFT by Turn

| Strategy | Turn 0 | Turn 1 | Turn 2 | Turn 3 |
|----------|--------|--------|--------|--------|
| all      | 963ms | 595ms | 560ms | 592ms |
| remove_static | 657ms | 549ms | 576ms | 646ms |
| remove_dynamic | 621ms | 549ms | 576ms | 629ms |
| mask_desc | 811ms | 606ms | 575ms | 657ms |
| mask_logit | 644ms | 574ms | 627ms | 661ms |

## Key Findings

### H1: Cache Economics (Claude)
- TODO: compare all vs remove_dynamic cost/task on claude_haiku

### H2: Dynamic Tool Change Effect
- TODO: compare TTFT by turn: mask_logit vs remove_dynamic on vLLM

### H3: Model Confusion
- TODO: compare accuracy: all vs remove_dynamic

### H4: Model Scale
- TODO: compare 8B vs 14B across strategies