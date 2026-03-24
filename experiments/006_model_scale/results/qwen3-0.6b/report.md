# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-24 12:33:02

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        |  0.94s   |             75 |
| prompt | 0/90 (0%)      | 0/90 (0%)        |  0.95s   |             67 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  1.00s   |             65 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| guided | 30/30 (100%)   | 30/30 (100%)   | 27/30 (90%)   | 30/30 (100%)   | 18/30 (60%)   | 18/30 (60%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | N/A        |
| guided | 6/12 (50%)   |

### B2 available 歧义（LLM judge）

| 策略   | available  |
|--------|------------|
| free   | N/A        |
| prompt | N/A        |
| guided | 12/12 (100%)   |

### B3 age 近似（范围匹配）

| 策略   | age        |
|--------|------------|
| free   | N/A        |
| prompt | N/A        |
| guided | 9/12 (75%)   |

## H5：缺失信息处理（Group C 幻觉率）

| 策略   | 子组             | 缺失字段    | 幻觉次数 / 总次数 |
|--------|------------------|------------|-------------------|
| free   | missing_age      | age        | N/A               |
| prompt | missing_age      | age        | N/A               |
| guided | missing_age      | age        | 1/12（8% 幻觉）    |
| free   | missing_available | available  | N/A               |
| prompt | missing_available | available  | N/A               |
| guided | missing_available | available  | 0/12（0% 幻觉）    |

## H6：延迟对比（/no_think 模式）

| 策略   | 平均延迟 | 最小延迟 | 最大延迟 |
|--------|----------|----------|----------|
| free   |  0.94s   |  0.70s   |  1.61s   |
| prompt |  0.95s   |  0.71s   |  1.18s   |
| guided |  1.00s   |  0.71s   |  2.24s   |

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
| A01     | clear             | free   | ✗    | ✗      | 0.78s |
| A02     | clear             | free   | ✗    | ✗      | 0.96s |
| A03     | clear             | free   | ✗    | ✗      | 0.99s |
| A04     | clear             | free   | ✗    | ✗      | 1.02s |
| A05     | clear             | free   | ✗    | ✗      | 0.92s |
| A06     | clear             | free   | ✗    | ✗      | 0.70s |
| A07     | clear             | free   | ✗    | ✗      | 0.76s |
| A08     | clear             | free   | ✗    | ✗      | 0.93s |
| A09     | clear             | free   | ✗    | ✗      | 0.76s |
| A10     | clear             | free   | ✗    | ✗      | 0.77s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 1.60s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 0.76s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 0.77s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 0.97s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 0.98s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 1.15s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 0.82s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 0.97s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 0.96s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 1.20s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 0.79s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 1.15s |
| C101    | missing_age       | free   | ✗    | ✗      | 0.91s |
| C102    | missing_age       | free   | ✗    | ✗      | 0.72s |
| C103    | missing_age       | free   | ✗    | ✗      | 1.22s |
| C104    | missing_age       | free   | ✗    | ✗      | 0.88s |
| C201    | missing_available | free   | ✗    | ✗      | 0.78s |
| C202    | missing_available | free   | ✗    | ✗      | 0.98s |
| C203    | missing_available | free   | ✗    | ✗      | 0.96s |
| C204    | missing_available | free   | ✗    | ✗      | 0.87s |
| A01     | clear             | prompt | ✗    | ✗      | 0.94s |
| A02     | clear             | prompt | ✗    | ✗      | 0.94s |
| A03     | clear             | prompt | ✗    | ✗      | 0.92s |
| A04     | clear             | prompt | ✗    | ✗      | 1.15s |
| A05     | clear             | prompt | ✗    | ✗      | 0.91s |
| A06     | clear             | prompt | ✗    | ✗      | 0.91s |
| A07     | clear             | prompt | ✗    | ✗      | 0.85s |
| A08     | clear             | prompt | ✗    | ✗      | 0.96s |
| A09     | clear             | prompt | ✗    | ✗      | 0.72s |
| A10     | clear             | prompt | ✗    | ✗      | 0.74s |
| B101    | role_ambiguity    | prompt | ✗    | ✗      | 0.96s |
| B102    | role_ambiguity    | prompt | ✗    | ✗      | 0.96s |
| B103    | role_ambiguity    | prompt | ✗    | ✗      | 0.75s |
| B104    | role_ambiguity    | prompt | ✗    | ✗      | 0.96s |
| B201    | available_ambiguity | prompt | ✗    | ✗      | 0.96s |
| B202    | available_ambiguity | prompt | ✗    | ✗      | 0.96s |
| B203    | available_ambiguity | prompt | ✗    | ✗      | 0.96s |
| B204    | available_ambiguity | prompt | ✗    | ✗      | 0.95s |
| B301    | age_ambiguity     | prompt | ✗    | ✗      | 1.05s |
| B302    | age_ambiguity     | prompt | ✗    | ✗      | 1.07s |
| B303    | age_ambiguity     | prompt | ✗    | ✗      | 1.07s |
| B304    | age_ambiguity     | prompt | ✗    | ✗      | 1.08s |
| C101    | missing_age       | prompt | ✗    | ✗      | 1.07s |
| C102    | missing_age       | prompt | ✗    | ✗      | 1.06s |
| C103    | missing_age       | prompt | ✗    | ✗      | 1.05s |
| C104    | missing_age       | prompt | ✗    | ✗      | 1.05s |
| C201    | missing_available | prompt | ✗    | ✗      | 0.97s |
| C202    | missing_available | prompt | ✗    | ✗      | 0.98s |
| C203    | missing_available | prompt | ✗    | ✗      | 0.98s |
| C204    | missing_available | prompt | ✗    | ✗      | 1.01s |
| A01     | clear             | guided | ✓    | ✓      | 2.01s |
| A02     | clear             | guided | ✓    | ✓      | 2.01s |
| A03     | clear             | guided | ✓    | ✓      | 1.76s |
| A04     | clear             | guided | ✓    | ✓      | 2.24s |
| A05     | clear             | guided | ✓    | ✓      | 1.14s |
| A06     | clear             | guided | ✓    | ✓      | 0.96s |
| A07     | clear             | guided | ✓    | ✓      | 0.90s |
| A08     | clear             | guided | ✓    | ✓      | 0.97s |
| A09     | clear             | guided | ✓    | ✓      | 0.75s |
| A10     | clear             | guided | ✓    | ✓      | 0.77s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 0.97s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 0.96s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 0.74s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 0.96s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 0.97s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 0.97s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 0.98s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 0.98s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 0.99s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 0.98s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 0.96s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 1.04s |
| C101    | missing_age       | guided | ✓    | ✓      | 1.10s |
| C102    | missing_age       | guided | ✓    | ✓      | 1.10s |
| C103    | missing_age       | guided | ✓    | ✓      | 1.11s |
| C104    | missing_age       | guided | ✓    | ✓      | 1.04s |
| C201    | missing_available | guided | ✓    | ✓      | 0.97s |
| C202    | missing_available | guided | ✓    | ✓      | 0.98s |
| C203    | missing_available | guided | ✓    | ✓      | 0.99s |
| C204    | missing_available | guided | ✓    | ✓      | 0.98s |