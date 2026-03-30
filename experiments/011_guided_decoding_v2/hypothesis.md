# 实验 011：Guided Decoding — 任务复杂度 × Enum 规模

## 背景

实验 005/006 发现 xgrammar guided decoding 保证结构正确（100% parse rate）但导致 enum 字段
语义退化（-25pp 到 -75pp）。然而测试集仅 30 条合成 person extraction 任务，单一 schema，
区分度不足。本实验用公开 benchmark 全面评估 guided decoding 的影响。

## 核心问题

**Guided decoding 的语义退化到底发生在哪里？**

- 是 enum 特例，还是普遍现象？
- 推理任务（非提取）是否也受影响？
- enum 数量增多时，bias 是放大还是稀释？
- thinking 模式的价值有多大？

## 假设

**H1（简单 schema 无害假设）**：
在 GSM8K 上（schema 仅含 integer，无 enum），`guided_nothink` 与 `prompt_nothink`
准确率无显著差异。结构约束本身不影响推理，005/006 的退化是 enum-specific 的。

**H2（thinking 价值假设）**：
`prompt_think` 显著优于两个 nothink 条件，尤其在 Hard 题（5+ 步推理）上。
这量化了 guided decoding 的隐性代价——它不仅约束格式，还阻断了 thinking 能力。

**H3（enum 规模假设）**：
Guided decoding 的 enum 准确率惩罚随 enum 数量增大而加剧：
- SST-5（5 类）：轻微退化
- GoEmotions（28 类）：中度退化
- BANKING77（77 类）：严重退化

**H4（难度交互假设）**：
Hard 分类任务上 guided 退化更严重——模型在歧义样本上更需要灵活的 token 分布，
而 xgrammar 的硬 mask 压缩了这种灵活性。

**H5（模型规模假设）**：
14B 模型的 guided 惩罚小于 8B——更强的模型有更集中的 token 分布，
受硬 mask 干扰更小。

## 设计

### Track 1：推理 + 结构化输出（GSM8K）
- 100 题，按推理步数分级（Easy 1-2 步 / Medium 3-4 步 / Hard 5+）
- Schema：`{"answer": integer}`
- 3 条件：prompt_nothink, prompt_think, guided_nothink
- 注：guided_think 不可行（xgrammar 阻断 `<think>` token）

### Track 2：Enum 规模 × 分类难度
- SST-5（5 类，80 题）+ GoEmotions（28 类，80 题）+ BANKING77（77 类，140 题）
- Schema：`{"label": enum[N]}`
- 2 条件：prompt_nothink, guided_nothink
- 难度由 Claude confidence 预分级

### 控制变量
- 所有条件使用**相同 system prompt**，唯一变量是 response_format 开关
- 模型：Qwen3-8B, Qwen3-14B（vLLM, temperature=0.0）

## 预测

如果所有假设成立：
- GSM8K：guided ≈ prompt（±3pp），thinking >> nothink（+15pp+ on Hard）
- SST-5：guided penalty ~5pp
- GoEmotions：guided penalty ~15pp
- BANKING77：guided penalty ~30pp
- 14B 各 penalty 约为 8B 的一半

最有信息量的结果是 H1 + H3 的组合：如果 GSM8K 无退化但 BANKING77 严重退化，
证明 guided decoding 的问题是 enum-specific 的 token 分布扭曲，而非通用的推理干扰。
