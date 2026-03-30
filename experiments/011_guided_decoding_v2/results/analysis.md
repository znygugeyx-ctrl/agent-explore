# 实验 011：Guided Decoding — 任务复杂度 × Enum 规模 — 分析报告

**生成时间**：2026-03-29 22:39:53

**模型**：Qwen3-0.6B, Qwen3-1.7B, Qwen3-14B, Qwen3-32B, Qwen3-4B, Qwen3-8B

---

## Track 1: GSM8K — 推理 × 约束

### 总体结果

| 模型 | 条件 | 准确率 | Parse率 | 平均延迟 | 平均输出token |
|------|------|--------|---------|----------|--------------|
| Qwen3-0.6B | guided_nothink | 1.0% (1/100) | 100.0% | 0.63s | 11 |
| Qwen3-0.6B | prompt_nothink | 3.0% (3/100) | 100.0% | 0.72s | 17 |
| Qwen3-0.6B | prompt_think | 66.0% (66/100) | 93.0% | 4.17s | 787 |
| Qwen3-1.7B | guided_nothink | 9.0% (9/100) | 100.0% | 0.77s | 11 |
| Qwen3-1.7B | prompt_nothink | 63.0% (63/100) | 100.0% | 1.73s | 182 |
| Qwen3-1.7B | prompt_think | 88.0% (88/100) | 100.0% | 8.89s | 1026 |
| Qwen3-14B | guided_nothink | 27.0% (27/100) | 100.0% | 1.00s | 11 |
| Qwen3-14B | prompt_nothink | 30.0% (30/100) | 100.0% | 1.73s | 25 |
| Qwen3-14B | prompt_think | 95.0% (95/100) | 100.0% | 11.42s | 666 |
| Qwen3-32B | guided_nothink | 34.0% (34/100) | 100.0% | 1.19s | 8 |
| Qwen3-32B | prompt_nothink | 38.0% (38/100) | 100.0% | 1.44s | 16 |
| Qwen3-32B | prompt_think | 95.0% (95/100) | 100.0% | 17.03s | 538 |
| Qwen3-4B | guided_nothink | 17.0% (17/100) | 100.0% | 0.82s | 12 |
| Qwen3-4B | prompt_nothink | 27.0% (27/100) | 100.0% | 1.37s | 55 |
| Qwen3-4B | prompt_think | 92.0% (92/100) | 98.0% | 10.52s | 737 |
| Qwen3-8B | guided_nothink | 27.0% (27/100) | 98.0% | 0.93s | 10 |
| Qwen3-8B | prompt_nothink | 29.0% (29/100) | 100.0% | 1.01s | 15 |
| Qwen3-8B | prompt_think | 92.0% (92/100) | 95.0% | 16.86s | 682 |

### 按难度分级

| 模型 | 条件 | Easy | Medium | Hard |
|------|------|------|--------|------|
| Qwen3-0.6B | guided_nothink | 2.9% (1/35) | 0.0% (0/35) | 0.0% (0/30) |
| Qwen3-0.6B | prompt_nothink | 2.9% (1/35) | 2.9% (1/35) | 3.3% (1/30) |
| Qwen3-0.6B | prompt_think | 80.0% (28/35) | 71.4% (25/35) | 43.3% (13/30) |
| Qwen3-1.7B | guided_nothink | 20.0% (7/35) | 5.7% (2/35) | 0.0% (0/30) |
| Qwen3-1.7B | prompt_nothink | 71.4% (25/35) | 60.0% (21/35) | 56.7% (17/30) |
| Qwen3-1.7B | prompt_think | 91.4% (32/35) | 94.3% (33/35) | 76.7% (23/30) |
| Qwen3-14B | guided_nothink | 48.6% (17/35) | 25.7% (9/35) | 3.3% (1/30) |
| Qwen3-14B | prompt_nothink | 51.4% (18/35) | 28.6% (10/35) | 6.7% (2/30) |
| Qwen3-14B | prompt_think | 97.1% (34/35) | 97.1% (34/35) | 90.0% (27/30) |
| Qwen3-32B | guided_nothink | 48.6% (17/35) | 37.1% (13/35) | 13.3% (4/30) |
| Qwen3-32B | prompt_nothink | 51.4% (18/35) | 37.1% (13/35) | 23.3% (7/30) |
| Qwen3-32B | prompt_think | 94.3% (33/35) | 97.1% (34/35) | 93.3% (28/30) |
| Qwen3-4B | guided_nothink | 28.6% (10/35) | 8.6% (3/35) | 13.3% (4/30) |
| Qwen3-4B | prompt_nothink | 42.9% (15/35) | 17.1% (6/35) | 20.0% (6/30) |
| Qwen3-4B | prompt_think | 91.4% (32/35) | 100.0% (35/35) | 83.3% (25/30) |
| Qwen3-8B | guided_nothink | 42.9% (15/35) | 28.6% (10/35) | 6.7% (2/30) |
| Qwen3-8B | prompt_nothink | 40.0% (14/35) | 28.6% (10/35) | 16.7% (5/30) |
| Qwen3-8B | prompt_think | 91.4% (32/35) | 100.0% (35/35) | 83.3% (25/30) |

### 关键对比

- **Qwen3-0.6B** thinking 价值: +63.0pp (prompt_think 66.0% vs prompt_nothink 3.0%)
- **Qwen3-0.6B** guided 代价: -2.0pp (guided_nothink 1.0% vs prompt_nothink 3.0%)
- **Qwen3-1.7B** thinking 价值: +25.0pp (prompt_think 88.0% vs prompt_nothink 63.0%)
- **Qwen3-1.7B** guided 代价: -54.0pp (guided_nothink 9.0% vs prompt_nothink 63.0%)
- **Qwen3-14B** thinking 价值: +65.0pp (prompt_think 95.0% vs prompt_nothink 30.0%)
- **Qwen3-14B** guided 代价: -3.0pp (guided_nothink 27.0% vs prompt_nothink 30.0%)
- **Qwen3-32B** thinking 价值: +57.0pp (prompt_think 95.0% vs prompt_nothink 38.0%)
- **Qwen3-32B** guided 代价: -4.0pp (guided_nothink 34.0% vs prompt_nothink 38.0%)
- **Qwen3-4B** thinking 价值: +65.0pp (prompt_think 92.0% vs prompt_nothink 27.0%)
- **Qwen3-4B** guided 代价: -10.0pp (guided_nothink 17.0% vs prompt_nothink 27.0%)
- **Qwen3-8B** thinking 价值: +63.0pp (prompt_think 92.0% vs prompt_nothink 29.0%)
- **Qwen3-8B** guided 代价: -2.0pp (guided_nothink 27.0% vs prompt_nothink 29.0%)

## Track 2: 分类 — Enum 规模 × 约束

### BANKING77 (77类意图) (77 enum)

| 模型 | 条件 | 准确率 | Parse率 | 平均延迟 |
|------|------|--------|---------|----------|
| Qwen3-0.6B | guided_nothink | 41.0% (41/100) | 100.0% | 0.71s |
| Qwen3-0.6B | prompt_nothink | 33.0% (33/100) | 100.0% | 0.63s |
| Qwen3-0.6B | prompt_think | 45.0% (45/100) | 100.0% | 1.23s |
| Qwen3-1.7B | guided_nothink | 38.0% (38/100) | 69.0% | 0.76s |
| Qwen3-1.7B | prompt_nothink | 61.0% (61/100) | 100.0% | 0.76s |
| Qwen3-1.7B | prompt_think | 63.0% (63/100) | 99.0% | 2.44s |
| Qwen3-14B | guided_nothink | 80.0% (80/100) | 100.0% | 1.19s |
| Qwen3-14B | prompt_nothink | 79.0% (79/100) | 100.0% | 1.28s |
| Qwen3-14B | prompt_think | 78.0% (78/100) | 100.0% | 8.92s |
| Qwen3-32B | guided_nothink | 77.0% (77/100) | 100.0% | 1.17s |
| Qwen3-32B | prompt_nothink | 77.0% (77/100) | 100.0% | 1.36s |
| Qwen3-32B | prompt_think | 81.0% (81/100) | 100.0% | 6.60s |
| Qwen3-4B | guided_nothink | 73.0% (73/100) | 100.0% | 0.84s |
| Qwen3-4B | prompt_nothink | 72.0% (72/100) | 100.0% | 0.98s |
| Qwen3-4B | prompt_think | 71.0% (71/100) | 100.0% | 3.37s |
| Qwen3-8B | guided_nothink | 73.0% (73/100) | 100.0% | 1.15s |
| Qwen3-8B | prompt_nothink | 72.0% (72/100) | 100.0% | 0.95s |
| Qwen3-8B | prompt_think | 75.0% (75/100) | 100.0% | 7.19s |

**按难度分级**

| 模型 | 条件 | Easy | Medium | Hard |
|------|------|------|--------|------|
| Qwen3-0.6B | guided_nothink | 69.6% (16/23) | 38.0% (19/50) | 22.2% (6/27) |
| Qwen3-0.6B | prompt_nothink | 60.9% (14/23) | 30.0% (15/50) | 14.8% (4/27) |
| Qwen3-0.6B | prompt_think | 78.3% (18/23) | 44.0% (22/50) | 18.5% (5/27) |
| Qwen3-1.7B | guided_nothink | 78.3% (18/23) | 36.0% (18/50) | 7.4% (2/27) |
| Qwen3-1.7B | prompt_nothink | 91.3% (21/23) | 66.0% (33/50) | 25.9% (7/27) |
| Qwen3-1.7B | prompt_think | 95.7% (22/23) | 70.0% (35/50) | 22.2% (6/27) |
| Qwen3-14B | guided_nothink | 95.7% (22/23) | 86.0% (43/50) | 55.6% (15/27) |
| Qwen3-14B | prompt_nothink | 95.7% (22/23) | 86.0% (43/50) | 51.9% (14/27) |
| Qwen3-14B | prompt_think | 95.7% (22/23) | 84.0% (42/50) | 51.9% (14/27) |
| Qwen3-32B | guided_nothink | 95.7% (22/23) | 84.0% (42/50) | 48.1% (13/27) |
| Qwen3-32B | prompt_nothink | 95.7% (22/23) | 84.0% (42/50) | 48.1% (13/27) |
| Qwen3-32B | prompt_think | 100.0% (23/23) | 86.0% (43/50) | 55.6% (15/27) |
| Qwen3-4B | guided_nothink | 95.7% (22/23) | 72.0% (36/50) | 55.6% (15/27) |
| Qwen3-4B | prompt_nothink | 95.7% (22/23) | 74.0% (37/50) | 48.1% (13/27) |
| Qwen3-4B | prompt_think | 95.7% (22/23) | 74.0% (37/50) | 44.4% (12/27) |
| Qwen3-8B | guided_nothink | 95.7% (22/23) | 84.0% (42/50) | 33.3% (9/27) |
| Qwen3-8B | prompt_nothink | 95.7% (22/23) | 86.0% (43/50) | 25.9% (7/27) |
| Qwen3-8B | prompt_think | 95.7% (22/23) | 86.0% (43/50) | 37.0% (10/27) |

## Track 3: Few-NERD NER — 复杂结构 × 约束

### 总体结果

| 模型 | 条件 | Entity F1 | 准确率(F1≥0.8) | 结构有效率 | Parse率 | 平均延迟 |
|------|------|-----------|---------------|-----------|---------|----------|
| Qwen3-0.6B | guided_nothink | 0.112 | 3.0% (3/100) | 100.0% | 100.0% | 1.00s |
| Qwen3-0.6B | prompt_nothink | 0.064 | 1.0% (1/100) | 78.0% | 100.0% | 0.73s |
| Qwen3-0.6B | prompt_think | 0.367 | 14.0% (14/100) | 81.0% | 100.0% | 2.18s |
| Qwen3-1.7B | guided_nothink | 0.444 | 17.0% (17/100) | 100.0% | 100.0% | 1.21s |
| Qwen3-1.7B | prompt_nothink | 0.428 | 19.0% (19/100) | 89.0% | 100.0% | 1.09s |
| Qwen3-1.7B | prompt_think | 0.477 | 18.0% (18/100) | 69.0% | 100.0% | 7.18s |
| Qwen3-14B | guided_nothink | 0.560 | 33.0% (33/100) | 100.0% | 100.0% | 1.79s |
| Qwen3-14B | prompt_nothink | 0.561 | 32.0% (32/100) | 100.0% | 100.0% | 1.53s |
| Qwen3-14B | prompt_think | 0.628 | 35.0% (35/100) | 100.0% | 100.0% | 9.92s |
| Qwen3-32B | guided_nothink | 0.582 | 33.0% (33/100) | 100.0% | 100.0% | 2.46s |
| Qwen3-32B | prompt_nothink | 0.566 | 33.0% (33/100) | 100.0% | 100.0% | 2.55s |
| Qwen3-32B | prompt_think | 0.584 | 35.0% (35/100) | 100.0% | 100.0% | 16.35s |
| Qwen3-4B | guided_nothink | 0.532 | 31.0% (31/100) | 100.0% | 100.0% | 1.70s |
| Qwen3-4B | prompt_nothink | 0.456 | 23.0% (23/100) | 100.0% | 100.0% | 1.33s |
| Qwen3-4B | prompt_think | 0.608 | 38.0% (38/100) | 100.0% | 100.0% | 13.73s |
| Qwen3-8B | guided_nothink | 0.569 | 34.0% (34/100) | 100.0% | 100.0% | 2.69s |
| Qwen3-8B | prompt_nothink | 0.558 | 33.0% (33/100) | 92.0% | 100.0% | 2.11s |
| Qwen3-8B | prompt_think | 0.623 | 33.0% (33/100) | 99.0% | 99.0% | 21.68s |

### 按难度分级

| 模型 | 条件 | Easy F1 | Medium F1 | Hard F1 |
|------|------|---------|-----------|---------|
| Qwen3-0.6B | guided_nothink | 0.077 | 0.096 | 0.173 |
| Qwen3-0.6B | prompt_nothink | 0.014 | 0.081 | 0.104 |
| Qwen3-0.6B | prompt_think | 0.333 | 0.340 | 0.436 |
| Qwen3-1.7B | guided_nothink | 0.486 | 0.402 | 0.444 |
| Qwen3-1.7B | prompt_nothink | 0.402 | 0.447 | 0.437 |
| Qwen3-1.7B | prompt_think | 0.411 | 0.465 | 0.567 |
| Qwen3-14B | guided_nothink | 0.506 | 0.603 | 0.572 |
| Qwen3-14B | prompt_nothink | 0.506 | 0.600 | 0.581 |
| Qwen3-14B | prompt_think | 0.625 | 0.641 | 0.615 |
| Qwen3-32B | guided_nothink | 0.519 | 0.621 | 0.610 |
| Qwen3-32B | prompt_nothink | 0.475 | 0.620 | 0.607 |
| Qwen3-32B | prompt_think | 0.542 | 0.584 | 0.633 |
| Qwen3-4B | guided_nothink | 0.470 | 0.549 | 0.585 |
| Qwen3-4B | prompt_nothink | 0.438 | 0.461 | 0.473 |
| Qwen3-4B | prompt_think | 0.598 | 0.592 | 0.639 |
| Qwen3-8B | guided_nothink | 0.487 | 0.609 | 0.617 |
| Qwen3-8B | prompt_nothink | 0.487 | 0.578 | 0.620 |
| Qwen3-8B | prompt_think | 0.590 | 0.619 | 0.669 |

## Track 4: Recipe — 嵌套多字段 × 约束

### 总体结果

| 模型 | 条件 | 准确率(≥0.7) | 结构有效率 | Parse率 | 平均延迟 | 平均输出token |
|------|------|-------------|-----------|---------|----------|--------------|
| Qwen3-0.6B | guided_nothink | 11.0% (11/100) | 100.0% | 100.0% | 1.47s | 304 |
| Qwen3-0.6B | prompt_nothink | 10.0% (10/100) | 64.0% | 64.0% | 2.39s | 310 |
| Qwen3-0.6B | prompt_think | 17.0% (17/100) | 81.0% | 81.0% | 4.38s | 768 |
| Qwen3-1.7B | guided_nothink | 22.0% (22/100) | 100.0% | 100.0% | 2.55s | 306 |
| Qwen3-1.7B | prompt_nothink | 13.0% (13/100) | 76.0% | 76.0% | 2.28s | 277 |
| Qwen3-1.7B | prompt_think | 19.0% (19/100) | 90.0% | 90.0% | 12.75s | 1740 |
| Qwen3-14B | guided_nothink | 28.0% (28/100) | 100.0% | 100.0% | 11.12s | 255 |
| Qwen3-14B | prompt_nothink | 26.0% (26/100) | 100.0% | 100.0% | 13.34s | 309 |
| Qwen3-14B | prompt_think | 17.0% (17/100) | 100.0% | 100.0% | 22.36s | 1425 |
| Qwen3-32B | guided_nothink | 21.0% (21/100) | 100.0% | 100.0% | 8.05s | 247 |
| Qwen3-32B | prompt_nothink | 19.0% (19/100) | 99.0% | 99.0% | 10.28s | 316 |
| Qwen3-32B | prompt_think | 13.0% (13/100) | 100.0% | 100.0% | 42.56s | 1229 |
| Qwen3-4B | guided_nothink | 22.0% (22/100) | 100.0% | 100.0% | 4.05s | 272 |
| Qwen3-4B | prompt_nothink | 22.0% (22/100) | 95.0% | 95.0% | 4.31s | 279 |
| Qwen3-4B | prompt_think | 18.0% (18/100) | 84.0% | 84.0% | 29.43s | 2075 |
| Qwen3-8B | guided_nothink | 19.0% (19/100) | 100.0% | 100.0% | 8.01s | 320 |
| Qwen3-8B | prompt_nothink | 17.0% (17/100) | 97.0% | 97.0% | 6.71s | 251 |
| Qwen3-8B | prompt_think | 16.0% (16/100) | 66.0% | 66.0% | 38.33s | 1568 |

### 按难度分级

| 模型 | 条件 | Easy | Medium | Hard |
|------|------|------|--------|------|
| Qwen3-0.6B | guided_nothink | 17.1% (6/35) | 14.3% (5/35) | 0.0% (0/30) |
| Qwen3-0.6B | prompt_nothink | 14.3% (5/35) | 8.6% (3/35) | 6.7% (2/30) |
| Qwen3-0.6B | prompt_think | 22.9% (8/35) | 20.0% (7/35) | 6.7% (2/30) |
| Qwen3-1.7B | guided_nothink | 20.0% (7/35) | 20.0% (7/35) | 26.7% (8/30) |
| Qwen3-1.7B | prompt_nothink | 20.0% (7/35) | 8.6% (3/35) | 10.0% (3/30) |
| Qwen3-1.7B | prompt_think | 17.1% (6/35) | 22.9% (8/35) | 16.7% (5/30) |
| Qwen3-14B | guided_nothink | 25.7% (9/35) | 28.6% (10/35) | 30.0% (9/30) |
| Qwen3-14B | prompt_nothink | 25.7% (9/35) | 25.7% (9/35) | 26.7% (8/30) |
| Qwen3-14B | prompt_think | 31.4% (11/35) | 8.6% (3/35) | 10.0% (3/30) |
| Qwen3-32B | guided_nothink | 22.9% (8/35) | 20.0% (7/35) | 20.0% (6/30) |
| Qwen3-32B | prompt_nothink | 20.0% (7/35) | 20.0% (7/35) | 16.7% (5/30) |
| Qwen3-32B | prompt_think | 17.1% (6/35) | 11.4% (4/35) | 10.0% (3/30) |
| Qwen3-4B | guided_nothink | 25.7% (9/35) | 20.0% (7/35) | 20.0% (6/30) |
| Qwen3-4B | prompt_nothink | 20.0% (7/35) | 25.7% (9/35) | 20.0% (6/30) |
| Qwen3-4B | prompt_think | 22.9% (8/35) | 14.3% (5/35) | 16.7% (5/30) |
| Qwen3-8B | guided_nothink | 22.9% (8/35) | 17.1% (6/35) | 16.7% (5/30) |
| Qwen3-8B | prompt_nothink | 17.1% (6/35) | 17.1% (6/35) | 16.7% (5/30) |
| Qwen3-8B | prompt_think | 25.7% (9/35) | 8.6% (3/35) | 13.3% (4/30) |

## 2×2 评估矩阵：Format × Content

每个单元格: Full Success / Semantic Failure / Format Failure / Total Failure

| 数据集 | Schema复杂度 | 条件 | 模型 | FullSuccess | SemanticFail | FormatFail | TotalFail | 结构有效率 |
|--------|-------------|------|------|-------------|-------------|------------|-----------|-----------|
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-0.6B | 1/100 | 99/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-0.6B | 3/100 | 92/100 | 0/100 | 5/100 | 95.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-0.6B | 66/100 | 27/100 | 0/100 | 7/100 | 93.0% |
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-1.7B | 9/100 | 91/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-1.7B | 24/100 | 25/100 | 39/100 | 12/100 | 49.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-1.7B | 88/100 | 12/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-14B | 27/100 | 73/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-14B | 28/100 | 69/100 | 2/100 | 1/100 | 97.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-14B | 95/100 | 5/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-32B | 34/100 | 66/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-32B | 38/100 | 61/100 | 0/100 | 1/100 | 99.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-32B | 95/100 | 5/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-4B | 17/100 | 83/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-4B | 14/100 | 68/100 | 13/100 | 5/100 | 82.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-4B | 92/100 | 6/100 | 0/100 | 2/100 | 98.0% |
| GSM8K (推理) | L1 单字段 | guided_nothink | Qwen3-8B | 27/100 | 71/100 | 0/100 | 2/100 | 98.0% |
| GSM8K (推理) | L1 单字段 | prompt_nothink | Qwen3-8B | 29/100 | 71/100 | 0/100 | 0/100 | 100.0% |
| GSM8K (推理) | L1 单字段 | prompt_think | Qwen3-8B | 92/100 | 3/100 | 0/100 | 5/100 | 95.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-0.6B | 41/100 | 59/100 | 0/100 | 0/100 | 100.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-0.6B | 32/100 | 58/100 | 1/100 | 9/100 | 90.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-0.6B | 45/100 | 47/100 | 0/100 | 8/100 | 92.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-1.7B | 38/100 | 31/100 | 0/100 | 31/100 | 69.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-1.7B | 61/100 | 34/100 | 0/100 | 5/100 | 95.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-1.7B | 63/100 | 31/100 | 0/100 | 6/100 | 94.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-14B | 80/100 | 20/100 | 0/100 | 0/100 | 100.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-14B | 79/100 | 16/100 | 0/100 | 5/100 | 95.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-14B | 78/100 | 17/100 | 0/100 | 5/100 | 95.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-32B | 77/100 | 23/100 | 0/100 | 0/100 | 100.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-32B | 75/100 | 19/100 | 2/100 | 4/100 | 94.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-32B | 81/100 | 15/100 | 0/100 | 4/100 | 96.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-4B | 73/100 | 27/100 | 0/100 | 0/100 | 100.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-4B | 72/100 | 22/100 | 0/100 | 6/100 | 94.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-4B | 71/100 | 25/100 | 0/100 | 4/100 | 96.0% |
| BANKING77 (77类意图) | L2 单enum | guided_nothink | Qwen3-8B | 73/100 | 27/100 | 0/100 | 0/100 | 100.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_nothink | Qwen3-8B | 72/100 | 24/100 | 0/100 | 4/100 | 96.0% |
| BANKING77 (77类意图) | L2 单enum | prompt_think | Qwen3-8B | 75/100 | 22/100 | 0/100 | 3/100 | 97.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-0.6B | 3/100 | 97/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-0.6B | 1/100 | 77/100 | 0/100 | 22/100 | 78.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-0.6B | 14/100 | 67/100 | 0/100 | 19/100 | 81.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-1.7B | 17/100 | 83/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-1.7B | 17/100 | 72/100 | 2/100 | 9/100 | 89.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-1.7B | 13/100 | 56/100 | 5/100 | 26/100 | 69.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-14B | 33/100 | 67/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-14B | 32/100 | 68/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-14B | 35/100 | 65/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-32B | 33/100 | 67/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-32B | 33/100 | 67/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-32B | 35/100 | 65/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-4B | 31/100 | 69/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-4B | 23/100 | 77/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-4B | 38/100 | 62/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | guided_nothink | Qwen3-8B | 34/100 | 66/100 | 0/100 | 0/100 | 100.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_nothink | Qwen3-8B | 31/100 | 61/100 | 2/100 | 6/100 | 92.0% |
| Few-NERD (NER 8类实体) | L3 对象数组+enum | prompt_think | Qwen3-8B | 33/100 | 66/100 | 0/100 | 1/100 | 99.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-0.6B | 11/100 | 89/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-0.6B | 10/100 | 54/100 | 0/100 | 36/100 | 64.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-0.6B | 17/100 | 64/100 | 0/100 | 19/100 | 81.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-1.7B | 22/100 | 78/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-1.7B | 13/100 | 63/100 | 0/100 | 24/100 | 76.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-1.7B | 19/100 | 71/100 | 0/100 | 10/100 | 90.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-14B | 28/100 | 72/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-14B | 26/100 | 74/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-14B | 17/100 | 83/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-32B | 21/100 | 79/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-32B | 19/100 | 80/100 | 0/100 | 1/100 | 99.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-32B | 13/100 | 87/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-4B | 22/100 | 78/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-4B | 22/100 | 73/100 | 0/100 | 5/100 | 95.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-4B | 18/100 | 66/100 | 0/100 | 16/100 | 84.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | guided_nothink | Qwen3-8B | 19/100 | 81/100 | 0/100 | 0/100 | 100.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_nothink | Qwen3-8B | 17/100 | 80/100 | 0/100 | 3/100 | 97.0% |
| Recipe (食谱解析) | L4 嵌套多字段 | prompt_think | Qwen3-8B | 16/100 | 50/100 | 0/100 | 34/100 | 66.0% |

### 结构复杂度 × Format Failure 对比

| Schema复杂度 | 数据集 | prompt结构有效率 | guided结构有效率 | prompt FormatFail率 |
|-------------|--------|-----------------|-----------------|-------------------|
| L1 单字段 | GSM8K (推理) | 87.0% | 99.7% | 9.0% |
| L2 单enum | BANKING77 (77类意图) | 94.0% | 94.8% | 0.5% |
| L3 对象数组+enum | Few-NERD (NER 8类实体) | 93.2% | 100.0% | 0.7% |
| L4 嵌套多字段 | Recipe (食谱解析) | 88.5% | 100.0% | 0.0% |

## 假设验证总结

| 假设 | 内容 | 验证结果 |
|------|------|----------|
| H1 | 简单 schema（GSM8K integer）guided 无语义退化 | 待分析 |
| H2 | thinking 显著提升推理准确率 | 待分析 |
| H3 | enum 惩罚随 enum 数量递增（5→28→77） | 待分析 |
| H4 | Hard 任务 guided 退化更严重 | 待分析 |
| H5 | 14B guided 惩罚 < 8B | 待分析 |
| H6 | 复杂 schema（NER 对象数组）prompt format failure 率显著高于简单 schema | 待分析 |
| H7 | NER 上 guided 的 format 保障收益大于语义代价（net positive） | 待分析 |
| H8 | format failure 中 >30% 任务答案本身正确（format_failure 类别） | 待分析 |

*注：以上待分析项需根据实际数据填写。运行 analyze.py 查看表格后手动更新。*
