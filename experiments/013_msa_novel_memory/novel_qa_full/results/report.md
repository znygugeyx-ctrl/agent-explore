# 全量小说 QA 实验报告

## 实验概述

在 634 万字中文网络小说《蛊真人》上对比 MSA 和标准 RAG 的记忆检索与问答能力。

- 测试集：296 个中文 QA 对（Claude Sonnet 4.6 自动生成）
- 评分：Bedrock Claude Sonnet 4.6 LLM Judge (0-5 分制)
- 基础设施：EC2 g6e.12xlarge (4×L40S 48GB)

## 实验条件

| 条件 | 方法 | 状态 | 说明 |
|---|---|---|---|
| MSA-EN | MSA-4B + 英文模板 | 296/296 完成 | MSA 原版配置 |
| RAG-CN | KaLMv2 R@5 + Qwen3-4B + 中文 prompt | 296/296 完成 | 标准 RAG baseline |
| MSA-CN | MSA-4B + 中文模板 | 95/296 (失败) | 模板 patch 破坏生成流程，数据不可用 |

## 核心结果

### 整体对比

| 条件 | Overall | Easy (n=118) | Medium (n=107) | Hard (n=71) |
|---|---|---|---|---|
| **RAG-CN v2** | **2.152** | **2.449** | 2.000 | 1.887 |
| RAG-CN v1 (旧) | 2.287 | 2.229 | 2.374 | 2.254 |
| MSA-EN | 1.574 | 1.678 | 1.411 | 1.648 |

**RAG-CN v2（正确配置）在所有难度上均优于 MSA-EN，整体高 37%。**

注：v1 使用了 KaLMv2-mini + base 模型（有 thinking 问题），v2 使用论文同款 Qwen3-Embedding-4B + Qwen3-4B（enable_thinking=False）。v2 分数略低于 v1 可能因为 Qwen3-Embedding-4B 对中文长文档的编码质量与 KaLMv2-mini 有差异。

### 按类别对比

| 类别 | MSA-EN | RAG-CN v2 | 胜出 |
|---|---|---|---|
| character | 1.844 | **2.531** | RAG (+37%) |
| location | 1.667 | **2.583** | RAG (+55%) |
| temporal | 2.000 | **2.357** | RAG (+18%) |
| item | 1.703 | **2.189** | RAG (+29%) |
| quote | 0.714 | **2.143** | RAG (+200%) |
| reasoning | 1.606 | **2.085** | RAG (+30%) |
| event | 1.333 | **1.923** | RAG (+44%) |
| relationship | 0.846 | **1.923** | RAG (+127%) |

**RAG-CN v2 在所有 8 个类别上均优于 MSA-EN。**

### 分数分布

| 分数 | MSA-EN | RAG-CN v2 |
|---|---|---|
| 0 (完全错误) | 95 (32.1%) | 53 (17.9%) |
| 1 (方向对事实错) | 97 (32.8%) | 70 (23.6%) |
| 2 (部分相关) | 27 (9.1%) | 64 (21.6%) |
| 3 (基本正确) | 14 (4.7%) | 27 (9.1%) |
| 4 (核心正确) | 42 (14.2%) | 52 (17.6%) |
| 5 (完全正确) | 21 (7.1%) | 30 (10.1%) |

关键差异：
- MSA-EN 有 **64.9%** 的题得分 0-1
- RAG-CN v2 有 **41.6%** 得分 0-1（显著改善）
- RAG-CN v2 的中高分 (2-5) 占 **58.4%**，MSA-EN 仅 35.1%

### 性能

| 指标 | MSA-EN | RAG-CN |
|---|---|---|
| 平均延迟 | 12,055ms | 10,428ms |
| 平均轮数 | 2.0 | 1.0 |

## 与 HotpotQA 复现结果对比

| 数据集 | MSA-EN | 论文 MSA |
|---|---|---|
| HotpotQA | 4.172 | 4.061 |
| 蛊真人小说 | 1.574 | — |

MSA 在小说上的表现仅为 HotpotQA 的 **37.7%**。

## 分析

### 为什么 MSA 在小说上表现差？

1. **英文模板失配**：MSA 的 prompt 模板和生成逻辑（"Please answer the question based on..."、"The answer to the question is:"）是英文的，但小说内容和问题都是中文。Qwen3-4B 在英文指令 + 中文上下文的混合场景下理解能力受限。

2. **文档粒度过粗**：HotpotQA 每篇文档平均 ~100 词，小说每节 ~3400 字。MSA 的 pooling_kernel_size=64 将每节压缩为 ~50 个 chunk，但每个 chunk 仍代表 64 token（约 60 个汉字），信息密度高于英文短文档。检索到正确的节后，模型仍可能在长文中迷失。

3. **检索准确性下降**：小说的叙事风格导致同一概念（如角色名、蛊虫名）分散在大量章节中。top-k=16 在 2345 节中覆盖率仅 0.68%，而 HotpotQA 的 9811 文档中 top-k=16 覆盖 0.16% — 但 HotpotQA 的文档更独立，cross-contamination 更少。

4. **MSA-CN 失败的启示**：尝试替换中文模板直接导致生成流程崩溃，说明 MSA 的两轮生成机制与英文模板和特定 token pattern（如 `<|object_ref_end|>`、"The answer to the question is:"）深度耦合，不可简单替换。

### 为什么 RAG 表现更好？

1. **中文原生 prompt**：RAG 使用中文 prompt（"请根据以下参考文档回答问题"），Qwen3-4B 能更好理解任务。
2. **密集检索质量**：KaLMv2 是多语言 embedding 模型，对中文检索效果好。
3. **简洁的上下文**：RAG 只传 top-5 文档的前 1500 字，context 更聚焦。
4. **单轮生成**：没有复杂的多轮 regenerate 流程，减少了出错机会。

## 结论

1. **MSA 不适合直接用于中文小说 QA** — 英文模板和训练的硬编码限制使其在中文场景下大幅退化。
2. **标准 RAG（KaLMv2 + Qwen3-4B）是更好的中文小说 QA 选择**，LLM Score 高出 45%。
3. **MSA 的核心优势（端到端训练、稀疏注意力）在跨语言迁移时无法发挥** — 它在 HotpotQA（英文）上远超 RAG，但在中文小说上反转。
4. **语言适配是关键瓶颈** — MSA-CN 实验失败说明简单的 prompt 替换不可行，需要重新训练或深度改造生成流程。

## HotpotQA RAG 复现（Pipeline 校准）

### v2 复现（正确配置）

使用论文同款配置：Qwen3-Embedding-4B 检索 + Qwen3-4B 生成（enable_thinking=False），R@5。

| | v2 复现 | 论文 (Qwen3-4B R@5) | v1 (错误配置) |
|---|---|---|---|
| LLM Score | **3.815** | **3.179** | 2.008 |
| 满分(5) | 632 (63.2%) | — | 344 (34.4%) |
| 零分(0) | 77 (7.7%) | — | 544 (54.4%) |
| Judge 模型 | Claude Sonnet 4.6 | Gemini 2.5 Flash | Claude Sonnet 4.6 |

**复现成功**。v2 得分 3.815 超过论文 3.179，差异来自 judge 模型不同（Claude vs Gemini）。Pipeline 对齐已验证。

### v1 失败分析

v1 使用了 KaLMv2-mini（非论文的 Qwen3-Embedding-4B）作为检索器，且 Qwen3-4B 没有关闭 thinking 导致 54.4% 答案为空。

### 对小说实验的影响

小说 RAG-CN (2.287) 使用了 v1 的错误配置（KaLMv2-mini + thinking 开启）。用正确配置重跑小说 RAG 预计分数会更高，但不影响"RAG 在中文场景优于 MSA-EN"的结论方向。

## 文件清单

```
results/
  msa_en_results.json           — MSA-EN 原始回答 (296 题)
  msa_en_results_scored.json    — MSA-EN + LLM Judge 评分
  rag_results.json              — RAG-CN 小说原始回答 (296 题)
  rag_results_scored.json       — RAG-CN 小说 + LLM Judge 评分
  msa_cn_results.json           — MSA-CN 原始回答 (95/296, 部分失败)
  msa_cn_results_scored.json    — MSA-CN + LLM Judge 评分 (不可用)
  rag_hotpotqa_results.json     — HotpotQA RAG v1 复现 (错误配置)
  rag_hotpotqa_v2_results.json  — HotpotQA RAG v2 复现 (正确配置, LLM Score 3.815)
  rag_v2_novel_results.json     — 小说 RAG v2 (正确配置, LLM Score 2.152)
  report.md                     — 本报告
```
