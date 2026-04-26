# D2L Baseline: 参数化记忆对比实验

## 核心问题

三种记忆范式（ICL / MSA / D2L）在相同信息量下，记忆保真度如何对比？

## 范式定义

| 范式 | 处理方式 | 推理时上下文成本 |
|------|---------|----------------|
| ICL (In-Context Learning) | 文档直接塞入 prompt | 全量 |
| MSA (Memory Sparse Attention) | 文档编码到 KV cache + learned router | ~0 |
| D2L (Doc-to-LoRA) | 文档编码为 LoRA 权重 | 0 |

## 假设

- **H1**: ICL 是信息零损失上限，MSA 和 D2L 都有压缩损失。在 8K 规模下 ICL > MSA ≥ D2L。
- **H2**: D2L 的保真度随信息量增长而下降（2K > 4K > 8K），因为 LoRA rank=8 的容量有限。
- **H3**: D2L 在英文（HotpotQA）上显著优于中文（小说），因为训练数据全为英文。
- **H4**: 在 2K（D2L 训练分布内）规模下，D2L 的压缩损失最小，可能接近 ICL。

## 实验设计

### HotpotQA: 2K/4K/8K 三档信息梯度
- 200 题，每题构造嵌套 context pools (pool_2K ⊂ pool_4K ⊂ pool_8K)
- 三种方案 × 三档 = 9 个条件

### 小说 QA: 8K 一档
- ~180 题，重新构造（确保 hard 题 gold context 在 8K 内）
- 三种方案 × 1 档 = 3 个条件

### 评估
- LLM Judge (Claude Sonnet 4.6, 0-5 分)
