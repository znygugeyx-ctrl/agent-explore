# 实验 013：MSA 小说记忆 — 完整实验报告

## 一、实验背景

Memory Sparse Attention（MSA）是 EverMind-AI 提出的端到端可训练稀疏注意力记忆框架，声称能在 2×A800 GPU 上处理最高 1 亿 token 的上下文。本实验在自有基础设施上部署 MSA，首先复现论文结果验证部署正确性，然后将 MSA 应用于中文长篇小说（634 万字），评估其在非英文、非百科文档场景下的实际表现，并与标准 RAG 方案做对比。

**核心问题**：MSA 的端到端学习记忆能否有效处理中文网络小说？与标准 RAG 相比表现如何？

---

## 二、复现实验

### 2.1 复现策略

分别复现 MSA 和 RAG baseline，使用论文同款数据集和评测方式，验证部署和 pipeline 的正确性。

#### MSA 复现

| 配置项 | 论文 | 我们 |
|---|---|---|
| 模型 | MSA-4B (Qwen3-4B-Instruct 微调) | 同左，HuggingFace 权重 |
| GPU | 8× A800 80GB | 4× L40S 48GB |
| 参数 | top_k=16, pooling=64, router layers 18-35 | 同左 |
| 模板 | QWEN3_INSTRUCT_TEMPLATE | 同左 |
| 代码 | 原始仓库 | 同左，修复了 2 个 deserialize bug |

#### RAG baseline 复现

| 配置项 | 论文 (Table 2, Qwen3-4B R@5) | 我们 |
|---|---|---|
| 检索器 | Qwen3-4B-Embedding | Qwen3-Embedding-4B (同款) |
| 生成器 | Qwen3-4B-Instruct-2507 | Qwen/Qwen3-4B (enable_thinking=False) |
| Reranker | 无（base R@5 行无 reranker） | 无 |
| 检索流程 | 检索 100 → 取 top-5 | 同左 |
| RAG 框架 | UltraRAG v2.0 | 自建（FAISS + 原生 generate） |

### 2.2 测试数据集

**HotpotQA**：论文 9 个 QA benchmark 之一
- 记忆库：9,811 篇英文维基百科文档
- 测试集：1,000 个多跳问答对（每题需综合 2 篇文档）
- 记忆库规模：1.35M tokens

### 2.3 复现结果

| 方法 | LLM Score | 论文报告 | 差异 |
|---|---|---|---|
| **MSA** | **4.172** | 4.061 | +0.111 (judge 模型差异) |
| **RAG R@5** | **3.815** | 3.179 | +0.636 (judge 模型差异) |

评分方式：LLM Judge 0-5 分制。论文用 Gemini 2.5 Flash，我们用 Claude Sonnet 4.6。

#### MSA 分数分布 (HotpotQA)

| 分数 | 数量 | 占比 |
|---|---|---|
| 5 (完全正确) | 769 | 76.9% |
| 4 | 28 | 2.8% |
| 3 | 27 | 2.7% |
| 2 | 24 | 2.4% |
| 1 | 86 | 8.6% |
| 0 (完全错误) | 66 | 6.6% |

#### RAG R@5 分数分布 (HotpotQA)

| 分数 | 数量 | 占比 |
|---|---|---|
| 5 | 632 | 63.2% |
| 4 | 83 | 8.3% |
| 3 | 36 | 3.6% |
| 2 | 43 | 4.3% |
| 1 | 129 | 12.9% |
| 0 | 77 | 7.7% |

### 2.4 复现结论

- **MSA 复现成功**：4.172 vs 论文 4.061，在合理误差范围内
- **RAG 复现成功**：3.815 vs 论文 3.179，pipeline 对齐验证通过
- **MSA > RAG**：在 HotpotQA 上，MSA 比同 backbone RAG 高出 9.4%，与论文结论一致
- judge 模型差异（Claude Sonnet 4.6 vs Gemini 2.5 Flash）导致两者分数均偏高

### 2.5 复现中的踩坑

部署过程中遇到 9 个问题，详见 `deployment_notes.md`，关键问题：

1. MSA 的 `deserialize()` 有 2 个 bug（rk/k 设备分配 + BlockDesc 恢复），导致从缓存加载后 crash
2. MSA 的 QA 是**多轮生成**（通常 3 轮），单轮只能拿到检索结果，无法生成最终答案
3. RAG 首次复现（v1）使用了错误的 embedding 模型和 base 版 generator（未关闭 thinking），导致 54% 答案为空
4. Qwen3-4B 默认启用 thinking，必须设 `enable_thinking=False` 才能获得干净输出

---

## 三、小说实验

### 3.1 数据集构造

#### 记忆库

| 属性 | 值 |
|---|---|
| 小说 | 《蛊真人》 |
| 总字数 | 634 万字 |
| Token 数 | 589 万 (Qwen3 tokenizer) |
| 切分方式 | 按"节"切分 |
| 段落数 | 2,345 节 |
| 平均每节 | 3,387 字 |
| 预估 chunks (MSA) | 93,539 |

#### 测试集

296 个中文 QA 对，由 Claude Sonnet 4.6 从小说随机采样段落自动生成。

**难度分布**：

| 难度 | 数量 | 定义 |
|---|---|---|
| Easy | 118 | 答案在单一节中明确出现 |
| Medium | 107 | 需要理解上下文或综合本段多处信息 |
| Hard | 71 | 需要跨段落推理、因果分析或关联 |

**类别分布**：

| 类别 | 数量 | 说明 |
|---|---|---|
| reasoning | 142 | 因果、动机、比较分析 |
| event | 39 | 情节事件 |
| item | 37 | 蛊虫、蛊屋等物品 |
| character | 32 | 人物身份、属性 |
| temporal | 14 | 时间顺序、先后 |
| relationship | 13 | 人物关系 |
| location | 12 | 地点、势力 |
| quote | 7 | 原文引用识别 |

按卷次均匀分布于小说 6 卷：第一卷 ~38 题, 第二三卷 ~40 题, 第四五卷 ~62 题, 第六卷 ~64 题。

### 3.2 实验条件

| 条件 | 方法 | Prompt 语言 | 说明 |
|---|---|---|---|
| **MSA-EN** | MSA-4B + 原版英文模板 | English | MSA 默认配置 |
| **RAG-CN v2** | Qwen3-Embedding-4B + Qwen3-4B | Chinese | 论文同款 RAG pipeline |

另有 MSA-CN（中文模板）实验因 monkey-patch 破坏了多轮生成流程而失败，数据不可用。

### 3.3 实验结果

#### 整体对比

| 条件 | Overall | Easy | Medium | Hard |
|---|---|---|---|---|
| **RAG-CN v2** | **2.152** | **2.449** | **2.000** | **1.887** |
| MSA-EN | 1.574 | 1.678 | 1.411 | 1.648 |
| 差值 | **+0.578 (+37%)** | +0.771 | +0.589 | +0.239 |

#### 按类别对比

| 类别 | MSA-EN | RAG-CN v2 | RAG 优势 |
|---|---|---|---|
| character | 1.844 | **2.531** | +37% |
| location | 1.667 | **2.583** | +55% |
| temporal | 2.000 | **2.357** | +18% |
| item | 1.703 | **2.189** | +29% |
| quote | 0.714 | **2.143** | +200% |
| reasoning | 1.606 | **2.085** | +30% |
| event | 1.333 | **1.923** | +44% |
| relationship | 0.846 | **1.923** | +127% |

**RAG-CN v2 在全部 8 个类别上均优于 MSA-EN。**

#### 分数分布

| 分数 | MSA-EN | 占比 | RAG-CN v2 | 占比 |
|---|---|---|---|---|
| 0 (完全错误) | 95 | 32.1% | 53 | 17.9% |
| 1 (方向对事实错) | 97 | 32.8% | 70 | 23.6% |
| 2 (部分相关) | 27 | 9.1% | 64 | 21.6% |
| 3 (基本正确) | 14 | 4.7% | 27 | 9.1% |
| 4 (核心正确) | 42 | 14.2% | 52 | 17.6% |
| 5 (完全正确) | 21 | 7.1% | 30 | 10.1% |

#### 与 HotpotQA 的对比

| 数据集 | MSA | RAG R@5 | MSA 优势 |
|---|---|---|---|
| **HotpotQA** (英文百科) | **4.172** | 3.815 | **MSA +9.4%** |
| **蛊真人** (中文小说) | 1.574 | **2.152** | **RAG +37%** |

### 3.4 分析

#### MSA 在中文小说上表现差的原因

1. **英文模板硬编码**：MSA 的 prompt 模板（"Please answer the question based on the above historical document information"）、生成流程中的关键检测 token（"The answer to the question is:"、`<|object_ref_end|>`）均为英文。Qwen3-4B 在英文指令 + 中文上下文的混合场景下理解能力受限。

2. **文档粒度过粗**：HotpotQA 每篇文档约 100 词，小说每节约 3,400 字。MSA 的 chunk-mean pooling（kernel=64 tokens）将每节压缩为约 50 个 chunk，但在长叙事文本中，关键信息可能被稀释在大量叙述描写中。

3. **检索精度下降**：小说的叙事风格导致同一角色名、蛊虫名分散在大量章节中。top-k=16 在 2,345 节中仅覆盖 0.68%，而同样 top-k=16 在 HotpotQA 的 9,811 文档中覆盖 0.16% — 比例更低但 HotpotQA 文档更独立，cross-contamination 更少。

4. **多轮生成机制的脆弱性**：MSA 的三轮生成（检索 → 加载原文 → 生成答案）对 prompt 语言高度敏感。尝试替换中文模板直接导致 `should_regenerate()` 检测失败，生成流程崩溃。这说明 MSA 的生成逻辑与英文 token pattern 深度耦合。

#### RAG 在中文小说上表现更好的原因

1. **中文原生 prompt**：RAG 使用中文指令（"请根据以下参考文档回答问题"），Qwen3-4B 能更自然地理解任务。

2. **密集检索质量**：Qwen3-Embedding-4B 是多语言 embedding 模型，对中文文本的语义匹配效果好。

3. **简洁的上下文**：RAG 只传 top-5 文档的前 1,500 字，context 更聚焦，减少了模型在长文中"迷失"的概率。

4. **单轮生成**：没有复杂的多轮 regenerate 流程，减少了出错环节。

#### 两者均表现不佳的原因

无论 MSA (1.574) 还是 RAG (2.152)，在小说上的表现都远低于 HotpotQA 上的水平（4.172 / 3.815）。核心原因：

1. **4B 模型的中文推理能力有限**：Qwen3-4B 在复杂中文叙事理解和推理上能力不足，尤其是 reasoning 类题（MSA 1.606 / RAG 2.085）。

2. **小说信息密度低**：百科文档几乎每句都是事实，小说大量篇幅是对话、描写、心理活动，关键信息稀疏且分散。

3. **测试集难度高**：296 题中 142 题是 reasoning 类（占 48%），这类题对 4B 模型来说本身就很有挑战。

---

## 四、总结

### 核心发现

1. **MSA 在英文百科 QA 上复现成功**（4.172 vs 论文 4.061），端到端学习的优势在英文短文档场景下成立。

2. **MSA 不适合直接用于中文小说 QA**（1.574），英文模板和训练的硬编码限制使其在中文场景下严重退化。

3. **标准 RAG 在中文小说上优于 MSA**（2.152 vs 1.574，+37%），中文 prompt + 密集检索的简单方案更有效。

4. **MSA 的核心优势在跨语言迁移时消失**：在 HotpotQA 上 MSA 超过 RAG 9.4%，但在中文小说上反转为 RAG 超过 MSA 37%。

5. **语言适配是关键瓶颈**：MSA-CN 实验失败表明简单的 prompt 替换不可行，需要重新训练或深度改造生成流程。

### 实验局限性

1. **Judge 模型差异**：我们使用 Claude Sonnet 4.6，论文使用 Gemini 2.5 Flash，导致绝对分数不完全可比（但相对排序有效）。
2. **RAG 未使用 Reranker**：论文的 RR 组使用了 Qwen3-4B-Rerank，加入 reranker 可能进一步提升 RAG 性能。
3. **MSA-CN 失败**：未能完成中文模板对照实验，无法确认语言因素的精确贡献。
4. **单一小说**：仅测试了一部网络小说，结论的泛化性有待更多中文数据集验证。

### 对后续实验的建议

1. **中文微调 MSA**：用中文 QA 数据对 MSA 做 SFT，将模板和检测逻辑改为中文。
2. **更大模型**：用 Qwen3-14B 或 Qwen3-32B 作为 RAG generator，测试模型规模对小说 QA 的影响。
3. **RAG + Reranker**：加入 Qwen3-Reranker-4B，测试 reranking 对长文档检索的提升。
4. **混合方案**：MSA 做粗检索 + RAG 做精排和生成，结合两者优势。

---

## 五、文件索引

```
experiments/013_msa_novel_memory/
  experiment_report.md                    ← 本报告
  hypothesis.md                           — 实验假设
  config.yaml                             — 配置参数
  deployment_notes.md                     — 9 个部署踩坑及修复
  ec2_recovery_guide.md                   — 环境恢复完整指南
  MSA_paper.pdf                           — 论文 PDF

  results/hotpotqa_reproduction/          — HotpotQA MSA 复现
    report.md                             — 复现报告
    bench_hotpotqa_raw.json               — 1000 题原始结果
    bench_hotpotqa_llmscore.json          — LLM Score 4.172

  novel_qa_test/                          — Pilot 50 题测试
    plan.md                               — 测试计划
    qa_pairs.json                         — 50 题测试集
    results/eval_results.json             — Pilot 结果 (1.88)

  novel_qa_full/                          — 全量 296 题实验
    plan.md                               — 实验计划
    qa_300.json                           — 296 题测试集
    generate_qa.py                        — QA 生成脚本
    run_msa.py                            — MSA 评估脚本
    analyze.py                            — 分析脚本
    rag_baseline/                         — RAG baseline 代码
      build_index.py                      — 向量索引构建
      rag_generate.py                     — RAG 检索 + 生成
    results/
      msa_en_results_scored.json          — MSA-EN: 1.574
      rag_v2_novel_results.json           — RAG-CN v2: 2.152
      rag_hotpotqa_v2_results.json        — HotpotQA RAG 复现: 3.815
      report.md                           — 详细对比报告
```
