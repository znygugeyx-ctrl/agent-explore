# Experiment 011: Guided Decoding — Task Complexity x Enum Scale

## Context

实验 005/006 发现 xgrammar guided decoding 保证结构正确但导致 enum 语义退化（-25pp 到 -75pp）。但测试集太简单（30 条合成 person extraction，单一 schema），无区分度。本实验用公开 benchmark 全面评估 guided decoding 对推理能力和分类准确率的影响。

## 实验目录

```
experiments/011_guided_decoding_v2/
├── __init__.py
├── hypothesis.md          # 假设文档
├── config.yaml            # 所有参数
├── schemas.py             # 各数据集的 JSON Schema 定义
├── prepare_tasks.py       # 数据下载 + 难度分级 + 输出 JSONL
├── run.py                 # 主实验 runner
├── analyze.py             # 跨 track 分析 + 报告生成
├── tasks/                 # prepare_tasks.py 输出
│   ├── gsm8k.jsonl
│   ├── sst5.jsonl
│   ├── goemo.jsonl
│   └── banking77.jsonl
└── results/               # run.py 输出
    ├── gsm8k/
    ├── sst5/
    ├── goemo/
    └── banking77/
```

## 假设

- **H1**: 在 GSM8K（纯 integer schema）上，`guided_nothink` 与 `prompt_nothink` 准确率无显著差异——简单 schema 不含 enum 时，结构约束对语义无害
- **H2**: `prompt_think` 显著优于 `prompt_nothink`，尤其在 Hard 题上——thinking 对多步推理至关重要
- **H3**: Guided decoding 的 enum 准确率惩罚随 enum 数量增大而加剧（5 → 28 → 77）
- **H4**: 难度与 guided 惩罚交互——Hard 分类任务上 guided 退化更严重
- **H5**: 14B 模型的 guided 惩罚小于 8B（更强模型部分抵消约束退化）

## 实验条件

| 条件 | Thinking | 结构约束 | 适用 Track |
|------|---------|---------|-----------|
| `prompt_nothink` | /no_think | Schema in prompt | Track 1 + 2 |
| `prompt_think` | 启用 | Schema in prompt | Track 1 only |
| `guided_nothink` | /no_think | xgrammar 硬 mask | Track 1 + 2 |

注：`guided_think` 不可行——xgrammar 阻断 `<think>` token。

## Track 1: 推理 + 结构化输出（GSM8K）

- **数据集**: `openai/gsm8k` test split（HuggingFace）
- **Schema**: `{"answer": integer}` — 极简，无 enum
- **任务数**: 100（Easy 35 / Medium 35 / Hard 30）
- **难度分级**: 按 ground truth solution 中 `<<>>` 算术标注数量（机械计数，不需要 Claude）
  - Easy: 1-2 步, Medium: 3-4 步, Hard: 5+ 步
- **条件**: 3（prompt_nothink, prompt_think, guided_nothink）
- **模型**: Qwen3-8B, Qwen3-14B
- **验证**: 数值精确匹配（int == int）
- **总调用**: 100 × 3 × 2 = 600

### System Prompt 设计

**所有条件使用相同 prompt**（唯一变量是 response_format 开关）：
```
Solve the math problem. Respond with JSON only: {"answer": <integer>}
```
- `prompt_nothink`: 无 response_format
- `prompt_think`: 无 response_format，不加 /no_think
- `guided_nothink`: 加 response_format（xgrammar 硬 mask）

这样任何准确率差异都归因于 xgrammar logit masking，而非 prompt 差异。

### 答案提取

- `guided_nothink`: 直接 JSON parse → `["answer"]`
- `prompt_nothink`: strip `<think>` → 尝试 JSON parse → fallback regex 提取最后一个数字
- `prompt_think`: 同 prompt_nothink（strip think 后处理）

## Track 2: Enum 规模 × 分类难度

三个数据集，enum 数量递增：

### SST-5（5 类情感）
- **来源**: `SetFit/sst5`（HuggingFace）
- **Labels**: very_negative, negative, neutral, positive, very_positive
- **Schema**: `{"label": {"type": "string", "enum": [5 values]}}`
- **任务数**: 80（Easy 30 / Medium 30 / Hard 20）
- **难度分级**: Claude confidence 预分类

### GoEmotions（28 类情绪）
- **来源**: `google-research-datasets/go_emotions`（HuggingFace）
- **过滤**: 只取单标签样本
- **Labels**: admiration, amusement, anger, ... (28 classes)
- **Schema**: `{"label": {"type": "string", "enum": [28 values]}}`
- **任务数**: 80（Easy 30 / Medium 30 / Hard 20）
- **难度分级**: Claude confidence 预分类

### BANKING77（77 类意图）
- **来源**: `PolyAI/banking77`（HuggingFace）
- **Labels**: 77 个银行意图类别
- **Schema**: `{"label": {"type": "string", "enum": [77 values]}}`
- **任务数**: 140（Easy 50 / Medium 50 / Hard 40）
- **难度分级**: Claude confidence 预分类

### Track 2 共性
- **条件**: 2（prompt_nothink, guided_nothink）
- **模型**: Qwen3-8B, Qwen3-14B
- **验证**: 字符串精确匹配（case-insensitive）
- **总调用**: (80+80+140) × 2 × 2 = 1200

### System Prompt 设计（Track 2）

**所有条件使用相同 prompt**：
```
Classify the text into one of these categories: [enum list].
Respond with JSON only: {"label": "<category>"}
```
- `prompt_nothink`: 无 response_format
- `guided_nothink`: 加 response_format（xgrammar 硬 mask）

唯一变量是 response_format 开关。两者都在 prompt 中列出 enum 值。

## 数据准备 (`prepare_tasks.py`)

### 实现步骤

1. **GSM8K**: 加载 → 计算 `<<>>` 步数分桶 → 平衡采样 100 条 → 输出 JSONL
2. **SST-5 / GoEmotions / BANKING77**:
   - 加载 → (GoEmotions 过滤单标签) → 随机采样候选池(~200-300)
   - 用 Claude (Bedrock Haiku) batch 打 confidence → 按 confidence 分桶
     - Easy: confidence > 0.8
     - Medium: 0.5-0.8
     - Hard: < 0.5
   - 平衡采样目标数量 → 输出 JSONL

### JSONL 格式
```json
{
  "id": "gsm8k_042",
  "dataset": "gsm8k",
  "prompt": "Natalia sold clips to 48 of her friends...",
  "expected_answer": 72,
  "difficulty": "medium",
  "metadata": {"steps": 3}
}
```

### CLI
```bash
python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset gsm8k
python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset sst5
python -m experiments.011_guided_decoding_v2.prepare_tasks --all
```

## 主实验 Runner (`run.py`)

### 架构
- 复用 005 的 direct HTTP 模式（非 agent loop，因为无 tool calling）
- `_build_payload()` 构建 vLLM 请求（根据 condition 决定是否加 response_format）
- `run_condition_with_resume()` 支持断点恢复
- `asyncio.Semaphore(4)` 控制并发
- Observer fire-and-forget 集成

### CLI
```bash
# Pilot（每数据集 10 题，仅 8B）
python -m experiments.011_guided_decoding_v2.run --pilot

# 单 track
python -m experiments.011_guided_decoding_v2.run --track 1 --model Qwen/Qwen3-8B

# 全量
python -m experiments.011_guided_decoding_v2.run --track all

# 断点恢复（相同命令重跑）
python -m experiments.011_guided_decoding_v2.run --track all
```

### 结果文件
```
results/gsm8k/8b_prompt_nothink.json
results/gsm8k/8b_prompt_think.json
results/gsm8k/8b_guided_nothink.json
results/gsm8k/14b_prompt_nothink.json
...
results/banking77/8b_prompt_nothink.json
results/banking77/8b_guided_nothink.json
...
```

## 分析报告 (`analyze.py`)

### 核心输出表

**Table 1: Track 1 GSM8K — 推理 × 约束**

| Model | Condition | Easy | Medium | Hard | Overall | Parse% | Avg Latency |
|-------|-----------|------|--------|------|---------|--------|-------------|

**Table 2: Track 2 Cross-Dataset — Enum 规模 × 约束**

| Dataset | Enum# | prompt Acc | guided Acc | Delta(pp) | Parse%(prompt) |
|---------|-------|------------|------------|-----------|----------------|

**Table 3: 难度交互**

| Dataset | Difficulty | prompt Acc | guided Acc | Delta(pp) |
|---------|------------|------------|------------|-----------|

**Table 4: 模型规模效应**

| Dataset | Model | prompt Acc | guided Acc | Delta(pp) |
|---------|-------|------------|------------|-----------|

## Pilot 计划

### 规模
- GSM8K: 10 题 × 3 条件 × 1 模型(8B) = 30 calls
- SST-5: 10 题 × 2 条件 = 20 calls
- GoEmotions: 10 题 × 2 条件 = 20 calls
- BANKING77: 10 题 × 2 条件 = 20 calls
- **总计: 90 calls，约 5 分钟**

### 验证清单
1. guided_nothink 全部 parse_success = true
2. prompt_nothink parse success > 80%
3. prompt_think 产生 `<think>` 块且答案可提取
4. BANKING77 的 77-enum schema 能被 xgrammar 正常编译
5. 延迟合理（< 30s/call）
6. Observer 正常接收事件

## 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Qwen3-14B 在单 L40S 上 OOM | 无法跑 14B | 已验证可行，无需特殊处理 |
| 77-enum xgrammar 编译慢/出错 | BANKING77 guided 不可用 | Pilot 中优先验证; 备选: 减少 enum 数 |
| prompt_think 答案提取不稳定 | GSM8K prompt_think 准确率虚低 | Strip think → JSON parse → regex fallback 三级提取 |
| GoEmotions 单标签样本不足 | 采样池太小 | 检查过滤后数量; 备选: 放宽为"主标签"而非严格单标签 |
| SST-5 HuggingFace 名称可能变化 | 加载失败 | prepare_tasks.py 中 try 多个名称 |

## 关键复用文件

- `experiments/005_guided_decoding/run.py` — _build_payload(), run_strategy() 模式
- `experiments/007_content_format/prepare_tasks.py` — HuggingFace 数据加载模式
- `core/providers/openai_compat.py` — StreamOptions.extra 传递 response_format
- `bench/verifier.py` — ExactMatchVerifier
- `observer/client.py` — attach_observer

## 实现顺序

1. 创建目录 + hypothesis.md + config.yaml + schemas.py
2. 实现 prepare_tasks.py，逐数据集运行生成 JSONL
3. 实现 run.py，跑 Pilot（90 calls）
4. 验证 Pilot 结果，调整提取逻辑
5. 全量运行 8B（900 calls）
6. 切换模型，全量运行 14B（900 calls）
7. 实现 analyze.py，生成报告
