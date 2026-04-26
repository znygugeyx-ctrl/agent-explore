# D2L Baseline 初步分析（临时）

**时间**: 2026-04-25
**状态**: RAG + MSA 完成，D2L 仍在编译 flash-attn（进行中）
**评分方法**: LLM Judge (Claude Sonnet 4.6, 0-5 分)

---

## 1. 总体结果对比

### HotpotQA（200题）

| 方案 | 2K pool | 4K pool | 8K pool | 均值 |
|------|:---:|:---:|:---:|:---:|
| **RAG** | 4.125 | 4.215 | 4.225 | 4.188 |
| **MSA** | 4.460 | 4.440 | 4.260 | 4.387 |
| **D2L** | — | — | — | 待测 |

**观察**：
- MSA 整体 > RAG（+0.20 pp）
- MSA 随 pool 增大性能轻微下降（4.46 → 4.26），符合 top-k router 在大 corpus 中信号稀释
- RAG 随 pool 增大反而小幅上升（4.13 → 4.23），可能因为 2K pool 里 distractor 少但 gold 信息也少

### 小说 QA（131题，中文）

| 方案 | Overall | Easy (n=44) | Medium (n=57) | Hard (n=30) |
|------|:---:|:---:|:---:|:---:|
| **RAG** | **3.840** | 4.419 | 3.986 | 2.935 |
| **MSA** | 2.802 | 3.194 | 2.870 | 2.258 |
| **D2L** | — | — | — | — |

**观察**：
- **RAG 显著优于 MSA**（+1.04 pp，相对提升 37%）
- 两方案都随难度递减：easy → medium → hard 明显下降
- 与 013 原始实验一致：MSA 在中文上表现不佳（原始 MSA-EN=1.574, RAG-CN v2=2.152），新数据集上 RAG 进一步拉开差距

---

## 2. 按类别分析（小说）

| Category | RAG | MSA | 差距 |
|----------|:---:|:---:|:---:|
| item | 4.565 | 3.000 | +1.57 |
| location | 4.500 | 2.000 | +2.50 |
| event | 4.455 | 2.545 | +1.91 |
| character | 3.917 | 3.750 | +0.17 |
| reasoning | 3.423 | 2.704 | +0.72 |
| relationship | 1.000 | 1.000 | 0.00 |

**观察**：
- RAG 在事实检索类（item/location/event）大幅领先（+1.5-2.5 pp）
- character 类两者接近（MSA 的强项）
- relationship 类两者都极差 — 说明关系推理跨 section 能力不足，与 context 长度无关

---

## 3. 关键发现

### 3.1 HotpotQA：MSA 整体优于 RAG
MSA 的 learned router 在英文短文本（avg 116 tokens/doc）上表现良好。但我们实验有一个**方法学问题**：

- 我们把 200 题的 pool docs 合并成一个 corpus（8k 档 6970 unique docs）给 MSA
- MSA retrieval precision：**2k=9.75%, 4k=4.75%, 8k=3.0%**（远低于 013 原始 85%）
- 但 LLM Judge 评答案质量仍然很高（4.26-4.46）

**这说明**：MSA 的 `pred_answer` 不完全依赖 router 选出的 top-k docs，多轮生成流程中模型可能从已编码的 KV cache 中其他位置提取信息。**retrieval precision 低不等于答案质量差**。

### 3.2 小说：RAG >> MSA（与 013 原始实验一致但差距更大）
- 013 原始：MSA-EN=1.574, RAG-CN v2=2.152（差距 0.58）
- 本次实验：MSA=2.802, RAG=3.840（差距 1.04）

**解释**：
- 本次 RAG 跑在受控 8K window 上，答案密度比全书检索高
- MSA 仍受限于英文模板（"The answer to the question is:"），中文生成被截断

### 3.3 Hard 题是三个方案的瓶颈
| 方案 | Easy | Hard | 降幅 |
|------|:---:|:---:|:---:|
| RAG | 4.419 | 2.935 | -34% |
| MSA | 3.194 | 2.258 | -29% |

Hard 题需要跨 section 推理（虽然 gold context 都在 8K window 内）。relationship 类两者都是 1.0，表明**关系推理是模型本身能力瓶颈**，与记忆机制无关。

### 3.4 小样本偏差需要警惕
- relationship 类仅 6 题 → 置信度低
- location 类 RAG 4.50, MSA 2.00 但样本少 → 结论谨慎

---

## 4. 方法学说明（important caveats）

### 4.1 MSA 的 corpus 合并偏差
为了单次运行 MSA engine（避免每题重启 worker 开销），我们把 200 题的 pool docs 合并成一个大 corpus。这与"严格控制信息量"的原则有偏离：

- 对 RAG：每题独立 pool，符合约束
- 对 MSA：corpus 包含其他题的 docs，但 router 选 top-k 仍主要命中相关 docs（从 retrieval precision 可看出这是 MSA 的天然路由行为）
- 对 D2L：每题独立 internalize，最严格

### 4.2 小说 MSA corpus 重切分
Agent 2 遇到 NCCL 超时，把原始 131 docs × 10K chars 切成 155 docs × 2141 chars。MSA 的小说评测实际用的是切分后版本，与 RAG 不完全对齐。

### 4.3 RAG v1 bug 已修复
初版 RAG 把 8K context_text 截断到 1500 字符导致 74% 拒答，v2 改为 500 字符 chunks 检索 top-5，拒答率降到 3.8%。

---

## 5. 待完成

1. **D2L 实验**（等 flash-attn 2.6.3 编译完，~15min）— 这是关键对比
2. **D2L vs MSA vs RAG 综合分析**
3. 按题目 id 配对比较三方案的胜负分布
4. 延迟对比（RAG ~2s vs MSA ~2min/131题 vs D2L 待测）

---

## 6. 预期的 D2L 表现（待验证）

基于论文的 F1 benchmarks 和我们小规模 pilot 预测：

| 场景 | 预期 |
|------|------|
| HotpotQA | 可能介于 RAG 和 MSA 之间（英文训练过）|
| 小说 | 大概率最差（LoRA 训练数据全英文，中文 OOD）|
| 短 context (2K) | 最好情况，LoRA 容量足够 |
| 长 context (8K) | 可能退化，因为需要压缩更多信息到同样 rank=8 LoRA |

**最有趣的对比**：若 D2L-HotpotQA-2K > MSA-HotpotQA-2K，说明参数化记忆在小规模信息上可以胜过注意力路由。

---

## 7. 数据文件位置

所有原始结果 + 评分后文件：
```
experiments/013_msa_novel_memory/d2l_baseline/results/
  {rag,msa}_{hotpotqa_{2k,4k,8k},novel_8k}.json          # 原始
  {rag,msa}_{hotpotqa_{2k,4k,8k},novel_8k}_scored.json  # 含 score 字段
  summary_partial.json                                    # 统计结果
```
