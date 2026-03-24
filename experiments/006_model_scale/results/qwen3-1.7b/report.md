# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-24 12:36:15

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        |  2.16s   |            229 |
| prompt | 90/90 (100%)   | 90/90 (100%)     |  1.16s   |             54 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  1.22s   |             59 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 21/30 (70%)   | 24/30 (80%)   |
| guided | 30/30 (100%)   | 30/30 (100%)   | 27/30 (90%)   | 30/30 (100%)   | 21/30 (70%)   | 18/30 (60%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | 9/12 (75%)   |
| guided | 3/12 (25%)   |

### B2 available 歧义（LLM judge）

| 策略   | available  |
|--------|------------|
| free   | N/A        |
| prompt | 12/12 (100%)   |
| guided | 9/12 (75%)   |

### B3 age 近似（范围匹配）

| 策略   | age        |
|--------|------------|
| free   | N/A        |
| prompt | 12/12 (100%)   |
| guided | 12/12 (100%)   |

## H5：缺失信息处理（Group C 幻觉率）

| 策略   | 子组             | 缺失字段    | 幻觉次数 / 总次数 |
|--------|------------------|------------|-------------------|
| free   | missing_age      | age        | N/A               |
| prompt | missing_age      | age        | 3/12（25% 幻觉）    |
| guided | missing_age      | age        | 9/12（75% 幻觉）    |
| free   | missing_available | available  | N/A               |
| prompt | missing_available | available  | 0/12（0% 幻觉）    |
| guided | missing_available | available  | 0/12（0% 幻觉）    |

## H6：延迟对比（/no_think 模式）

| 策略   | 平均延迟 | 最小延迟 | 最大延迟 |
|--------|----------|----------|----------|
| free   |  2.16s   |  0.99s   |  4.05s   |
| prompt |  1.16s   |  0.87s   |  1.32s   |
| guided |  1.22s   |  1.04s   |  1.65s   |

## 假设验证小结

| 假设 | 内容                                     | 验证结果 |
|------|------------------------------------------|----------|
| H1   | guided 100% 结构合法                     | 待确认   |
| H2   | Group A 三策略语义准确率相当              | 待确认   |
| H3   | Group B1 guided role 准确率低于 prompt   | 待确认   |
| H4   | Group B2 available 策略间差异            | 待确认   |
| H5   | Group C guided 幻觉率高于 prompt         | 待确认   |
| H6   | /no_think 后三策略延迟无明显差异          | 待确认   |

## 各任务详情（所有策略，第 1 轮）

| 任务 ID | 子组              | 策略   | 解析 | Schema | 延迟  |
|---------|-------------------|--------|------|--------|-------|
| A01     | clear             | free   | ✗    | ✗      | 3.14s |
| A02     | clear             | free   | ✗    | ✗      | 1.52s |
| A03     | clear             | free   | ✗    | ✗      | 1.34s |
| A04     | clear             | free   | ✗    | ✗      | 1.27s |
| A05     | clear             | free   | ✗    | ✗      | 1.82s |
| A06     | clear             | free   | ✗    | ✗      | 1.06s |
| A07     | clear             | free   | ✗    | ✗      | 3.85s |
| A08     | clear             | free   | ✗    | ✗      | 1.69s |
| A09     | clear             | free   | ✗    | ✗      | 3.01s |
| A10     | clear             | free   | ✗    | ✗      | 2.73s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 3.93s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 1.45s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 1.93s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 1.44s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 3.33s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 1.34s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 1.35s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 1.93s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 1.31s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 1.55s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 1.20s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 3.58s |
| C101    | missing_age       | free   | ✗    | ✗      | 2.57s |
| C102    | missing_age       | free   | ✗    | ✗      | 1.33s |
| C103    | missing_age       | free   | ✗    | ✗      | 1.35s |
| C104    | missing_age       | free   | ✗    | ✗      | 3.86s |
| C201    | missing_available | free   | ✗    | ✗      | 2.37s |
| C202    | missing_available | free   | ✗    | ✗      | 2.36s |
| C203    | missing_available | free   | ✗    | ✗      | 1.24s |
| C204    | missing_available | free   | ✗    | ✗      | 1.64s |
| A01     | clear             | prompt | ✓    | ✓      | 1.07s |
| A02     | clear             | prompt | ✓    | ✓      | 1.07s |
| A03     | clear             | prompt | ✓    | ✓      | 1.05s |
| A04     | clear             | prompt | ✓    | ✓      | 1.28s |
| A05     | clear             | prompt | ✓    | ✓      | 1.06s |
| A06     | clear             | prompt | ✓    | ✓      | 1.27s |
| A07     | clear             | prompt | ✓    | ✓      | 1.03s |
| A08     | clear             | prompt | ✓    | ✓      | 1.06s |
| A09     | clear             | prompt | ✓    | ✓      | 1.10s |
| A10     | clear             | prompt | ✓    | ✓      | 1.32s |
| B101    | role_ambiguity    | prompt | ✓    | ✓      | 1.13s |
| B102    | role_ambiguity    | prompt | ✓    | ✓      | 1.32s |
| B103    | role_ambiguity    | prompt | ✓    | ✓      | 0.95s |
| B104    | role_ambiguity    | prompt | ✓    | ✓      | 1.20s |
| B201    | available_ambiguity | prompt | ✓    | ✓      | 1.01s |
| B202    | available_ambiguity | prompt | ✓    | ✓      | 1.20s |
| B203    | available_ambiguity | prompt | ✓    | ✓      | 0.97s |
| B204    | available_ambiguity | prompt | ✓    | ✓      | 1.20s |
| B301    | age_ambiguity     | prompt | ✓    | ✓      | 1.21s |
| B302    | age_ambiguity     | prompt | ✓    | ✓      | 0.98s |
| B303    | age_ambiguity     | prompt | ✓    | ✓      | 1.20s |
| B304    | age_ambiguity     | prompt | ✓    | ✓      | 0.96s |
| C101    | missing_age       | prompt | ✓    | ✓      | 1.14s |
| C102    | missing_age       | prompt | ✓    | ✓      | 1.22s |
| C103    | missing_age       | prompt | ✓    | ✓      | 1.22s |
| C104    | missing_age       | prompt | ✓    | ✓      | 1.22s |
| C201    | missing_available | prompt | ✓    | ✓      | 1.22s |
| C202    | missing_available | prompt | ✓    | ✓      | 1.21s |
| C203    | missing_available | prompt | ✓    | ✓      | 0.87s |
| C204    | missing_available | prompt | ✓    | ✓      | 1.20s |
| A01     | clear             | guided | ✓    | ✓      | 1.43s |
| A02     | clear             | guided | ✓    | ✓      | 1.42s |
| A03     | clear             | guided | ✓    | ✓      | 1.41s |
| A04     | clear             | guided | ✓    | ✓      | 1.65s |
| A05     | clear             | guided | ✓    | ✓      | 1.08s |
| A06     | clear             | guided | ✓    | ✓      | 1.30s |
| A07     | clear             | guided | ✓    | ✓      | 1.08s |
| A08     | clear             | guided | ✓    | ✓      | 1.33s |
| A09     | clear             | guided | ✓    | ✓      | 1.13s |
| A10     | clear             | guided | ✓    | ✓      | 1.21s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 1.23s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 1.22s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 1.07s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 1.21s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 1.21s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 1.21s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 1.22s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 1.26s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 1.29s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 1.29s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 1.25s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 1.26s |
| C101    | missing_age       | guided | ✓    | ✓      | 1.28s |
| C102    | missing_age       | guided | ✓    | ✓      | 1.28s |
| C103    | missing_age       | guided | ✓    | ✓      | 1.24s |
| C104    | missing_age       | guided | ✓    | ✓      | 1.18s |
| C201    | missing_available | guided | ✓    | ✓      | 1.22s |
| C202    | missing_available | guided | ✓    | ✓      | 1.22s |
| C203    | missing_available | guided | ✓    | ✓      | 1.22s |
| C204    | missing_available | guided | ✓    | ✓      | 1.21s |