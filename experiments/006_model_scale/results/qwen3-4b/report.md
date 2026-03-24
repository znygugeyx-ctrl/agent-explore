# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-24 12:40:39

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        |  3.61s   |            224 |
| prompt | 90/90 (100%)   | 90/90 (100%)     |  1.65s   |             61 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  1.68s   |             62 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | 30/30 (100%)   | 30/30 (100%)   | 27/30 (90%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |
| guided | 30/30 (100%)   | 30/30 (100%)   | 9/30 (30%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | 6/12 (50%)   |
| guided | 0/12 (0%)   |

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
| guided | 9/12 (75%)   |

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
| free   |  3.61s   |  1.64s   |  7.30s   |
| prompt |  1.65s   |  1.39s   |  2.65s   |
| guided |  1.68s   |  1.29s   |  2.38s   |

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
| A01     | clear             | free   | ✗    | ✗      | 6.07s |
| A02     | clear             | free   | ✗    | ✗      | 2.16s |
| A03     | clear             | free   | ✗    | ✗      | 4.96s |
| A04     | clear             | free   | ✗    | ✗      | 2.88s |
| A05     | clear             | free   | ✗    | ✗      | 2.85s |
| A06     | clear             | free   | ✗    | ✗      | 1.87s |
| A07     | clear             | free   | ✗    | ✗      | 2.96s |
| A08     | clear             | free   | ✗    | ✗      | 2.00s |
| A09     | clear             | free   | ✗    | ✗      | 2.96s |
| A10     | clear             | free   | ✗    | ✗      | 2.41s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 2.64s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 3.93s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 3.22s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 2.21s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 5.79s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 2.71s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 2.70s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 4.46s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 3.46s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 7.18s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 2.97s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 7.18s |
| C101    | missing_age       | free   | ✗    | ✗      | 2.37s |
| C102    | missing_age       | free   | ✗    | ✗      | 3.18s |
| C103    | missing_age       | free   | ✗    | ✗      | 7.19s |
| C104    | missing_age       | free   | ✗    | ✗      | 7.03s |
| C201    | missing_available | free   | ✗    | ✗      | 3.18s |
| C202    | missing_available | free   | ✗    | ✗      | 2.17s |
| C203    | missing_available | free   | ✗    | ✗      | 2.19s |
| C204    | missing_available | free   | ✗    | ✗      | 2.87s |
| A01     | clear             | prompt | ✓    | ✓      | 1.80s |
| A02     | clear             | prompt | ✓    | ✓      | 1.80s |
| A03     | clear             | prompt | ✓    | ✓      | 1.81s |
| A04     | clear             | prompt | ✓    | ✓      | 2.03s |
| A05     | clear             | prompt | ✓    | ✓      | 1.42s |
| A06     | clear             | prompt | ✓    | ✓      | 1.67s |
| A07     | clear             | prompt | ✓    | ✓      | 1.51s |
| A08     | clear             | prompt | ✓    | ✓      | 1.69s |
| A09     | clear             | prompt | ✓    | ✓      | 1.56s |
| A10     | clear             | prompt | ✓    | ✓      | 1.60s |
| B101    | role_ambiguity    | prompt | ✓    | ✓      | 1.52s |
| B102    | role_ambiguity    | prompt | ✓    | ✓      | 1.53s |
| B103    | role_ambiguity    | prompt | ✓    | ✓      | 1.44s |
| B104    | role_ambiguity    | prompt | ✓    | ✓      | 1.52s |
| B201    | available_ambiguity | prompt | ✓    | ✓      | 1.69s |
| B202    | available_ambiguity | prompt | ✓    | ✓      | 1.68s |
| B203    | available_ambiguity | prompt | ✓    | ✓      | 1.55s |
| B204    | available_ambiguity | prompt | ✓    | ✓      | 1.58s |
| B301    | age_ambiguity     | prompt | ✓    | ✓      | 1.60s |
| B302    | age_ambiguity     | prompt | ✓    | ✓      | 1.55s |
| B303    | age_ambiguity     | prompt | ✓    | ✓      | 1.47s |
| B304    | age_ambiguity     | prompt | ✓    | ✓      | 1.70s |
| C101    | missing_age       | prompt | ✓    | ✓      | 1.54s |
| C102    | missing_age       | prompt | ✓    | ✓      | 1.70s |
| C103    | missing_age       | prompt | ✓    | ✓      | 1.62s |
| C104    | missing_age       | prompt | ✓    | ✓      | 1.70s |
| C201    | missing_available | prompt | ✓    | ✓      | 1.47s |
| C202    | missing_available | prompt | ✓    | ✓      | 1.72s |
| C203    | missing_available | prompt | ✓    | ✓      | 1.47s |
| C204    | missing_available | prompt | ✓    | ✓      | 1.48s |
| A01     | clear             | guided | ✓    | ✓      | 1.83s |
| A02     | clear             | guided | ✓    | ✓      | 1.87s |
| A03     | clear             | guided | ✓    | ✓      | 1.77s |
| A04     | clear             | guided | ✓    | ✓      | 2.02s |
| A05     | clear             | guided | ✓    | ✓      | 1.55s |
| A06     | clear             | guided | ✓    | ✓      | 1.67s |
| A07     | clear             | guided | ✓    | ✓      | 1.38s |
| A08     | clear             | guided | ✓    | ✓      | 1.71s |
| A09     | clear             | guided | ✓    | ✓      | 1.53s |
| A10     | clear             | guided | ✓    | ✓      | 1.76s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 1.85s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 1.85s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 1.57s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 1.73s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 1.54s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 1.54s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 1.54s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 1.30s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 1.48s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 1.46s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 1.60s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 1.60s |
| C101    | missing_age       | guided | ✓    | ✓      | 1.59s |
| C102    | missing_age       | guided | ✓    | ✓      | 1.64s |
| C103    | missing_age       | guided | ✓    | ✓      | 1.50s |
| C104    | missing_age       | guided | ✓    | ✓      | 1.65s |
| C201    | missing_available | guided | ✓    | ✓      | 1.72s |
| C202    | missing_available | guided | ✓    | ✓      | 1.72s |
| C203    | missing_available | guided | ✓    | ✓      | 1.73s |
| C204    | missing_available | guided | ✓    | ✓      | 1.74s |