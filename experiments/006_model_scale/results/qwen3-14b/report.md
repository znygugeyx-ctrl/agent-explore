# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-24 14:33:35

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        |  8.40s   |            185 |
| prompt | 90/90 (100%)   | 90/90 (100%)     |  3.14s   |             55 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  3.01s   |             52 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |
| guided | 30/30 (100%)   | 30/30 (100%)   | 27/30 (90%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | 12/12 (100%)   |
| guided | 9/12 (75%)   |

### B2 available 歧义（LLM judge）

| 策略   | available  |
|--------|------------|
| free   | N/A        |
| prompt | 6/12 (50%)   |
| guided | 6/12 (50%)   |

### B3 age 近似（范围匹配）

| 策略   | age        |
|--------|------------|
| free   | N/A        |
| prompt | 9/12 (75%)   |
| guided | 12/12 (100%)   |

## H5：缺失信息处理（Group C 幻觉率）

| 策略   | 子组             | 缺失字段    | 幻觉次数 / 总次数 |
|--------|------------------|------------|-------------------|
| free   | missing_age      | age        | N/A               |
| prompt | missing_age      | age        | 12/12（100% 幻觉）    |
| guided | missing_age      | age        | 12/12（100% 幻觉）    |
| free   | missing_available | available  | N/A               |
| prompt | missing_available | available  | 12/12（100% 幻觉）    |
| guided | missing_available | available  | 12/12（100% 幻觉）    |

## H6：延迟对比（/no_think 模式）

| 策略   | 平均延迟 | 最小延迟 | 最大延迟 |
|--------|----------|----------|----------|
| free   |  8.40s   |  2.46s   | 21.74s   |
| prompt |  3.14s   |  2.83s   |  3.72s   |
| guided |  3.01s   |  2.58s   |  3.82s   |

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
| A01     | clear             | free   | ✗    | ✗      | 7.84s |
| A02     | clear             | free   | ✗    | ✗      | 3.54s |
| A03     | clear             | free   | ✗    | ✗      | 16.02s |
| A04     | clear             | free   | ✗    | ✗      | 2.77s |
| A05     | clear             | free   | ✗    | ✗      | 6.56s |
| A06     | clear             | free   | ✗    | ✗      | 4.78s |
| A07     | clear             | free   | ✗    | ✗      | 12.11s |
| A08     | clear             | free   | ✗    | ✗      | 4.56s |
| A09     | clear             | free   | ✗    | ✗      | 9.03s |
| A10     | clear             | free   | ✗    | ✗      | 3.64s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 8.07s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 6.81s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 7.65s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 2.58s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 7.24s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 4.98s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 6.19s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 9.28s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 12.41s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 21.56s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 9.72s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 20.50s |
| C101    | missing_age       | free   | ✗    | ✗      | 6.16s |
| C102    | missing_age       | free   | ✗    | ✗      | 4.58s |
| C103    | missing_age       | free   | ✗    | ✗      | 12.40s |
| C104    | missing_age       | free   | ✗    | ✗      | 19.59s |
| C201    | missing_available | free   | ✗    | ✗      | 3.32s |
| C202    | missing_available | free   | ✗    | ✗      | 5.26s |
| C203    | missing_available | free   | ✗    | ✗      | 5.53s |
| C204    | missing_available | free   | ✗    | ✗      | 4.35s |
| A01     | clear             | prompt | ✓    | ✓      | 2.94s |
| A02     | clear             | prompt | ✓    | ✓      | 3.12s |
| A03     | clear             | prompt | ✓    | ✓      | 3.17s |
| A04     | clear             | prompt | ✓    | ✓      | 3.42s |
| A05     | clear             | prompt | ✓    | ✓      | 2.96s |
| A06     | clear             | prompt | ✓    | ✓      | 2.97s |
| A07     | clear             | prompt | ✓    | ✓      | 2.96s |
| A08     | clear             | prompt | ✓    | ✓      | 3.45s |
| A09     | clear             | prompt | ✓    | ✓      | 3.02s |
| A10     | clear             | prompt | ✓    | ✓      | 3.08s |
| B101    | role_ambiguity    | prompt | ✓    | ✓      | 3.28s |
| B102    | role_ambiguity    | prompt | ✓    | ✓      | 3.29s |
| B103    | role_ambiguity    | prompt | ✓    | ✓      | 3.04s |
| B104    | role_ambiguity    | prompt | ✓    | ✓      | 3.05s |
| B201    | available_ambiguity | prompt | ✓    | ✓      | 3.04s |
| B202    | available_ambiguity | prompt | ✓    | ✓      | 3.04s |
| B203    | available_ambiguity | prompt | ✓    | ✓      | 3.57s |
| B204    | available_ambiguity | prompt | ✓    | ✓      | 3.06s |
| B301    | age_ambiguity     | prompt | ✓    | ✓      | 3.29s |
| B302    | age_ambiguity     | prompt | ✓    | ✓      | 3.01s |
| B303    | age_ambiguity     | prompt | ✓    | ✓      | 3.20s |
| B304    | age_ambiguity     | prompt | ✓    | ✓      | 3.14s |
| C101    | missing_age       | prompt | ✓    | ✓      | 3.12s |
| C102    | missing_age       | prompt | ✓    | ✓      | 3.13s |
| C103    | missing_age       | prompt | ✓    | ✓      | 3.06s |
| C104    | missing_age       | prompt | ✓    | ✓      | 3.07s |
| C201    | missing_available | prompt | ✓    | ✓      | 3.18s |
| C202    | missing_available | prompt | ✓    | ✓      | 3.18s |
| C203    | missing_available | prompt | ✓    | ✓      | 3.08s |
| C204    | missing_available | prompt | ✓    | ✓      | 3.09s |
| A01     | clear             | guided | ✓    | ✓      | 3.82s |
| A02     | clear             | guided | ✓    | ✓      | 3.60s |
| A03     | clear             | guided | ✓    | ✓      | 3.54s |
| A04     | clear             | guided | ✓    | ✓      | 3.58s |
| A05     | clear             | guided | ✓    | ✓      | 3.32s |
| A06     | clear             | guided | ✓    | ✓      | 3.07s |
| A07     | clear             | guided | ✓    | ✓      | 3.03s |
| A08     | clear             | guided | ✓    | ✓      | 2.84s |
| A09     | clear             | guided | ✓    | ✓      | 2.81s |
| A10     | clear             | guided | ✓    | ✓      | 3.28s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 3.17s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 3.34s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 2.58s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 2.70s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 2.85s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 3.10s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 2.96s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 2.78s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 3.11s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 2.88s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 2.91s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 2.90s |
| C101    | missing_age       | guided | ✓    | ✓      | 2.86s |
| C102    | missing_age       | guided | ✓    | ✓      | 3.10s |
| C103    | missing_age       | guided | ✓    | ✓      | 2.84s |
| C104    | missing_age       | guided | ✓    | ✓      | 3.03s |
| C201    | missing_available | guided | ✓    | ✓      | 3.18s |
| C202    | missing_available | guided | ✓    | ✓      | 3.12s |
| C203    | missing_available | guided | ✓    | ✓      | 3.12s |
| C204    | missing_available | guided | ✓    | ✓      | 3.25s |