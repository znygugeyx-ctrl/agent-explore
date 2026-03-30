# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-28 12:25:56

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        | 11.94s   |            263 |
| prompt | 90/90 (100%)   | 90/90 (100%)     |  3.37s   |             62 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  2.95s   |             51 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |
| guided | 30/30 (100%)   | 30/30 (100%)   | 27/30 (90%)   | 30/30 (100%)   | 18/30 (60%)   | 30/30 (100%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | 6/12 (50%)   |
| guided | 6/12 (50%)   |

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
| prompt | 12/12 (100%)   |
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
| free   | 11.94s   |  3.62s   | 22.89s   |
| prompt |  3.37s   |  3.03s   |  3.72s   |
| guided |  2.95s   |  2.57s   |  3.21s   |

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
| A01     | clear             | free   | ✗    | ✗      | 6.83s |
| A02     | clear             | free   | ✗    | ✗      | 4.62s |
| A03     | clear             | free   | ✗    | ✗      | 9.85s |
| A04     | clear             | free   | ✗    | ✗      | 10.61s |
| A05     | clear             | free   | ✗    | ✗      | 10.02s |
| A06     | clear             | free   | ✗    | ✗      | 4.46s |
| A07     | clear             | free   | ✗    | ✗      | 18.81s |
| A08     | clear             | free   | ✗    | ✗      | 3.62s |
| A09     | clear             | free   | ✗    | ✗      | 14.35s |
| A10     | clear             | free   | ✗    | ✗      | 13.59s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 22.50s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 22.42s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 11.15s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 5.71s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 7.48s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 10.10s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 8.48s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 22.28s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 9.62s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 22.32s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 12.07s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 7.68s |
| C101    | missing_age       | free   | ✗    | ✗      | 7.67s |
| C102    | missing_age       | free   | ✗    | ✗      | 6.25s |
| C103    | missing_age       | free   | ✗    | ✗      | 22.60s |
| C104    | missing_age       | free   | ✗    | ✗      | 22.58s |
| C201    | missing_available | free   | ✗    | ✗      | 9.32s |
| C202    | missing_available | free   | ✗    | ✗      | 9.34s |
| C203    | missing_available | free   | ✗    | ✗      | 13.50s |
| C204    | missing_available | free   | ✗    | ✗      | 7.83s |
| A01     | clear             | prompt | ✓    | ✓      | 3.37s |
| A02     | clear             | prompt | ✓    | ✓      | 3.24s |
| A03     | clear             | prompt | ✓    | ✓      | 3.17s |
| A04     | clear             | prompt | ✓    | ✓      | 3.24s |
| A05     | clear             | prompt | ✓    | ✓      | 3.30s |
| A06     | clear             | prompt | ✓    | ✓      | 3.34s |
| A07     | clear             | prompt | ✓    | ✓      | 3.14s |
| A08     | clear             | prompt | ✓    | ✓      | 3.42s |
| A09     | clear             | prompt | ✓    | ✓      | 3.28s |
| A10     | clear             | prompt | ✓    | ✓      | 3.42s |
| B101    | role_ambiguity    | prompt | ✓    | ✓      | 3.51s |
| B102    | role_ambiguity    | prompt | ✓    | ✓      | 3.51s |
| B103    | role_ambiguity    | prompt | ✓    | ✓      | 3.26s |
| B104    | role_ambiguity    | prompt | ✓    | ✓      | 3.41s |
| B201    | available_ambiguity | prompt | ✓    | ✓      | 3.23s |
| B202    | available_ambiguity | prompt | ✓    | ✓      | 3.44s |
| B203    | available_ambiguity | prompt | ✓    | ✓      | 3.49s |
| B204    | available_ambiguity | prompt | ✓    | ✓      | 3.03s |
| B301    | age_ambiguity     | prompt | ✓    | ✓      | 3.41s |
| B302    | age_ambiguity     | prompt | ✓    | ✓      | 3.21s |
| B303    | age_ambiguity     | prompt | ✓    | ✓      | 3.34s |
| B304    | age_ambiguity     | prompt | ✓    | ✓      | 3.55s |
| C101    | missing_age       | prompt | ✓    | ✓      | 3.13s |
| C102    | missing_age       | prompt | ✓    | ✓      | 3.37s |
| C103    | missing_age       | prompt | ✓    | ✓      | 3.47s |
| C104    | missing_age       | prompt | ✓    | ✓      | 3.50s |
| C201    | missing_available | prompt | ✓    | ✓      | 3.54s |
| C202    | missing_available | prompt | ✓    | ✓      | 3.51s |
| C203    | missing_available | prompt | ✓    | ✓      | 3.27s |
| C204    | missing_available | prompt | ✓    | ✓      | 3.30s |
| A01     | clear             | guided | ✓    | ✓      | 2.72s |
| A02     | clear             | guided | ✓    | ✓      | 3.04s |
| A03     | clear             | guided | ✓    | ✓      | 2.93s |
| A04     | clear             | guided | ✓    | ✓      | 3.13s |
| A05     | clear             | guided | ✓    | ✓      | 2.82s |
| A06     | clear             | guided | ✓    | ✓      | 3.02s |
| A07     | clear             | guided | ✓    | ✓      | 2.69s |
| A08     | clear             | guided | ✓    | ✓      | 3.02s |
| A09     | clear             | guided | ✓    | ✓      | 2.82s |
| A10     | clear             | guided | ✓    | ✓      | 3.03s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 3.03s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 3.03s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 2.75s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 2.95s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 2.95s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 3.15s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 2.97s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 2.88s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 3.00s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 2.83s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 2.82s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 2.91s |
| C101    | missing_age       | guided | ✓    | ✓      | 2.85s |
| C102    | missing_age       | guided | ✓    | ✓      | 3.03s |
| C103    | missing_age       | guided | ✓    | ✓      | 3.02s |
| C104    | missing_age       | guided | ✓    | ✓      | 2.86s |
| C201    | missing_available | guided | ✓    | ✓      | 3.06s |
| C202    | missing_available | guided | ✓    | ✓      | 2.98s |
| C203    | missing_available | guided | ✓    | ✓      | 3.21s |
| C204    | missing_available | guided | ✓    | ✓      | 3.00s |