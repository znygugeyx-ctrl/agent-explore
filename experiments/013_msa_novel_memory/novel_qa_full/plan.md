# 全量小说 QA 实验：MSA vs RAG

## 目标

在 634 万字中文网络小说《蛊真人》上，对比 MSA（Memory Sparse Attention）和标准 RAG 的记忆检索与问答能力，同时测试中英文 prompt 对 MSA 的影响。

## 实验条件

| 条件 | 方法 | Prompt | 说明 |
|---|---|---|---|
| **MSA-EN** | MSA-4B，原版英文模板 | English | 当前默认配置 |
| **MSA-CN** | MSA-4B，中文模板 | Chinese | Prompt 对照 |
| **RAG-CN** | KaLMv2 检索 + Qwen3-4B 生成 | Chinese | RAG baseline |

额外：在 HotpotQA 上复现 RAG baseline，验证 pipeline 对齐论文 Table 1。

## 测试集

300 个中文 QA 对，由 Claude Sonnet 4.6 从小说随机采样段落生成。

| 难度 | 数量 | 定义 |
|---|---|---|
| Easy | ~120 | 单节事实检索 |
| Medium | ~100 | 跨 2-3 节综合 |
| Hard | ~80 | 跨卷推理/因果/比较 |

8 个题型类别：character, item, event, location, relationship, reasoning, temporal, quote

## 基础设施

- EC2 g6e.12xlarge: 4×L40S 48GB, 384GB RAM
- MSA-4B 模型（Qwen3-4B-Instruct 微调）
- KaLMv2 embedding: `HIT-TMG/KaLM-embedding-multilingual-mini-instruct-v2`
- LLM Judge: Bedrock Claude Sonnet 4.6

## RAG Baseline 设计

论文 Table 1 的 RAG baseline 使用 KaLMv2 密集检索 + Qwen3-4B 生成器。我们复现 R@5 配置：

1. KaLMv2 编码语料库 → FAISS 索引
2. KaLMv2 编码查询 → ANN 检索 top-5
3. 拼接 top-5 段落 + 问题 → Qwen3-4B-Instruct 生成答案

**HotpotQA 复现目标**: 论文 Qwen3-4B R@5 = 3.179

## 评估方法

- LLM Judge 0-5 分制（与 HotpotQA 复现一致）
- 中文评分 prompt
- 多维度分析：整体、按难度、按类别、按卷次、MSA vs RAG 对比

## 预期结果

1. MSA-CN > MSA-EN（中文模板更适配中文内容）
2. MSA 整体分数低于 HotpotQA（小说比百科更难）
3. RAG-CN 在 Easy 题上可能接近或超过 MSA（短文本检索是 RAG 强项）
4. MSA 在 Hard/reasoning 题上可能优于 RAG（端到端学习的优势）

## 执行顺序

1. 生成 300 题测试集 (`generate_qa.py`)
2. HotpotQA RAG 复现 (验证 pipeline)
3. 小说 RAG baseline (`run_rag.py`)
4. MSA-EN 评估 (`run_msa_en.py`)
5. MSA-CN 评估 (`run_msa_cn.py`)
6. LLM Judge 评分
7. 分析报告 (`analyze.py`)
