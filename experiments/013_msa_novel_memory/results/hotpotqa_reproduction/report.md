# HotpotQA Benchmark 复现报告

## 目标

在自有基础设施上复现 MSA (Memory Sparse Attention) 论文在 HotpotQA 数据集上的结果，验证部署正确性。

## 论文参考

MSA 论文 Table 1 报告 HotpotQA 上 MSA (adaptive) 的 LLM Judge 评分为 **4.061**（0-5 分制），使用 Gemini 2.5 Flash 作为 judge 模型。

## 基础设施

| 配置 | 论文 | 本次复现 |
|---|---|---|
| GPU | 8× A800 80GB | 4× L40S 48GB |
| 系统内存 | 未明确 | 384 GB |
| CUDA | 未明确 | 12.8 |
| 模型 | MSA-4B (Qwen3-4B-Instruct) | 同左，HuggingFace 权重 `EverMind-AI/MSA-4B` |
| 框架 | 原始代码 | 同左，`github.com/EverMind-AI/MSA` |

### MSA 推理参数

```yaml
template: QWEN3_INSTRUCT_TEMPLATE
temperature: 0.0
top_p: 0.9
max_generate_tokens: 2048
block_size: 2048
max_chunk_per_block: 16384
max_batch_size: 8  # per GPU (论文用16，我们4卡调小)
doc_top_k: 16
pooling_kernel_size: 64
router_layer_idx: "18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35"
qa_mode: true
```

## 数据集

HotpotQA benchmark，从 HuggingFace 自动下载 (`EverMind-AI/MSA-RAG-BENCHMARKS`)：
- **记忆库**: 9,811 篇英文维基百科文档 (`mdata_hotpotqa.pkl`)
- **测试集**: 1,000 个多跳问答对 (`qdata_hotpotqa.pkl`)
- 每个问题需要从 2 篇文档中综合信息才能回答

## 执行过程

### 1. 环境搭建 (EC2 g6e.12xlarge)

```bash
# AMI: Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04)
# 安装 miniconda + Python 3.12 + flash-attn 2.7.4 + MSA 依赖
conda create -n msa python=3.12 -y
pip install -r requirements.txt
pip install flash-attn==2.7.4.post1 --no-build-isolation
huggingface-cli download EverMind-AI/MSA-4B --local-dir ckpt/MSA-4B
```

### 2. Benchmark 执行

```bash
export CUDA_VISIBLE_DEVICES=0,1,2,3
export MASTER_PORT=29509
python -u src/app/benchmark.py \
    --benchmark hotpotqa \
    --model_path ckpt/MSA-4B \
    --top_p 0.9 --temperature 0.0 \
    --max_length 2048 \
    --template QWEN3_INSTRUCT_TEMPLATE \
    --output_file bench_hotpotqa_v2.json \
    --max_batch_size 8 \
    --max_chunk_per_block 16384 \
    --block_size 2048 \
    --case_name hotpotqa
```

执行流程：
1. **文档编码** (~35s): 9,811 篇文档 → 前向传播 → chunk-mean pooling → KV cache 存储
2. **模型加载** (~2s/GPU): 每个 GPU 加载一份 MSA-4B 用于生成
3. **问答生成** (~6min): 1,000 个问题，batch_size=8×4GPU=32
   - 每个问题经历两轮 generate：第一轮检索文档，第二轮基于检索结果生成答案
   - `should_regenerate()` 自动判断是否需要第二轮

### 3. LLM Judge 评分

由于 EC2 实例无 Bedrock 权限，在本地机器执行评分：

```bash
# 使用 AWS Bedrock Claude Sonnet 4.6 作为 judge
python3 llm_judge_bedrock.py bench_hotpotqa_v2.json
```

评分标准（0-5分）与论文一致，评估预测答案与真实答案的准确性、完整性和相关性。

## 结果

### 检索指标 (AR Metrics)

| 指标 | 值 |
|---|---|
| Precision | 0.8515 |
| Recall | 0.8510 |
| F1 | 0.8512 |
| IoU | 0.8255 |

MSA 从 9,811 篇文档中，对 85.1% 的问题正确检索到了相关文档。

### LLM Judge 评分

| | 本次复现 | 论文 Table 1 |
|---|---|---|
| **LLM Score** | **4.172** | **4.061** |
| Judge 模型 | Claude Sonnet 4.6 | Gemini 2.5 Flash |

### 评分分布

| 分数 | 数量 | 占比 |
|---|---|---|
| 5 (完全正确) | 769 | 76.9% |
| 4 (核心信息正确，略有冗余) | 28 | 2.8% |
| 3 (基本正确，有偏差) | 27 | 2.7% |
| 2 (部分相关) | 24 | 2.4% |
| 1 (方向正确但事实错误) | 86 | 8.6% |
| 0 (完全错误) | 66 | 6.6% |

### 典型案例

**满分 (Score 5) — 精确匹配:**
- Q: "When was Erik Watts' father born?"
- True: "May 5, 1939"
- Pred: "May 5, 1939"

**中等 (Score 3) — 部分回答:**
- Q: "Woman's Era and Naj are what kind of magazines?"
- True: "fortnightly women interest magazine"
- Pred: "The retrieved documents only provide information about Woman's Era..."
  (只检索到一篇文档，未能综合两篇信息)

**错误 (Score 0) — 检索到错误文档:**
- Q: "Who was the last king of the Shahiya?"
- True: "Trilochanpala"
- Pred: "Stanisław II Augustus"
  (检索到了错误的文档，回答了另一个国家的国王)

## 结论

1. **复现成功**: LLM Score 4.172 与论文 4.061 处于同一水平，略高 0.111 分，差异可归因于 judge 模型不同（Claude Sonnet 4.6 vs Gemini 2.5 Flash）。

2. **4×L40S 足够**: 尽管 GPU 数量从 8 减至 4，VRAM 从 80GB 降至 48GB，MSA 在 HotpotQA 规模（~10K 文档）下完全可用。

3. **错误模式**: 6.6% 的完全错误主要来自检索失败 — top-k=16 未能覆盖正确文档，导致模型在错误上下文中生成答案。

4. **两轮生成是关键**: MSA 的 QA 流程必须经过两轮 generate（检索 → 基于检索结果回答），单轮只能拿到原文引用，无法生成最终答案。

## 文件说明

```
hotpotqa_reproduction/
  report.md                      ← 本文件
  bench_hotpotqa_raw.json        ← benchmark 原始输出（含检索ID、预测答案、引用文档）
  bench_hotpotqa_llmscore.json   ← LLM Judge 评分结果（含每题评分和分布）
```
