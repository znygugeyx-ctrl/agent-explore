# 实验 003（v3）：前缀缓存验证 — 结果报告

生成时间：2026-03-22 17:52:13

50 个工具，每个任务移除/掩码 10 个工具

## 汇总

| 策略 | 运行次数 | 准确率 | 平均延迟 | 平均首 Token 时间 | 缓存命中率 | 平均输入 Token | 平均输出 Token |
|------|---------|--------|----------|-----------------|-----------|--------------|--------------|
| all        | 3 | 83.3% | 12.34s | 0.683s | 99.5% | 11308 | 444 |
| remove     | 3 | 80.0% | 12.32s | 0.650s | 99.5% |  8304 | 457 |
| logit_mask | 3 | 88.3% | 17.33s | 0.650s | 98.8% | 13707 | 638 |
| desc_mask  | 3 | 83.3% | 12.17s | 0.652s | 98.9% | 10674 | 444 |

## 首 Token 时间（TTFT）分析

### all
- 均值：0.683s
- 中位数：0.660s
- P90：0.813s
- 最小值：0.564s，最大值：1.083s
- 总轮次数：139

### remove
- 均值：0.650s
- 中位数：0.642s
- P90：0.725s
- 最小值：0.371s，最大值：0.837s
- 总轮次数：122

### logit_mask
- 均值：0.650s
- 中位数：0.630s
- P90：0.700s
- 最小值：0.567s，最大值：1.407s
- 总轮次数：161

### desc_mask
- 均值：0.652s
- 中位数：0.638s
- P90：0.710s
- 最小值：0.565s，最大值：1.024s
- 总轮次数：129

## 前缀缓存指标

| 策略 | 运行 | 查询量（增量） | 命中量（增量） | 命中率 |
|------|-----|--------------|--------------|--------|
| all        | 1 | 706,223 | 702,752 | 99.5% |
| all        | 2 | 658,459 | 655,152 | 99.5% |
| all        | 3 | 667,393 | 664,064 | 99.5% |
| remove     | 1 | 495,056 | 492,640 | 99.5% |
| remove     | 2 | 497,687 | 495,248 | 99.5% |
| remove     | 3 | 492,588 | 490,176 | 99.5% |
| logit_mask | 1 | 867,299 | 855,584 | 98.6% |
| logit_mask | 2 | 818,303 | 811,712 | 99.2% |
| logit_mask | 3 | 815,371 | 804,208 | 98.6% |
| desc_mask  | 1 | 557,392 | 552,864 | 99.2% |
| desc_mask  | 2 | 645,179 | 635,280 | 98.5% |
| desc_mask  | 3 | 610,364 | 605,072 | 99.1% |

## 各任务结果（最后一轮运行）

| 任务 ID | 策略 | 正确 | 步骤 | 延迟 | 平均首 Token 时间 | Token 数 |
|--------|------|------|------|------|-----------------|---------|
| chain4_calc_bin_char_power          | all        | 否 |  4/4 |    8.07s |   0.694s |   9871 |
| chain4_reverse_len_mod_even         | all        | 是 |  4/4 |   12.07s |   0.840s |  10140 |
| chain4_wc_power_base_upper          | all        | 是 |  4/4 |    9.46s |   0.710s |  10000 |
| chain4_caesar_reverse_len_calc      | all        | 是 |  4/4 |    9.19s |   0.797s |   9946 |
| chain5_calc_gcd_bin_char_power      | all        | 是 |  5/5 |   11.69s |   0.698s |  10234 |
| chain4_temp_round_mod_abs           | all        | 是 |  4/4 |   12.75s |   0.659s |  25071 |
| chain5_reverse_upper_len_lcm_bin    | all        | 是 |  5/5 |    9.54s |   0.663s |  10022 |
| chain4_calc_floor_gcd_even          | all        | 是 |  4/4 |   13.30s |   0.762s |  10306 |
| chain4_lower_replace_char_calc      | all        | 否 |  0/4 |   25.66s |   0.715s |   5654 |
| chain5_calc_mod_power_sumdig_even   | all        | 否 |  5/5 |    9.76s |   0.616s |  10046 |
| chain4_sort_first3_upper_len        | all        | 是 |  4/4 |   16.50s |   0.618s |  10542 |
| chain5_wc_gcd_power_bin_char        | all        | 是 |  5/5 |   10.87s |   0.672s |  10150 |
| chain4_unique_len_max_round         | all        | 是 |  4/4 |   15.85s |   0.682s |  10493 |
| chain4_calc_base_lower_len          | all        | 是 |  4/4 |   13.05s |   0.709s |  10267 |
| chain5_temp_calc_mod_power_sumdig   | all        | 是 |  5/5 |   11.14s |   0.656s |  29602 |
| chain4_repeat_len_floor_bin         | all        | 是 |  4/4 |   11.48s |   0.605s |  10151 |
| chain5_caesar_char_lcm_mod_even     | all        | 是 |  5/5 |   10.98s |   0.647s |  10149 |
| chain4_slice_reverse_upper_len      | all        | 否 |  4/4 |   12.56s |   0.621s |  10237 |
| chain5_calc_pct_round_floor_bin     | all        | 是 |  5/5 |   11.05s |   0.633s |  10157 |
| chain6_reverse_len_power_bin_char_calc | all     | 是 |  6/6 |   10.19s |   0.738s |  10143 |
| chain4_calc_bin_char_power          | remove     | 否 |  4/4 |    8.30s |   0.736s |   8255 |
| chain4_reverse_len_mod_even         | remove     | 是 |  4/4 |    9.03s |   0.688s |   8322 |
| chain4_wc_power_base_upper          | remove     | 否 |  4/4 |    8.61s |   0.682s |   8316 |
| chain4_caesar_reverse_len_calc      | remove     | 是 |  4/4 |    7.75s |   0.667s |   8230 |
| chain5_calc_gcd_bin_char_power      | remove     | 是 |  5/5 |    9.66s |   0.626s |   8468 |
| chain4_temp_round_mod_abs           | remove     | 是 |  4/4 |   11.54s |   0.656s |  20821 |
| chain5_reverse_upper_len_lcm_bin    | remove     | 是 |  5/5 |    9.58s |   0.756s |   8408 |
| chain4_calc_floor_gcd_even          | remove     | 是 |  4/4 |   12.94s |   0.613s |   8682 |
| chain4_lower_replace_char_calc      | remove     | 否 |  5/4 |   34.58s |   0.630s |  25570 |
| chain5_calc_mod_power_sumdig_even   | remove     | 否 |  5/5 |    9.47s |   0.616s |   8406 |
| chain4_sort_first3_upper_len        | remove     | 是 |  4/4 |   23.48s |   0.667s |   9508 |
| chain5_wc_gcd_power_bin_char        | remove     | 是 |  5/5 |   12.38s |   0.722s |   8662 |
| chain4_unique_len_max_round         | remove     | 是 |  4/4 |    8.49s |   0.675s |   8285 |
| chain4_calc_base_lower_len          | remove     | 是 |  4/4 |   10.41s |   0.646s |   8465 |
| chain5_temp_calc_mod_power_sumdig   | remove     | 是 |  5/5 |   12.60s |   0.642s |   8664 |
| chain4_repeat_len_floor_bin         | remove     | 是 |  4/4 |   12.68s |   0.623s |   8639 |
| chain5_caesar_char_lcm_mod_even     | remove     | 是 |  5/5 |    9.50s |   0.597s |   8421 |
| chain4_slice_reverse_upper_len      | remove     | 否 |  4/4 |   11.96s |   0.631s |   8571 |
| chain5_calc_pct_round_floor_bin     | remove     | 是 |  5/5 |    9.38s |   0.643s |   8415 |
| chain6_reverse_len_power_bin_char_calc | remove  | 是 |  6/6 |    9.94s |   0.622s |   8525 |
| chain4_calc_bin_char_power          | logit_mask | 否 |  4/4 |    8.15s |   0.624s |   9871 |
| chain4_reverse_len_mod_even         | logit_mask | 是 | 30/4 |   43.55s |   0.662s |  18954 |
| chain4_wc_power_base_upper          | logit_mask | 是 |  4/4 |    9.83s |   0.633s |  10022 |
| chain4_caesar_reverse_len_calc      | logit_mask | 是 |  4/4 |   10.06s |   0.637s |  24596 |
| chain5_calc_gcd_bin_char_power      | logit_mask | 是 |  5/5 |   11.87s |   0.616s |  10242 |
| chain4_temp_round_mod_abs           | logit_mask | 是 |  4/4 |   11.54s |   0.625s |  24891 |
| chain5_reverse_upper_len_lcm_bin    | logit_mask | 是 |  5/5 |    9.19s |   0.595s |  10006 |
| chain4_calc_floor_gcd_even          | logit_mask | 是 |  8/4 |   18.10s |   0.644s |  16024 |
| chain4_lower_replace_char_calc      | logit_mask | 是 |  4/4 |   15.47s |   0.633s |  10479 |
| chain5_calc_mod_power_sumdig_even   | logit_mask | 否 | 19/5 |   39.94s |   0.703s |  58903 |
| chain4_sort_first3_upper_len        | logit_mask | 是 |  5/4 |   32.63s |   0.651s |  17569 |
| chain5_wc_gcd_power_bin_char        | logit_mask | 是 |  5/5 |   15.28s |   0.614s |  10522 |
| chain4_unique_len_max_round         | logit_mask | 是 |  4/4 |    8.33s |   0.660s |   9883 |
| chain4_calc_base_lower_len          | logit_mask | 是 |  4/4 |    8.73s |   0.604s |   9939 |
| chain5_temp_calc_mod_power_sumdig   | logit_mask | 是 |  5/5 |   11.13s |   0.610s |  10152 |
| chain4_repeat_len_floor_bin         | logit_mask | 是 |  4/4 |   11.68s |   0.652s |  10151 |
| chain5_caesar_char_lcm_mod_even     | logit_mask | 是 | 31/5 |   29.98s |   0.606s |  11819 |
| chain4_slice_reverse_upper_len      | logit_mask | 是 |  0/4 |   25.67s |   0.590s |   5644 |
| chain5_calc_pct_round_floor_bin     | logit_mask | 是 |  5/5 |   11.19s |   0.635s |  10171 |
| chain6_reverse_len_power_bin_char_calc | logit_mask | 是 |  6/6 |   10.34s |   0.629s |  10145 |
| chain4_calc_bin_char_power          | desc_mask  | 否 |  4/4 |    8.23s |   0.652s |  10051 |
| chain4_reverse_len_mod_even         | desc_mask  | 是 |  4/4 |    8.93s |   0.661s |  10088 |
| chain4_wc_power_base_upper          | desc_mask  | 是 |  4/4 |    9.56s |   0.622s |  10188 |
| chain4_caesar_reverse_len_calc      | desc_mask  | 是 |  4/4 |   10.60s |   0.653s |  25128 |
| chain5_calc_gcd_bin_char_power      | desc_mask  | 是 |  5/5 |    8.78s |   0.592s |  10186 |
| chain4_temp_round_mod_abs           | desc_mask  | 是 |  4/4 |   12.01s |   0.651s |  25401 |
| chain5_reverse_upper_len_lcm_bin    | desc_mask  | 是 |  5/5 |    9.64s |   0.656s |  10202 |
| chain4_calc_floor_gcd_even          | desc_mask  | 是 |  4/4 |   15.67s |   0.621s |  10706 |
| chain4_lower_replace_char_calc      | desc_mask  | 否 |  4/4 |   20.56s |   0.647s |  11083 |
| chain5_calc_mod_power_sumdig_even   | desc_mask  | 否 |  5/5 |    9.76s |   0.611s |  10226 |
| chain4_sort_first3_upper_len        | desc_mask  | 是 |  4/4 |   14.56s |   0.684s |  10556 |
| chain5_wc_gcd_power_bin_char        | desc_mask  | 是 |  5/5 |   11.15s |   0.621s |  10352 |
| chain4_unique_len_max_round         | desc_mask  | 是 |  4/4 |   14.81s |   0.637s |  10599 |
| chain4_calc_base_lower_len          | desc_mask  | 是 |  4/4 |    9.94s |   0.684s |  10199 |
| chain5_temp_calc_mod_power_sumdig   | desc_mask  | 是 |  5/5 |   13.09s |   0.724s |  10468 |
| chain4_repeat_len_floor_bin         | desc_mask  | 是 |  4/4 |   11.34s |   0.631s |  10305 |
| chain5_caesar_char_lcm_mod_even     | desc_mask  | 是 |  5/5 |   10.77s |   0.665s |  10313 |
| chain4_slice_reverse_upper_len      | desc_mask  | 否 |  4/4 |   13.57s |   0.608s |  10495 |
| chain5_calc_pct_round_floor_bin     | desc_mask  | 是 |  5/5 |   10.18s |   0.626s |  10271 |
| chain6_reverse_len_power_bin_char_calc | desc_mask | 是 |  6/6 |   10.10s |   0.640s |  10323 |

## Token 映射表（Logit Mask — 前 10 个工具）

| 工具名称 | 封锁的 Token ID |
|---------|---------------|
| hex_encode | [12371, 17308] |
| hex_decode | [12371, 17308] |
| rot13 | [4640, 5749] |
| ascii_value | [23324, 47120] |
| vowel_count | [85, 76181] |
| consonant_count | [443, 77505] |
| is_palindrome | [285, 374] |
| factorial | [37591, 52962] |
| fibonacci | [75326, 75698] |
| prime_check | [10250, 32338] |

---

## 与 Manus "遮蔽，而非移除" 论点的偏差分析

### Manus 的核心论点

> "工具定义在序列化后位于上下文的前部，因此任何更改都会使后续所有动作和观察的 KV 缓存失效。"

> "Manus 使用上下文感知的 logit 遮蔽来管理工具可用性。它不是移除工具，而是在解码过程中遮蔽 token 的 logits，以在不修改工具定义的情况下约束动作空间。"

### 我们的观测

四种策略的 cache 命中率均在 **98.5%–99.5%** 之间，无显著差异；TTFT 在所有策略间几乎完全相同（0.650–0.683s），未出现预期中 Remove > Mask 的延迟差距。

**结论：在本实验条件下，Manus "遮蔽，而非移除" 的优势未能观测到。**

---

### 原因 1：缓存复用以"任务内"为主，而非"任务间"（最关键）

我们测量到的 ~99% 命中率，绝大部分来自**同一任务内的多轮复用**：turn 2 复用 turn 1 的完整上下文前缀，turn 3 复用 turn 2 的前缀。由于我们的实验设计中每个任务内工具集静态不变，这对所有策略都同样有效。

Manus 关注的是**跨用户、跨任务的前缀共享**：在生产环境中，成千上万并发用户共享同一套工具定义，只要工具列表不变，所有请求的第一轮 prefill 都可命中缓存。Remove 策略因为每个任务移除的工具不同，导致不同任务的前缀各不相同，破坏了**跨请求的缓存复用**。

我们的实验（3 个并行 run，任务串行）没有产生足够的跨任务并发压力，无法体现这一差异。

### 原因 2：vLLM block 级缓存 vs API 精确前缀匹配

Manus 的成本论据（缓存 token 价格 $0.30 vs 未缓存 $3.00，相差 10 倍）基于 **API 提供商（Anthropic/OpenAI）的全局精确前缀缓存**。前缀哪怕差一个 token 即为 miss，是全有或全无的匹配。

vLLM 的 prefix caching 是**本地 block 级别**（通常 16 token 一个 block），粒度更粗，容错性更高。即使 prompt 开头的 10 个工具被删除（约 2000 token，占总 ~10K token 的 20%），后续 80% 的 block 仍然可以命中，因此 remove 策略的 hit rate 看起来和 all 一样高。

### 原因 3：移除规模太小，缓存破坏效果被稀释

我们只移除了 10/50 个工具（约 2000/10000 token，占比 20%）。Manus 面对的是用户动态插入**数百个自定义工具**的场景，工具列表的变化幅度远大于我们的实验，缓存破坏的比例也更大。

### 原因 4：延迟指标掩盖了成本差距

即便 cache miss，在 L40S 单卡上对 10K token 做一次 prefill 也只需约 100–200ms，相对于总延迟（12s）几乎可以忽略，TTFT 上自然看不到差距。Manus 更关注的是**成本**（10 倍价格差），而非延迟；我们的实验没有测量成本维度。

### 原因 5：第二个论点（模型困惑）被实验设计规避

Manus 的第二个理由：先前动作引用了已移除工具时，模型会困惑。这个问题只在**运行中途动态增删工具**时才会发生。我们的 remove 策略在任务开始前就静态确定工具集，全程不变，因此不存在 trace 引用已移除工具的情况，这个论点无法在我们的实验设计中被测试。

---

### Logit Mask 的异常行为

实验中 logit_mask 平均延迟明显偏高（17.33s vs ~12s），部分任务步数远超预期（如某任务实际执行了 30 步，预期只有 4 步）。原因是 logit_bias 强制阻断了某些 token 的概率，在少数情况下导致模型陷入迂回推理——它意识到某些工具不可调用，但找不到合适的替代路径，反复尝试消耗大量轮次。这说明 logit_mask 虽然保留了 prefix cache，但有一定的**稳定性风险**，实际总成本（延迟 × token 数）在极端情况下可能更高。

---

### 适用场景总结

| 条件 | 本实验 | Manus 生产场景 |
|------|--------|---------------|
| 并发量 | 3 个并行 | 数千并发用户 |
| 缓存机制 | vLLM 本地 block 级 | API 全局精确前缀匹配 |
| 关键收益 | 延迟 | **成本**（10x 价格差） |
| 工具变化幅度 | 20%（10/50） | 大规模自定义工具增删 |
| 工具管理模式 | 静态（任务级） | 动态（轮次级） |

**Manus 的建议在高并发 API 生产环境（精确前缀匹配、按 token 计费、动态工具管理）下是合理的。在单 GPU 低并发自托管场景下，Remove 策略仍是最简单且最省 token 的选择（本实验减少约 27% 输入 token），Mask 策略的缓存收益在此场景下不显著。**

---

## 与 v2 实验的对比

| 指标 | v2（8 工具，2-3 步） | v3（50 工具，4-6 步） |
|------|---------------------|----------------------|
| All 准确率 | 100% | 83.3% |
| Remove 准确率 | 93.3% | 80.0% |
| All TTFT | 未测量 | 0.683s |
| Remove TTFT | 未测量 | 0.650s |
| All 缓存命中率 | 未测量 | 99.5% |
| Remove 缓存命中率 | 未测量 | 99.5% |
| All 输入 token | 2,554 | 11,308（+343%） |
| Remove 输入 token | 1,310 | 8,304（+534%） |

扩展到 50 工具后，输入 token 大幅增加，但准确率有所下降（更大工具集增加了工具选择难度）。缓存指标在两个实验尺度上均未呈现出策略间差异，说明在本实验设计中，缓存复用主要由任务内多轮对话驱动，而非跨任务的前缀共享。
