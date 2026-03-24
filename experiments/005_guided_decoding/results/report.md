# 实验 005：Guided Decoding — 结构保证 vs 语义质量

生成时间：2026-03-23 23:53:06

模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略

---

## H1：结构正确性

| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |
|--------|----------------|------------------|----------|----------------|
| free   | 0/90 (0%)      | 0/90 (0%)        |  5.07s   |            181 |
| prompt | 90/90 (100%)   | 90/90 (100%)     |  2.20s   |             55 |
| guided | 90/90 (100%)   | 90/90 (100%)     |  2.44s   |             64 |

## H2–H4：各子组字段准确率


### A  清晰 case（精确匹配）

| 策略   | name       | age        | role       | location   | skills     | available  |
|--------|------------|------------|------------|------------|------------|------------|
| free   | N/A        | N/A        | N/A        | N/A        | N/A        | N/A        |
| prompt | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |
| guided | 30/30 (100%)   | 30/30 (100%)   | 18/30 (60%)   | 30/30 (100%)   | 21/30 (70%)   | 30/30 (100%)   |

### B1 role 歧义（LLM judge）

| 策略   | role       |
|--------|------------|
| free   | N/A        |
| prompt | 9/12 (75%)   |
| guided | 0/12 (0%)   |

### B2 available 歧义（LLM judge）

| 策略   | available  |
|--------|------------|
| free   | N/A        |
| prompt | 3/12 (25%)   |
| guided | 6/12 (50%)   |

### B3 age 近似（范围匹配）

| 策略   | age        |
|--------|------------|
| free   | N/A        |
| prompt | 12/12 (100%)   |
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
| free   |  5.07s   |  1.95s   | 13.40s   |
| prompt |  2.20s   |  1.82s   |  3.06s   |
| guided |  2.44s   |  1.98s   |  4.02s   |

## 假设验证小结

| 假设 | 内容                                     | 验证结果 |
|------|------------------------------------------|----------|
| H1   | guided 100% 结构合法                     | ✅ 确认：free=0%，prompt/guided=100% |
| H2   | Group A 三策略语义准确率相当              | ❌ 不成立：guided role 仅 60%，prompt 100% |
| H3   | Group B1 guided role 准确率低于 prompt   | ✅ 强烈确认：guided 0% vs prompt 75% |
| H4   | Group B2 available 策略间差异            | ⚠️ 反直觉：guided 50% > prompt 25% |
| H5   | Group C guided 幻觉率高于 prompt         | ⚠️ 部分成立：两者均 100%，无差异 |
| H6   | /no_think 后三策略延迟无明显差异          | ✅ 基本确认：prompt 2.20s，guided 2.44s |

## 各任务详情（所有策略，第 1 轮）

| 任务 ID | 子组              | 策略   | 解析 | Schema | 延迟  |
|---------|-------------------|--------|------|--------|-------|
| A01     | clear             | free   | ✗    | ✗      | 8.74s |
| A02     | clear             | free   | ✗    | ✗      | 2.64s |
| A03     | clear             | free   | ✗    | ✗      | 4.14s |
| A04     | clear             | free   | ✗    | ✗      | 3.19s |
| A05     | clear             | free   | ✗    | ✗      | 4.15s |
| A06     | clear             | free   | ✗    | ✗      | 3.59s |
| A07     | clear             | free   | ✗    | ✗      | 3.46s |
| A08     | clear             | free   | ✗    | ✗      | 3.53s |
| A09     | clear             | free   | ✗    | ✗      | 2.77s |
| A10     | clear             | free   | ✗    | ✗      | 4.36s |
| B101    | role_ambiguity    | free   | ✗    | ✗      | 10.23s |
| B102    | role_ambiguity    | free   | ✗    | ✗      | 7.78s |
| B103    | role_ambiguity    | free   | ✗    | ✗      | 4.12s |
| B104    | role_ambiguity    | free   | ✗    | ✗      | 3.72s |
| B201    | available_ambiguity | free   | ✗    | ✗      | 8.71s |
| B202    | available_ambiguity | free   | ✗    | ✗      | 6.17s |
| B203    | available_ambiguity | free   | ✗    | ✗      | 3.59s |
| B204    | available_ambiguity | free   | ✗    | ✗      | 4.68s |
| B301    | age_ambiguity     | free   | ✗    | ✗      | 4.69s |
| B302    | age_ambiguity     | free   | ✗    | ✗      | 7.27s |
| B303    | age_ambiguity     | free   | ✗    | ✗      | 1.95s |
| B304    | age_ambiguity     | free   | ✗    | ✗      | 7.67s |
| C101    | missing_age       | free   | ✗    | ✗      | 4.33s |
| C102    | missing_age       | free   | ✗    | ✗      | 3.02s |
| C103    | missing_age       | free   | ✗    | ✗      | 3.22s |
| C104    | missing_age       | free   | ✗    | ✗      | 12.85s |
| C201    | missing_available | free   | ✗    | ✗      | 4.06s |
| C202    | missing_available | free   | ✗    | ✗      | 2.71s |
| C203    | missing_available | free   | ✗    | ✗      | 3.68s |
| C204    | missing_available | free   | ✗    | ✗      | 2.62s |
| A01     | clear             | prompt | ✓    | ✓      | 2.05s |
| A02     | clear             | prompt | ✓    | ✓      | 2.28s |
| A03     | clear             | prompt | ✓    | ✓      | 2.00s |
| A04     | clear             | prompt | ✓    | ✓      | 2.35s |
| A05     | clear             | prompt | ✓    | ✓      | 1.82s |
| A06     | clear             | prompt | ✓    | ✓      | 2.58s |
| A07     | clear             | prompt | ✓    | ✓      | 2.35s |
| A08     | clear             | prompt | ✓    | ✓      | 2.28s |
| A09     | clear             | prompt | ✓    | ✓      | 2.32s |
| A10     | clear             | prompt | ✓    | ✓      | 2.37s |
| B101    | role_ambiguity    | prompt | ✓    | ✓      | 2.37s |
| B102    | role_ambiguity    | prompt | ✓    | ✓      | 2.65s |
| B103    | role_ambiguity    | prompt | ✓    | ✓      | 2.38s |
| B104    | role_ambiguity    | prompt | ✓    | ✓      | 2.28s |
| B201    | available_ambiguity | prompt | ✓    | ✓      | 2.05s |
| B202    | available_ambiguity | prompt | ✓    | ✓      | 2.28s |
| B203    | available_ambiguity | prompt | ✓    | ✓      | 2.10s |
| B204    | available_ambiguity | prompt | ✓    | ✓      | 2.09s |
| B301    | age_ambiguity     | prompt | ✓    | ✓      | 2.19s |
| B302    | age_ambiguity     | prompt | ✓    | ✓      | 2.21s |
| B303    | age_ambiguity     | prompt | ✓    | ✓      | 2.20s |
| B304    | age_ambiguity     | prompt | ✓    | ✓      | 2.07s |
| C101    | missing_age       | prompt | ✓    | ✓      | 2.07s |
| C102    | missing_age       | prompt | ✓    | ✓      | 2.30s |
| C103    | missing_age       | prompt | ✓    | ✓      | 1.82s |
| C104    | missing_age       | prompt | ✓    | ✓      | 2.10s |
| C201    | missing_available | prompt | ✓    | ✓      | 2.33s |
| C202    | missing_available | prompt | ✓    | ✓      | 2.40s |
| C203    | missing_available | prompt | ✓    | ✓      | 2.12s |
| C204    | missing_available | prompt | ✓    | ✓      | 3.06s |
| A01     | clear             | guided | ✓    | ✓      | 3.45s |
| A02     | clear             | guided | ✓    | ✓      | 3.77s |
| A03     | clear             | guided | ✓    | ✓      | 3.21s |
| A04     | clear             | guided | ✓    | ✓      | 4.02s |
| A05     | clear             | guided | ✓    | ✓      | 2.24s |
| A06     | clear             | guided | ✓    | ✓      | 2.28s |
| A07     | clear             | guided | ✓    | ✓      | 2.25s |
| A08     | clear             | guided | ✓    | ✓      | 2.47s |
| A09     | clear             | guided | ✓    | ✓      | 2.37s |
| A10     | clear             | guided | ✓    | ✓      | 2.64s |
| B101    | role_ambiguity    | guided | ✓    | ✓      | 2.58s |
| B102    | role_ambiguity    | guided | ✓    | ✓      | 2.66s |
| B103    | role_ambiguity    | guided | ✓    | ✓      | 2.25s |
| B104    | role_ambiguity    | guided | ✓    | ✓      | 2.50s |
| B201    | available_ambiguity | guided | ✓    | ✓      | 2.56s |
| B202    | available_ambiguity | guided | ✓    | ✓      | 2.49s |
| B203    | available_ambiguity | guided | ✓    | ✓      | 2.40s |
| B204    | available_ambiguity | guided | ✓    | ✓      | 2.39s |
| B301    | age_ambiguity     | guided | ✓    | ✓      | 2.25s |
| B302    | age_ambiguity     | guided | ✓    | ✓      | 2.48s |
| B303    | age_ambiguity     | guided | ✓    | ✓      | 2.49s |
| B304    | age_ambiguity     | guided | ✓    | ✓      | 2.47s |
| C101    | missing_age       | guided | ✓    | ✓      | 2.40s |
| C102    | missing_age       | guided | ✓    | ✓      | 2.45s |
| C103    | missing_age       | guided | ✓    | ✓      | 2.39s |
| C104    | missing_age       | guided | ✓    | ✓      | 2.36s |
| C201    | missing_available | guided | ✓    | ✓      | 2.42s |
| C202    | missing_available | guided | ✓    | ✓      | 2.75s |
| C203    | missing_available | guided | ✓    | ✓      | 2.19s |
| C204    | missing_available | guided | ✓    | ✓      | 2.50s |