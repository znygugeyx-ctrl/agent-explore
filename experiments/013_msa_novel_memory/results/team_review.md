# Experiment 013 Team Review: MSA Novel Memory

> 生成时间：2026-04-27  
> 评审方式：Agent Teams（3 位专项 reviewer + 1 位 leader 协调）  
> 原始会话：`4b631859-ae73-4bca-921d-e467ff44270b`  
> 数据来源：从 subagent JSONL 文件解析，保留原始输出

---

## 团队概述

Leader 将评审工作拆分为三个并行任务，分别分配给独立的 subagent：

1. **methodologist**（`agent-abff5db2a96e390da`）— 评估实验设计的公平性和严谨性
2. **skeptic**（`agent-a02668b297dcc3736`）— 质疑核心结论的可靠性，找出最强反驳
3. **next-steps**（`agent-aa29b62f85a014af9`）— 基于发现提出后续实验建议

Leader 协调语录（主会话文字输出，按时序）：

> "我来组建评审团队。先启动 3 位队友并行阅读文件并独立形成初步结论。"

> "3 位队友已并行启动，分别以 methodologist / skeptic / next-steps 视角独立阅读 013 实验。等待他们的第一轮独立结论。"

> "next-steps 已返回，等待 methodologist 和 skeptic。"

> "methodologist 完成。等待 skeptic。"

三个 subagent 均已返回独立结论后，本次会话结束，leader 未输出最终综合文本。各 subagent 完整输出见下文。

---

## Methodologist：实验设计审核

> Agent: `agent-abff5db2a96e390da` | 模型: claude-opus-4-7  
> 任务：评估实验设计的公平性和严谨性，重点关注 MSA-EN vs RAG-v2 比较的混杂因素

---

# 方法论评估：实验 013 (MSA Novel Memory)

## 审查结论一览

**对"RAG-v2 领先 MSA-EN 37%"的置信度：中偏低（Medium-Low）**

方向性结论（RAG 在中文小说上优于 MSA-EN）**大概率成立**，但 **37% 这个具体幅度**不可作为"记忆架构差距"的量化证据。多条设计缺陷系统性地偏向 RAG 且相互叠加，真实的"架构层差距"（去除语言和 pipeline 混杂后）可能远小于 37%，甚至有可能反号。

---

## 最严重的 5 条设计缺陷（按严重性排序）

### 缺陷 1：语言混杂因素和记忆架构完全不可分 (Critical)

这是整个实验最致命的问题：MSA-EN 使用**英文 prompt 模板 + 英文硬编码检测 token**，RAG-v2 使用**中文 prompt** (`RAG_PROMPT_CN`)。MSA-CN 失败（只拿到 95/296 且 "数据不可用"），意味着**没有任何一个点把"语言"变量控制住**。作者在 report.md: 191-198 和 experiment_report.md: 234 都承认"语言适配是关键瓶颈"——但这同时就等于承认本实验**无法区分 37% 差距有多少来自"MSA 架构 vs RAG 架构"，有多少来自"英文 prompt vs 中文 prompt"**。

- 证据：`novel_qa_full/rag_baseline/rag_generate.py:25-32`（中文 prompt）vs `config.yaml:32` 的 `QWEN3_INSTRUCT_TEMPLATE` 与 report.md:192 描述的英文关键 token。
- 从 experiments/012 的历史看，同款 Qwen 模型 prompt 语言差异就能带来数十 pp 的抖动，单这一项就可能解释大部分差距。

### 缺陷 2：检索单元和上下文预算不匹配 (Critical)

MSA 检索粒度：对整部小说 2,345 节做 chunk-mean-pool（kernel=64），top-k=16 节。
RAG 检索粒度：对同样语料但每 doc 被截断到 **1,500 字**，top-k=5。

这两种"每题可看到的原文量"**天差地别**：MSA 的 top-16 节（理论上 16 × 3,387 ≈ 54K 字）但是被 pooling 有损压缩；RAG 的 top-5 × 1,500 = 7,500 字但保留原文。`rag_generate.py:82` 的硬截断 `d[:1500]` 对中文小说意味着每节只保留开头 44% 左右，**对 Easy/单节题有利**但对 Hard 跨节推理题构成真实瓶颈——然而数据显示 RAG 仍然在 Hard 上领先（1.887 vs 1.648），这说明差距可能还是 prompt 语言和"原文 vs 有损 KV"的综合效应。结论是：**两套检索参数是按各自默认而非对等信息量设的**，不符合"公平对比"的基本要求。d2l_baseline/FINAL_REPORT.md §5.1 已经显式承认"严格同信息量原则被打破"。

### 缺陷 3：Verifier 设计严重不盲评、不复评、存在潜在偏向 (High)

`novel_qa_full/analyze.py:22-37` 的 judge prompt 直接把 `预测答案` 字符串塞给 Claude Sonnet 4.6，`maxTokens=16`、单次打分、无盲评、无复评、无人工校验，也没有按系统轮替顺序。并且：
- **QA 生成**（`generate_qa.py:21`）和 **judge 评分**（`analyze.py:17`）**用的是同一个模型** `us.anthropic.claude-sonnet-4-6`。这会产生"出题人 == 评卷人"的系统偏差：judge 更容易认同与 Claude 自身生成风格一致的答案。由于 RAG 答案更长、更"像 Claude"（中文、完整句、带结构化说明），而 MSA 答案经常是短英文尾巴加中文片段，judge 偏向 RAG 的可能性非常大。
- HotpotQA 复现结果 `3.179 → 3.815` (+20%) 本身就显示 **judge 差异可以轻易制造 10-20 pp 级别分数抖动**（report.md:51 承认）。
- 没有任何多次独立评分的方差报告，0-5 整数离散分制信号噪声比本来就低。

### 缺陷 4：RAG "thinking=off" 与 MSA 实为两个不同生成流程，并非"对等同模型" (High)

虽然 MSA-4B 和 RAG generator 都宣称基于 Qwen3-4B，但：
- RAG 用 `Qwen/Qwen3-4B` 原生模型 + `enable_thinking=False`（report.md:89），走的是单轮 greedy。
- MSA-4B 是 Qwen3-4B-Instruct 经过 curriculum SFT 微调后的权重（hypothesis.md:44 / config.yaml: `MSA-4B`），并且走**两轮生成 + KV 注入**，生成流程被英文 token pattern 深度耦合（report.md:198）。

所以"同 backbone"只是参数量相同，**两者的权重、解码流程、中文能力都不同**。把输出质量差异归因于"记忆架构"而非"微调副作用"，证据是不充分的。一个简单的 sanity control——**Qwen3-4B-Instruct + 同中文 prompt + 完整小说 in-context（如果容量允许）或零上下文 baseline**——完全缺失。

### 缺陷 5：样本量、单次运行、无置信区间 (Medium-High)

- 296 题 **单次运行**，整数 0-5 判分，0.578 的均值差在看似巨大的前提下实际置信区间很宽。粗略估算：假设 σ ≈ 1.7（方差接近均匀分布），两组独立样本 t-test 的 SE ≈ √(1.7²/296 + 1.7²/296) ≈ 0.14。差值 0.578 对应 ~4 σ，看起来 highly significant——**但这忽略了 judge 噪声（同一题复评可能给出不同分数）和 296 题其实来自 ~150 段（每段 2 题，id 强相关），有效独立样本数远小于 296**。
- HotpotQA RAG v1→v2 差距 2.008 → 3.815 （report.md: 110-119）说明**同一数据集、同一方法族、只换 embedding/thinking flag 就能抖动 1.8 分**。这放在小说实验上意味着：0.578 的差距很可能和 RAG 自身配置敏感度是同一数量级。
- 类别级比较进一步受小样本影响：quote (n=7), relationship (n=13), location (n=12) —— `quote RAG +200%` 这种宣称基本是噪声（7 题 × 整数分，SE 约 0.7）。

### 缺陷 6（附加）：测试集偏向语义匹配，而非真正考察记忆架构差异

`generate_qa.py:46-76` 由 Claude 只读**单节**生成 QA（每段 2 题），因此绝大多数题目的 gold 集中在**一节**内。这样的集合**天然偏向 embedding top-k 检索**：只要 embedding 把这一节选进来，RAG 原文直接丢给模型就能答；而 MSA 必须先通过 learned router 把这一节 KV 路由进去、再通过有损 pool KV 生成答案。作者标注的 Hard=71 题"跨段落"，但生成脚本里仍是单节上下文，所谓"跨段"只是 Claude 的类别标签，**未强制验证答案跨节**。也就是说：**benchmark 设计本身就对 RAG 有利**。

---

## 关键结论与置信度定位

| 论断 | 置信度 | 理由 |
|---|---|---|
| RAG-CN 在该 benchmark 上得分高于 MSA-EN | 高 | 分数分布差异明显、全 8 类别胜出、分布差异不是单题噪声 |
| 差距源自"MSA 架构本身不适合中文小说" | **低** | 语言、prompt、生成流程、微调、检索预算、judge 偏向 6 个混杂因素全部叠加 |
| "37%" 是架构差距的量化证据 | **低** | 单次运行、无方差、judge 自指、benchmark 偏向 RAG 检索模式 |
| MSA 在中文长文档上有 limitation（pool 损失细节） | 中 | 论文自身 ablation + 本实验 "quote/relationship" 两类极端失败，方向性一致 |

## 给协作方的关键信号

- **skeptic**：请重点挑战"judge 自指"、"MSA-CN 失败导致语言变量完全不控"、"RAG/MSA 检索预算未对齐"三点，它们足以动摇 37% 的定量意义。
- **next-steps**：最低成本的修复实验是（a）给 MSA 写一个**无微调的 Qwen3-4B-Instruct + 英文 prompt + 中文 prompt** 的 2×2 ICL baseline 或小 context 抽取对照，彻底剥离 "MSA 架构 vs prompt 语言 vs 微调" 三个变量；(b) 换一个非 Claude judge（如 Gemini 或 GPT-4.1）做 10% 复评，给出方差。

---

## Skeptic：质疑最强反驳

> Agent: `agent-a02668b297dcc3736` | 模型: claude-opus-4-7  
> 任务：质疑核心结论可靠性，找出最强反驳论据

---

# 起诉书：对"RAG 较 MSA-EN 在中文小说上领先 37%"的质疑

## 罪状列表（按杀伤力降序）

### 【一级指控】Judge ≈ Generator 同源循环污染（致命）

**事实**：QA 由 Claude Sonnet 4.6 生成（`generate_qa.py:21`），judge 也是同一个 Claude Sonnet 4.6（`analyze.py:17`）。Judge prompt 里直接把"真实答案"（Claude 自己写的）和"预测答案"比对，0–5 分。

Judge 天然偏好"与它自己当初写 gold 时的表述接近的答案"。RAG 答案均长 125 字、gold 均长 88 字、MSA 均长 105 字——RAG 更接近 Claude 风格（分点列举、中文句式完整、复述原文），MSA 输出常为极短事实片段（如"红色，五转"、"十二位"）。在抽样中，甚至有 MSA 答对（"十二位"，与 gold 首字一致）但被判 5 分，而 MSA 答错被判 0 分——判分粒度接近完美，说明 judge 能区分，但**风格相似性在接近答案时放大了 RAG 的分数**。

**反事实**：如果换用 Gemini 2.5 Flash 或 GPT-5 做 judge，差距若从 +0.578 收缩到 < 0.2，则"架构差异"应重新定性为"judge-generator 同源偏置"。**论文 MSA 原文也用 Gemini 不用 Claude**，跨 judge 鲁棒性完全缺失。

---

### 【一级指控】这是"prompt 语言对照实验"，不是"记忆架构对照实验"

**事实**：MSA-EN 用英文 prompt 处理中文语料；RAG-CN 用中文 prompt。MSA-CN 用 monkey patch 打中文模板后，95 题里 mean=0.053——但看输出（`msa_cn_results_scored.json`），MSA-CN 根本没进入生成答案阶段，而是在 round 1 就把用户的 prompt 原样吐回来（`请返回与问题相关的所有文档<|im_end|>`）。这是**补丁工程故障**（两轮 regenerate 逻辑依赖英文 `<|object_ref_end|>` 作为终止符），**不是架构本身的语言能力结论**。

**反事实**：若 MSA 训练时用中文语料或补丁正确实现中文多轮回路，MSA 中文得分大概率显著提升。当前数据**不能区分**以下三个假设：
- H1: MSA 架构对中文语料不行
- H2: MSA 英文模板 + 中文语料的混搭伤害了 Qwen3-4B
- H3: MSA 在小说 narrative 场景下（非百科）检索粒度不够

实验设计把 H1/H2/H3 卷成一团，把结论宣布为 H1。

---

### 【二级指控】效应量中等偏小，单次运行无方差

**事实**：Paired diff mean = 0.578, stdev = 1.910, Cohen's d = **0.302**（小-中效应）。Paired t = 5.20 统计显著，但：
- 296 题样本容易让"小效应"达到 p<0.001
- RAG **仅赢 128 题**，输 68 题，平 100 题。"37% 领先"是一个平均数，背后是 43% 胜率 vs 23% 败率。
- 两条 pipeline 各跑 **1 次**，temperature=0.0 给了一个伪确定性的假象；MSA 的两轮生成内部有采样。**无种子方差**，无法估计该差值在再跑一次时能否保留。

**反事实**：若重跑 3 次后 95% CI 跨过零点，则"领先 37%"不再成立；Cohen's d = 0.3 在任何人类评分系统里都属于"有趣但不可推广"。

---

### 【二级指控】对 MSA 做了"最差公平"配置，对 RAG 反复调参到最佳

**事实**：
- HotpotQA RAG v1 → v2 从 **2.008 → 3.815** 的跳跃证明 RAG 对 embedding 模型、thinking 开关极端敏感。v1 几乎一半答案为空。
- 但小说 MSA **没有经过同等的调参循环**：没试过 top_k_docs ∈ {8, 32}、pooling_kernel_size ∈ {32, 128}、不同 max_rounds、不同温度、top_k×2 召回+rerank。
- MSA-CN 失败后被直接放弃，没有尝试修复 `should_regenerate()` 的中文分支。
- RAG 使用 1500 字/文档 × 5 文档 ≈ **7500 字的文本量喂给 Qwen3-4B**，MSA 的 top-k=16 但是压缩 KV——两者实际传给 generator 的"信息预算"并不对等。

**反事实**：如果 MSA 的 top_k_docs 和 pooling_kernel_size 被同等调参，或者给 MSA 一轮中文 SFT 10 步，分数会如何变化？没有数据。"领先 37%"的 baseline 可能被人为压低。

---

### 【三级指控】v1→v2 切换时的指标樱桃挑选嫌疑

**事实**：`results/report.md:27-31` 显示：
- RAG-CN v1（KaLMv2-mini + thinking on）= **2.287**
- RAG-CN v2（Qwen3-Embedding-4B + thinking off）= **2.152**

v2 **反而更低**。但 MEMORY.md 和 report 里宣传的数字都是 v2 的 2.152，理由是"v2 才对齐论文配置"。问题是：**小说场景下，论文配置并无先验正确性**——KaLMv2-mini 在中文上可能本来就更强。如果 v1 的 2.287 是真实的，那"领先"从 +0.713 / +45% 缩写为 +0.578 / +37%。但如果 v1 是因为错配置意外刷高分（thinking 偶尔泄漏正确答案），又完全可以反过来。**无一次独立 re-run 来消解这个不确定性**。更重要的：报告中 MEMORY.md 同时引用 v1 (2.287) 和 v2 (2.152) 两个数字，叙事上有"哪个支持论点就用哪个"的嫌疑。

---

### 【三级指控】域外混淆：HotpotQA 结论与小说结论的方向反转被夸大

**事实**：HotpotQA 上 MSA 4.172 > RAG 3.815（差 +0.357，Cohen's d 估算 < 0.2）；小说上 RAG 2.152 > MSA 1.574（差 +0.578）。报告把这描述成"跨语言迁移时 MSA 优势消失"。

但 HotpotQA（英文百科 100 词/篇）和蛊真人（中文小说 3400 字/节）**同时改变了**：语言、文档粒度、叙事风格、题型分布（296 题里 48% 是 reasoning，HotpotQA 是 multi-hop factoid）。**4 个变量同时变化**，却把解释锁定在"语言"这一条，是过度归因。

---

## 定性结论

**存疑（lean toward reject）**。

"37% 领先"的统计显著性没有问题，但其**可推广性和因果归因几乎都无法辩护**：
- 效应量只有 d=0.3
- Judge-generator 同源是教科书级 confounder
- MSA-CN 的失败把"架构 vs 工程"彻底混淆
- 单次运行，RAG 已被调参两轮，MSA 未调参

**推翻它最需要的单个实验**：
> 用一个**与 Qwen 家族无关的 judge（推荐 Gemini 2.5 Flash 对齐论文，或换 GPT-5）**重跑评分，同时用一个**正确实现中文多轮回路的 MSA-CN**（工程师花 3 天修 `should_regenerate`）跑一次 296 题。如果此时 RAG 仍领先 >20% 且 Cohen's d > 0.3，结论接受；否则应撤回"RAG 在中文小说上胜过 MSA"的强主张，改为"**英文模板 MSA 败给中文 RAG**"这一弱得多的描述。

次优实验：对 296 题做 **3 次独立 re-run**（即便 T=0，MSA 多轮生成内部有采样非确定性），给出 bootstrap 95% CI。若下界 ≤ 0.2，结论不成立。

**关键文件**：
- `/Users/zny/Documents/LLM/agent-explore/experiments/013_msa_novel_memory/novel_qa_full/generate_qa.py`（第21行，同 judge 模型）
- `/Users/zny/Documents/LLM/agent-explore/experiments/013_msa_novel_memory/novel_qa_full/analyze.py`（第17行 judge；第23-37行 prompt 无长度/风格控制）
- `/Users/zny/Documents/LLM/agent-explore/experiments/013_msa_novel_memory/novel_qa_full/results/msa_cn_results_scored.json`（MSA-CN 是工程失败不是架构失败）
- `/Users/zny/Documents/LLM/agent-explore/experiments/013_msa_novel_memory/novel_qa_full/results/report.md`（第27-31行，v1 2.287 vs v2 2.152 樱桃挑选）

---

## Next-Steps：后续实验建议

> Agent: `agent-aa29b62f85a014af9` | 模型: claude-opus-4-7  
> 任务：基于 013 发现和局限，提出 3 个后续实验建议并编号

---

# Follow-up Experiments for 013 (MSA Novel Memory)

## 014 `msa_pooling_ablation` — Why does MSA lose to RAG on novels?

**Single falsifiable hypothesis**: On Chinese novel QA, MSA's **chunk-mean pooling (kernel=64)** is the dominant cause of quality loss — not the English prompt template, not the backbone LLM. Reducing pooling kernel (64→32→16→1) will recover most of the 0.58pp gap to RAG, while keeping the English template constant.

**Why it matters**: 013 identified three confounded causes for MSA's novel failure (English template, pooling granularity, multi-round decoding), but the MSA-CN patch attempt failed, leaving the decomposition unresolved. The D2L extension showed "LoRA rank=8 capacity bottleneck" dominates D2L; we need the analogous answer for MSA. The 1/3 report literally cites the paper's ablation: disabling raw-text injection costs −37.1%. This experiment isolates the compression-vs-injection axis directly on Chinese.

**Core variables**:
- Controlled: backbone (MSA-4B), English template, top-k=16, same 296-题 novel set, same Claude Sonnet 4.6 judge
- Varied: pooling kernel ∈ {64 (default), 32, 16, 8, 1 (no pooling)}; plus one condition "kernel=64 + raw-text injection enabled" to replicate paper's ablation direction

**Min viable scope**: 296 tasks × 1 model × 5 conditions = 1,480 calls on 1 g6e.12xlarge; ~3h including re-encoding cache per kernel.

**Two outcomes**:
- If kernel=16/1 closes ≥70% of the MSA↔RAG gap → compression is the root cause, prompt-language is secondary. Publishable finding: MSA architecture is information-lossy for narrative text independent of language.
- If kernel reduction barely moves scores → pooling is a red herring and MSA's bottleneck is routing precision or template coupling. Redirects future work toward router training data diversity.

---

## 015 `rag_reranker_scale` — Is RAG's novel advantage stable under stronger configs?

**Single falsifiable hypothesis**: Adding Qwen3-Reranker-4B to the RAG pipeline on the 296-novel set improves LLM Score by ≥0.3pp, and scaling the generator 4B→14B adds another ≥0.3pp — pushing RAG-novel into the 2.8-3.2 range and widening the MSA gap beyond 37%.

**Why it matters**: 013 explicitly flags "RAG未使用 Reranker" as a limitation and suggests Qwen3-14B generator as next step. Before concluding "MSA architecture is wrong for Chinese novels," we must confirm a fair-resource RAG doesn't just win — it wins *more* as compute scales. This tests the monotonicity of the RAG advantage and establishes a credible ceiling. Also probes whether 4B's "low Chinese reasoning ceiling" (013 §3.4) is really the hard limit.

**Core variables**:
- Controlled: same 296 QA, same judge, same FAISS index, top-5 retrieval, thinking=False
- Varied: (reranker: off / Qwen3-Reranker-4B) × (generator: Qwen3-4B / Qwen3-14B / Qwen3-32B) = 6 conditions

**Min viable scope**: 296 × 6 = 1,776 calls. Qwen3-32B needs tensor-parallel=4 on g6e.12xlarge; reranker runs on spare GPU. ~4h. Pilot: 50 tasks × 6 conditions.

**Two outcomes**:
- If both axes deliver ≥0.3pp gains monotonically → RAG's novel-QA lead is robust and grows with compute; MSA needs architectural change (not just tuning) to close. Strong statement for the blog article.
- If gains plateau at 14B or reranker hurts (e.g., shuffles gold chunks out) → the 4B Chinese reasoning ceiling is real, and the MSA gap is about architecture rather than scale. Both RAG and MSA communities should focus on reasoning rather than retrieval.

---

## 016 `memory_hybrid_routing` — Can MSA-route + RAG-inject beat both?

**Single falsifiable hypothesis**: A hybrid pipeline that uses **MSA's learned router to select top-16 sections, then passes the raw text (not compressed KV) of those sections to Qwen3-4B** will beat both pure MSA (1.574) and pure RAG-CN (2.152) on the 296-novel set by ≥0.3pp.

**Why it matters**: 013's report (§四) and the D2L report §6.4 both propose hybrid as future work, but no one has run it. This directly tests the 013 blog's theoretical claim that "MSA learned routing is good; compressed KV injection is bad." It converts a narrative into a measured decomposition of MSA into two independent components, each testable. It's also the cheapest way to ask "is MSA's router actually better than dense retrieval?" — by stripping the compression.

**Core variables**:
- Controlled: backbone Qwen3-4B, thinking=False, same 296 QA, same judge, top-k=16→truncate to 5 × 1,500 chars to match RAG prompt budget
- Varied: retrieval source ∈ {Qwen3-Embedding-4B (RAG), MSA router, MSA router + MMR dedup, Hybrid fusion (RRF of both)}

**Min viable scope**: 296 × 4 conditions ≈ 1,184 calls, ~2h on existing MSA deployment. Pilot: 30 tasks × 4.

**Two outcomes**:
- If MSA-router variant ≥ RAG variant → MSA's learned router is the valuable part; compression is pure cost. Practical takeaway: keep the router as a drop-in retriever, throw away the sparse-attention machinery for small-ish corpora.
- If MSA-router ≤ RAG and hybrid fusion doesn't help → dense-retrieval already captures what the router offers on novels; MSA provides no value at this scale. The paper's advantage lives only in 100M-token regimes we can't test locally.

---

**Prioritization hint for methodologist/skeptic**: 014 is the most *diagnostic* (isolates a claimed root cause from 013); 016 is the most *actionable* (produces a deployable system and doubles as a second decomposition of MSA); 015 is the most *defensive* (closes the RAG-fairness loophole before 013's conclusion can be published as a blog article). If only one runs, 014 — because the 013 blog already implies but doesn't prove the compression hypothesis.

---

## 跨 Agent 讨论与分歧

本次评审三个 subagent 并行独立工作，主会话中未设跨 agent 交叉讨论轮次（leader 仅负责调度）。但从各自独立结论中可以观察到以下对照：

### 高度共识

1. **Judge-generator 同源问题**：methodologist（缺陷3）和 skeptic（一级指控）均将此列为最严重问题，措辞高度一致：Claude 出题 + Claude 打分 = 教科书级 confounder。

2. **MSA-CN 失败性质**：两者均认为是**工程故障**而非架构失败。skeptic 的文件溯源（`msa_cn_results_scored.json` 显示 round-1 把 prompt 原样吐回）为 methodologist 的方向性判断提供了具体证据支持。

3. **37% 差距因果归因脆弱**：两者均认为方向性结论（RAG 领先）大概率成立，但定量幅度无法归因于架构差距。

### 侧重差异

| 维度 | Methodologist | Skeptic |
|---|---|---|
| 检索预算不对等 | Critical — 详细计算了 54K 有损 KV vs 7.5K 原文 | 二级指控 — 简略提及 |
| benchmark 本身偏向 RAG | 列为缺陷6 — 单节 QA 生成天然偏向 embedding | 未单独列出 |
| v1 vs v2 选择问题 | 未单独列出 | 三级指控 — 专门质疑为樱桃挑选嫌疑 |
| 跨域混淆（HotpotQA vs 小说） | 未单独列出 | 三级指控 — 4 个变量同时变化 |

### Next-Steps 与其他 Agent 的呼应

Methodologist 在"给协作方的关键信号"中直接建议 next-steps：(a) 2×2 ICL baseline 剥离三个变量，(b) 换 judge 给出方差。Next-steps 提出的三个实验（014/015/016）与评审发现的对应关系：
- **014** `msa_pooling_ablation` → 对应 methodologist 缺陷2（检索预算/压缩损失）
- **015** `rag_reranker_scale` → 对应 skeptic 二级指控（MSA 未调参 vs RAG 调参两轮）
- **016** `memory_hybrid_routing` → 对应 methodologist 缺陷4 + skeptic 一级B（架构 vs 工程的综合方向）

值得注意的是，next-steps 的 014 选择了"pooling ablation"而非 methodologist 建议的"judge 替换"，优先级排序有分歧——前者诊断根因，后者最快清除最大 confounder。

---

## 综合结论

> 注：本次 leader 会话在 skeptic 返回后结束，未输出明确的综合文本。以下综合结论由本文档整理者根据三位 reviewer 一致意见归纳。

### 核心判定

**实验 013 的方向性发现可信，但定量结论不可直接引用为架构差距证据。**

| 主张 | 判定 | 理由摘要 |
|---|---|---|
| RAG-CN 在 296 题 benchmark 上得分高于 MSA-EN | **成立** | 统计显著（paired t=5.20），全 8 类别胜出，方向清晰 |
| "RAG 领先 37%"作为架构差距量化证据 | **不成立** | Cohen's d=0.302，judge-generator 同源，单次运行无方差 |
| "MSA 架构本身不适合中文叙事文本" | **待定** | 无法区分 MSA 架构 vs 英文模板 vs 工程故障三个假设 |

### 最高优先级修复（无需新实验）

用 Gemini 2.5 Flash（与 MSA 论文原文对齐）对现有 296 道题的所有答案重新打分。若 RAG-MSA 差距从 0.578 收缩到 < 0.2，原结论需撤回强主张；若差距保持 > 0.4 且方向不变，则 judge 偏置不是主因。

### 后续实验优先级（来自 next-steps agent）

1. **014** `msa_pooling_ablation` — 最诊断性，直接测试 pooling 压缩是否是根因（1,480 calls, ~3h）
2. **016** `memory_hybrid_routing` — 最可行，用现有部署资产，测试"MSA router 有价值，KV 压缩是累赘"假说（1,184 calls, ~2h）
3. **015** `rag_reranker_scale` — 最防御性，验证 RAG 优势随算力单调增长（1,776 calls, ~4h）

### 博客/报告修订建议

- 将"RAG 胜过 MSA"改为"**英文模板 MSA 在中文叙事 QA 上低于中文 RAG**"
- 明确标注："37% 差距包含 prompt 语言差异和 judge-generator 同源偏置，架构层净差距未知"
- 保留 HotpotQA 复现数字（MSA 4.172 > RAG 3.815）作为 MSA 在原始英文场景下的上界

---

*三位 agent 独立阅读实验全部文件后输出，未经跨 agent 互相传递意见。所有引用的代码位置和分数均可在 `experiments/013_msa_novel_memory/` 原始文件中核验。*
