# 013-1: Doc-to-LoRA 参数化记忆对比实验（v3 — 信息量控制 + 梯度）

## Context

实验 013 已完成 MSA 和 RAG 在各自最佳条件下的对比。现引入 D2L（参数化记忆）作为第三种范式，并重新设计实验框架：**严格控制信息输入量，只比较记忆机制本身。**

三种范式 × 相同信息量：
| 方案 | 处理 context pool 的方式 | 回答时上下文成本 |
|------|------------------------|----------------|
| **ICL** | 直接塞入 prompt | 全量（~2K/4K/8K tokens） |
| **MSA** | 编码到 KV cache + router | ~0（路由选取 top-k chunks） |
| **D2L** | 编码为 LoRA 权重 | 0（已内化为参数） |

**实验本质**：在 2K/4K/8K 三档信息预算下，三种记忆范式的保真度对比。ICL 是信息零损失上限，MSA 和 D2L 都有压缩损失。

---

## 决策记录

- **Checkpoint**: Qwen3-4B（主实验）+ Gemma-2-2B-IT（sanity check）
- **Sanity check**: 先在 D2L 论文 benchmark 上复现
- **MSA 处理**: 也限制到相同的 context pool（非全书编码）
- **信息量**: 2K / 4K / 8K 三档梯度

---

## 测试集构造

### 核心原则

每题有一个 **context pool**（精确控制 token 数），三种方案接收 **完全相同的 pool**。每题构造 3 个版本（2K/4K/8K），通过逐步添加文档/section 实现：

```
pool_2K ⊂ pool_4K ⊂ pool_8K  （嵌套关系，保证可比性）
```

### HotpotQA 测试集

**构造方法**:
1. 从 1,000 题中筛选：两个 gold docs 总 token ≤ 1.5K（确保 2K 档能装下）
2. 对每题：
   - **pool_2K**: 2 gold docs + 少量 distractors → ~2,048 tokens
   - **pool_4K**: pool_2K + 更多 distractors → ~4,096 tokens
   - **pool_8K**: pool_4K + 更多 distractors → ~8,192 tokens
3. Pool 内文档随机排序（消除位置偏差）
4. 采样 **200 题**（统计上 5 分制标准误 ±0.1，可区分 ≥0.3 分差异）

**token 预算分配（HotpotQA，avg ~116 tokens/doc）**:
| 档位 | 总 tokens | gold docs | distractors | 总 docs |
|------|----------|-----------|-------------|---------|
| 2K | ~2,048 | 2 (~232) | ~15 (~1,800) | ~17 |
| 4K | ~4,096 | 2 | ~33 (~3,850) | ~35 |
| 8K | ~8,192 | 2 | ~67 (~7,750) | ~69 |

### 小说 QA 测试集（仅 8K 一档，重新构造）

**核心要求**: 所有难度（含 hard）的 gold context 都必须在 8K token 预算内。需要**重新构造数据集**而非复用现有 296 题。

**构造方法**:
1. 选取 context window：从小说中选取连续 sections 拼接到 ~8K tokens（约 2-3 个连续 sections）
2. 基于 context window 生成 QA：用 Claude 从这个固定 window 内生成三种难度的题目
   - **Easy**: 答案在 window 内某一段落直接出现
   - **Medium**: 需理解 window 内多处信息综合推断
   - **Hard**: 需要跨 section 推理、因果关系或关系分析（但所需信息**必须全在 window 内**）
3. 每个 window 生成 3-5 题（覆盖不同难度和类别）

**数据集规模目标**: ~150-200 题（50 windows × 3-4 题/window）
| 难度 | 目标数量 | 说明 |
|------|---------|------|
| Easy | ~60 | 单点事实检索 |
| Medium | ~60 | 多处信息综合 |
| Hard | ~60 | 跨 section 推理，gold context 在 window 内 |

**Window 采样策略**:
- 从 2,345 sections 中均匀采样 ~50 个起始点
- 从起始点开始拼接连续 sections 直到 ~8K tokens
- 用 Qwen3-4B tokenizer 精确计量

**QA 生成 prompt 设计**（复用 `generate_qa.py` 的思路，增加约束）:
- 输入: 完整 8K context window
- 要求: 生成的问题**必须且仅需** window 内信息即可回答
- Hard 题额外要求: 必须涉及 window 内至少 2 个 section 的信息交叉

**关键区别 vs 现有 296 题**: 现有题目基于单 section 生成，hard 题可能需要小说其他部分的知识。新数据集确保 gold context 完全在 8K 内，使三种方案的对比公平。

---

## 实验矩阵

### HotpotQA

| 方案 | 模型 | 2K | 4K | 8K | 总 runs |
|------|------|----|----|----|---------| 
| ICL | Qwen3-4B | 200 | 200 | 200 | 600 |
| MSA | Qwen3-4B (MSA-4B) | 200 | 200 | 200 | 600 |
| D2L | Qwen3-4B (D2L-4B) | 200 | 200 | 200 | 600 |
| D2L | Gemma-2-2B (sanity) | 200 | 200 | 200 | 600 |
| **Total** | | | | | **2,400** |

### 小说 QA（仅 8K 一档）

| 方案 | 模型 | 8K | 总 runs |
|------|------|----|---------|
| ICL | Qwen3-4B | ~180 | 180 |
| MSA | Qwen3-4B (MSA-4B) | ~180 | 180 |
| D2L | Qwen3-4B (D2L-4B) | ~180 | 180 |
| D2L | Gemma-2-2B (sanity) | ~180 | 180 |
| **Total** | | | **~720** |

（题数取决于最终生成的数据集规模，目标 ~150-200 题）

**总评测调用**: ~3,120 次推理 + ~3,120 次 LLM Judge 评分

---

## 实现步骤

### Step 0: 环境搭建
- EC2 g6e.2xlarge (1× L40S)
- Clone doc-to-lora, 下载 checkpoints（Qwen3-4B + Gemma-2-2B）
- 安装依赖（flash-attn wheel 需 CUDA 12.x + Python 3.10）
- 验证基本推理: `model.internalize(doc) → model.generate(q) → model.reset()`

### Step 1: 论文 Benchmark 复现
- 用 D2L 自带 eval 脚本跑 SQuAD + DROP
- 两个 checkpoint 都跑，对比论文 F1 数字
- **通过标准**: ±2pp 内算复现成功
- **产出**: `results/sanity_check_{model}_{bench}.json`

### Step 2: 构造测试集
- **HotpotQA**: 下载语料库 → 筛选 200 题 → 构造 2K/4K/8K 嵌套 pools
- **小说（重新构造）**: 加载 corpus pkl → 采样 ~50 个 8K context windows → 用 Claude 生成 ~180 题 QA（确保 hard 题的 gold context 全在 window 内）
- Tokenizer: 用 Qwen3-4B tokenizer 精确计算 token 数（非估算）
- **产出**: `data/hotpotqa_pools.json`, `data/novel_8k_pools.json`

### Step 3: Pilot（每方案 5 题 × 3 档 = 45 次推理）
- 三种方案各跑 pilot，人工检查输出质量
- 重点检查: D2L 中文输出是否正常、MSA 小 pool 编码是否工作、ICL prompt 格式

### Step 4: HotpotQA Full Run
- D2L (两模型) × 3 档 × 200 题
- MSA × 3 档 × 200 题
- ICL × 3 档 × 200 题
- LLM Judge 评分

### Step 5: 小说 QA Full Run
- ~180 题 × 8K × 3 方案 × (1+1 模型)
- 按难度/类别分层评分

### Step 6: 分析报告
- HotpotQA: 三种范式 × 三档信息量 → 信息量 vs 保真度曲线
- 小说: 三种范式 × 8K × 三种难度
- 按难度/类别分层分析
- 中英文差异分析
- 延迟对比

---

## 文件结构

```
experiments/013_msa_novel_memory/
  d2l_baseline/
    setup.sh                    # 环境搭建 + checkpoint 下载
    d2l_wrapper.py              # D2L 推理封装 (internalize → generate → reset)
    build_hotpotqa_pool.py      # HotpotQA 2K/4K/8K context pool 构造
    build_novel_pool.py         # 小说 8K context window 采样
    generate_novel_qa.py        # 基于 8K window 生成 QA 数据集
    run_sanity.py               # 论文 benchmark 复现
    run_d2l.py                  # D2L evaluation runner
    run_msa_8k.py               # MSA 在受限 pool 上的 evaluation
    run_icl.py                  # ICL baseline (直接 prompt)
    analyze.py                  # 统一评分 + 报告生成
    data/
      hotpotqa_pools.json       # {question, answer, gold_ids, pools: {2k, 4k, 8k}}
      novel_8k_pools.json      # {question, answer, difficulty, category, context_window, window_sections, total_tokens}
    results/
      sanity_check_*.json
      hotpotqa_{method}_{model}_{size}.json
      novel_{method}_{model}_{size}.json
      report.md
```

**复用的现有代码**:
- `novel_qa_full/analyze.py` → LLM Judge prompt + scoring 逻辑
- `results/hotpotqa_reproduction/bench_hotpotqa_raw.json` → gold doc IDs + doc 内容
- `novel_qa_full/qa_300.json` → 小说 QA 数据集
- 小说 corpus `.pkl`（EC2 上）→ section 内容

---

## MSA 在受限 pool 下的实现方案

MSA 正常流程是编码大规模语料。在 8K pool 下需要调整：

**方案**: 对每题的 context pool，将其作为"迷你语料库"喂给 MSA engine：
1. 将 pool 中的 docs/sections 作为 memory corpus
2. 调用 MSA encode（每题独立编码）
3. 调用 MSA ask 获取答案
4. 清空 memory，下一题

**注意**: 
- 编码 8K 文本应极快（全书 5.89M tokens 需 150s，8K 应 <1s）
- 需确认 MSA API 支持动态更换 corpus（可能需要重启 engine 或支持 clear/reload）
- `pooling_kernel_size=64` 在小 pool 下效果可能不同（8K ≈ 128 chunks → router 从 128 中选 16）

---

## 验证方法

1. **Step 1**: SQuAD/DROP F1 与论文数字对比（±2pp）
2. **Step 3**: Pilot 人工检查 — D2L 输出可读、MSA 小 pool 正常工作、ICL 格式正确
3. **Token 精度**: 验证 pool 构造的 token 数误差 <5%（用 Qwen3-4B tokenizer 精确计量）
4. **嵌套一致性**: 验证 pool_2K ⊂ pool_4K ⊂ pool_8K 的包含关系
5. **评分一致性**: 同一个 judge model + prompt，与已有 013 结果可比
