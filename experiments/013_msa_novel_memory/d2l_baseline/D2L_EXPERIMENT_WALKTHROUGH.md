# D2L 实验执行流程详解

> **目标**: 完整讲解 **正在运行的 D2L 实验**（2026-04-25）每一步做了什么
> **适用读者**: 想要重现、debug 或扩展 D2L 对比实验的人
> **对应实验**: `experiments/013_msa_novel_memory/d2l_baseline/`

---

## 0. 一句话概述

实验在**一台 EC2 g6e.2xlarge**（1× L40S 46GB）上，串行跑**四个任务**：
```
HotpotQA 2K → HotpotQA 4K → HotpotQA 8K → 小说 8K
```

每个任务对每一道题做：**加载上下文 → internalize 成 LoRA → 回答问题 → 重置 LoRA**。

全程单实例、单 GPU、单 Python 进程（每个任务重新启动 Python 并从 checkpoint 加载模型）。

---

## 1. 环境与实例

| 项 | 值 |
|---|---|
| EC2 实例 | `<instance-id>` (g6e.2xlarge) |
| IP | `3.81.6.120` |
| GPU | 1× NVIDIA L40S (46 GB HBM) |
| vCPU / RAM | 8 / 32 GB |
| 磁盘 | 1 TB gp3 |
| OS / CUDA | Ubuntu 22.04 / CUDA 12.4（系统）、cu121（venv） |
| Python | 3.10.12 |
| venv | `~/d2l_strict_venv/` |
| 关键库 | `torch 2.4.0+cu121`, `flash-attn 2.7.0.post2`, `transformers 4.51.3` |

**为什么这个组合**: 见 `D2L_REPRODUCTION_GUIDE.md` §2「坑 2」。简而言之：doc-to-lora 的 `idefics2.py` 代码硬编码了 flash-attn **2.7.0 的 `unpad_input` 5 值返回** API，而预编译 wheel 又要求 torch 与 flash-attn ABI 严格对齐，**torch 2.4 + flash-attn 2.7.0.post2 是唯一路径**。

---

## 2. 启动脚本（4 个任务串行跑）

实验入口：`~/scripts/run_d2l_all_strict.sh` （由 nohup 启动）

```bash
#!/bin/bash
set -e
source ~/d2l_strict_venv/bin/activate
cd /home/ubuntu/doc-to-lora

echo "=== $(date) D2L HotpotQA 2k ==="
python3 ~/d2l_baseline/run_d2l.py \
    --dataset ~/d2l_baseline/data/hotpotqa_pools.json \
    --dataset_type hotpotqa --pool_size 2k \
    --checkpoint checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin \
    --output ~/d2l_baseline/results/hotpotqa_d2l_2k.json

# ... 重复 4k, 8k, novel 8k ...
```

**特性**：
- **串行**执行（`set -e` + 无后台符号）：一个跑完才跑下一个
- **每个任务独立 Python 进程**：进程结束时 CUDA 内存完全释放，避免累积碎片
- **每个任务各自重新加载 checkpoint**（~3s）：不是 bug，是刻意简化
- **有断点续跑支持**：如果中途挂了，重启脚本会自动从 `output JSON` 里已有的 question id 跳过

---

## 3. 单个任务的完整流程（以 HotpotQA 4K 为例）

### 3.1 启动阶段

```
python3 run_d2l.py --dataset hotpotqa_pools.json --dataset_type hotpotqa --pool_size 4k ...
```

#### 3.1.1 加载数据集（~0.1s）

```python
with open(args.dataset) as f:
    records = json.load(f)
# records: list of 200 questions, each with {question, answer, gold_doc_ids, pools: {2k, 4k, 8k}}
```

每条记录的 `pools['4k']` 结构：
```json
{
    "docs": ["...doc text 1...", "...doc text 2...", ...],  // ~30 docs
    "num_docs": 30,
    "total_tokens": 3952  // avg
}
```

#### 3.1.2 断点续跑检查（~0.01s）

```python
if os.path.exists(args.output):
    existing = json.load(open(args.output))
    done_ids = {r["question"] for r in existing}
    records = [r for r in records if r["question"] not in done_ids]
```

#### 3.1.3 加载 D2L 模型（~5-8s）

这是最复杂的一步，发生在 `D2LModel.__init__`:

```python
from d2l_wrapper import D2LModel
model = D2LModel(
    "checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin",
    max_ctx_chunk_len=4096,
)
```

内部展开：

1. **`torch.load(...)`**：从磁盘读取 checkpoint（约 1.5 GB，包含 hypernet 权重 + base model 名字）
2. **`ModulatedPretrainedModel.from_state_dict(...)`**:
   - 解析出 `base_model_name = "Qwen/Qwen3-4B-Instruct-2507"` 和 `lora_config` (rank=8, target=`down_proj`)
   - 调用 `get_model(...)` 加载 **冻结的 Qwen3-4B 基模**（从 HF cache，~3 GB，bf16，flash_attention_2）
   - 在 base model 上**套一层空 LoRA 适配器**（rank=8, α=45.25, 36 层每层一个 `down_proj` adapter）
   - 实例化 `HyperLoRA` hypernet（Perceiver aggregator + MLP heads），~300M 参数
   - **加载 hypernet 权重** from state_dict（覆盖随机初始化）
3. **`enable_iterative_mode(True)`** — aggregator 逐层处理（省峰值显存）
4. 初始化两个 tokenizer：
   - `self.tokenizer`：Qwen3-4B 的 tokenizer（给 base model 的 chat template 用）
   - `self.ctx_tokenizer`：context encoder 的 tokenizer（给 internalize 用，实际也是 Qwen3-4B）

**此时 GPU 占用**：约 10-12 GB（4B 模型 bf16 ≈ 8 GB + hypernet ≈ 1 GB + overhead）

#### 3.1.4 Warmup（隐式发生在第一题）

第一题会比后续题慢 ~50%（CUDA kernel 编译、内存分配等），后续稳定在 ~3-4s/题。

---

### 3.2 对每一道题的循环（核心）

```python
for i, rec in enumerate(records):  # 遍历 200 道题
    pool = rec["pools"]["4k"]
    context = "\n\n".join(pool["docs"])   # ~3952 tokens 的拼接字符串
    question = rec["question"]

    t0 = time.time()
    answer = model.ask(context, question)    # ← 单题的全部工作
    latency_ms = int((time.time() - t0) * 1000)

    results.append({
        "question": question, "answer": rec["answer"],
        "d2l_answer": answer, "latency_ms": latency_ms,
        "pool_size": "4k", "pool_tokens": pool["total_tokens"], ...
    })

    # 每 5 题保存一次（atomic write: tmp → rename）
    if (i+1) % 5 == 0:
        _save(args.output, results)
```

#### 3.2.1 单题推理的细节（`model.ask()`）

整个过程分三段：**Internalize → Generate → Reset**。

```python
def ask(self, context: str, question: str) -> str:
    self._internalize_chunked(context)      # ① 把 context 变成 LoRA 权重
    try:
        chat_ids = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": question}],
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.model.device)
        output = self.model.generate(       # ② 带 LoRA 的 base model 生成答案
            input_ids=chat_ids,
            max_new_tokens=256,
            do_sample=False,
        )
        answer = self.tokenizer.decode(
            output[0][chat_ids.shape[1]:], skip_special_tokens=True
        )
    finally:
        self.model.reset()                  # ③ 清空 LoRA（下一题要重新生）
        torch.cuda.empty_cache()
    return answer.strip()
```

### 3.2.2 ① Internalize — 把 context 变成 LoRA

这是 D2L 的**核心创新**，比 `model.generate()` 更值得讲清楚：

```python
def _internalize_chunked(self, context: str):
    # tokenize
    full_ids = tokenize_ctx_text({"context": [context]}, self.ctx_tokenizer)["ctx_ids"][0]
    total_len = len(full_ids)   # 对 4K pool 约 3950 tokens

    if total_len <= self.max_ctx_chunk_len:  # 4096, 4K pool 通常一刀不切
        # 走简单路径：整段喂给 hypernet
        return self.model._internalize_from_ids(
            torch.tensor([full_ids], device=self.model.device)
        )

    # 否则（8K 或更长）：切块处理
    n_chunks = ceil(total_len / self.max_ctx_chunk_len)   # 比如 8K/4K = 2 块
    avg_len = ceil(total_len / n_chunks)
    chunks = [full_ids[i:i+avg_len] for i in range(0, total_len, avg_len)]

    # 每块独立过 ctx_encoder，结果搬到 CPU，循环，节约峰值显存
    features, attn_mask = self._encode_chunks(chunks)

    # 拼好的 features 整体过 hypernet -> LoRA 权重
    self.model.patch_lora_forward()
    with torch.no_grad():
        flat_loras, _ = self.model.hypernet.forward(features, attn_mask, position_ids=None)
    generated_loras = self.model.hypernet._to_lora_dict(flat_loras)
    self.model.generated_loras = generated_loras
```

**具体数据流**（以 4K, 不分块 为例）：

```
context (str, ~16K chars)
    │
    ├── ctx_tokenizer.encode()
    ↓
ctx_ids (tensor [1, ~3950])
    │
    ├── self.model.ctx_encoder(...)  # 🔴 per-layer activations from Qwen3-4B itself
    ↓
features (tensor [1, 36_layers, ~3950, hidden_size])   # 🔴 显存大户：~10 GB
    │
    ├── self.model.hypernet.forward(features, attn_mask)
    │     │
    │     ├── Perceiver aggregator (8 blocks, cross-attention)
    │     │     features [1, 36, ~3950, dim] → latents [1, 36, 16, dim]  (压缩到 16 latents)
    │     │
    │     ├── ResMLP head
    │     ↓
    │   flat LoRA weights [36 layers, r=8 + out_features]
    ↓
generated_loras: dict {layer_idx: (A, B)}  # shape per layer: (8, 14336) and (14336, 8)
    │
    └── stored in self.model.generated_loras
        patched_forward: original_down_proj + (x @ A.T @ B.T) * scaling
```

**关键点**：
- `ctx_encoder` 不是 base model 的 full forward！它用 `per_layer_activations` 类型，返回**所有 36 层的 hidden states**。这是为什么显存占用大。
- `patch_lora_forward()` 替换 base model 每一层 `down_proj` 的 forward 函数，使其使用 `generated_loras` 里的权重。
- `reset()` 会把 forward 换回原版（`module.forward = module.forward_orig`）。

### 3.2.3 ② Generate — 带 internalized LoRA 生成答案

```python
chat_ids = tokenizer.apply_chat_template(
    [{"role": "user", "content": question}], ...  # ⚠️ 不包含 context！
)
output = model.generate(input_ids=chat_ids, max_new_tokens=256, do_sample=False)
```

**注意**：这里**只把 question 送进 prompt**，不含 context。context 已经"内化"到 LoRA 权重里了。这就是 D2L 的卖点——**推理时 0 context 成本**。

生成过程中每一层 `down_proj` 的 forward：
```python
y = base_down_proj(x) + (dropout(x) @ A.T) @ B.T * scaling   # A, B 来自 internalize 阶段
```

Qwen3-4B-Instruct 倾向输出完整句子（这是论文明确指出的 verbose 问题）。例如：
- 问："How tall is the Eiffel Tower?"
- 答："The Eiffel Tower is 330 metres tall, located in Paris."  ← 完整句子，不是单个答案

### 3.2.4 ③ Reset — 清空 LoRA

```python
self.model.reset()  # generated_loras = None, 恢复原版 down_proj.forward
torch.cuda.empty_cache()  # 释放 feature tensors 的显存
```

**为什么必须 reset**：下一题的 context 可能完全不同，若不清空，LoRA 残留会干扰下一题。

---

### 3.3 任务结束阶段

```python
_save(args.output, all_results)  # 最终原子保存
# Python 进程结束，CUDA 内存完全释放
```

然后 bash 脚本进入下一个任务（4K → 8K → novel）。

---

## 4. 时序图（单题级）

```
t=0    ┌─ _internalize_chunked()
       │   ├─ tokenize ctx_ids (~3950 tokens)     [~5 ms]
       │   ├─ ctx_encoder forward (36-layer acts) [~500 ms, 10 GB peak]
       │   ├─ hypernet Perceiver forward          [~200 ms, 3 GB peak]
       │   └─ patch_lora_forward (set down_proj)  [~50 ms]
t=800ms│
       ├─ tokenizer.apply_chat_template            [~10 ms]
       ├─ model.generate (256 tokens, greedy)
       │   ├─ prefill                             [~100 ms]
       │   └─ 256 decoding steps (LoRA每步)       [~2000 ms]
t=3s   │
       ├─ tokenizer.decode                         [~5 ms]
       └─ reset + empty_cache                      [~100 ms]
```

**4K pool 实测**: ~3-4 s/题
**8K pool 实测**: ~10-15 s/题（ctx_encoder 在 8K 上慢 ~3×，加上 chunk 循环）

---

## 5. 当前实验的四个任务对应的数据

### 5.1 HotpotQA（英文，200 题）

来源：`~/d2l_baseline/data/hotpotqa_pools.json`（200 条记录）

每条记录结构：
```json
{
    "question": "What Electoral Division in Victoria contained a suburb of Melbourne...",
    "answer": "The Division of Fawkner",
    "gold_doc_ids": [5974, 5972],  // 在 HotpotQA 9811 语料库中的 id
    "pools": {
        "2k": {"docs": [15 docs], "total_tokens": 1901},
        "4k": {"docs": [30 docs], "total_tokens": 3952},
        "8k": {"docs": [61 docs], "total_tokens": 8047}
    }
}
```

**2K/4K/8K 是嵌套的**：`pool_2K ⊂ pool_4K ⊂ pool_8K`。每档都含 2 个 gold docs + 不同数量 distractors。这样可以分离"信息密度"和"记忆压缩"的影响。

### 5.2 小说 8K（中文，131 题）

来源：`~/d2l_baseline/data/novel_8k_pools.json`（131 条记录）

从《蛊真人》采样 50 个 ~8K token 的 context windows，用 Claude Sonnet 4.6 基于每个 window 生成 3-5 道题。

每条记录结构：
```json
{
    "id": 1,
    "question": "春秋蝉在十大奇蛊中排名第几？它的作用是什么？",
    "answer": "春秋蝉在十大奇蛊排名中位列第七，其作用是逆转时光，简而言之就是重生。",
    "difficulty": "easy",  // easy / medium / hard
    "category": "item",    // reasoning / event / item / character / ...
    "window_sections": [0, 1, 2, 3],  // 小说中的 section index
    "window_tokens": 7936,
    "context_text": "==== chapter 1 ... chapter 2 ... chapter 3 ...（整段 ~11k 中文字符）"
}
```

---

## 6. 监控正在运行的实验

### 进度查看命令

```bash
# 看进程
ssh ubuntu@3.81.6.120 'ps aux | grep run_d2l | grep -v grep'

# 看 log
ssh ubuntu@3.81.6.120 'tail -10 /tmp/d2l_all_strict.log'

# 看结果文件记录数
ssh ubuntu@3.81.6.120 '
for f in ~/d2l_baseline/results/*.json; do
    [ -f "$f" ] && python3 -c "import json; d=json.load(open(\"$f\")); print(\"$f:\", len(d))"
done
'

# 看 GPU 占用
ssh ubuntu@3.81.6.120 'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader'
```

### 实时进度（写这篇文档时的状态，~14:15）

| 任务 | 状态 | 预计时长 |
|------|------|---------|
| HotpotQA 2k | ✅ 完成（200/200） | ~11 min |
| HotpotQA 4k | 🟢 运行中（刚启动 ~5 min） | ~15 min |
| HotpotQA 8k | ⏳ 排队 | ~45 min (chunked) |
| Novel 8k | ⏳ 排队 | ~25 min (中文+chunked) |

**总预计完成时间**：再约 80 min。

---

## 7. 输出文件格式（供后续 LLM Judge 用）

实验跑完后 `~/d2l_baseline/results/` 下 4 个 JSON 文件：

```json
// hotpotqa_d2l_4k.json
[
    {
        "question": "What Electoral Division in Victoria...",
        "answer": "The Division of Fawkner",
        "gold_doc_ids": [5974, 5972],
        "d2l_answer": "The Electoral Division in Victoria that contained...",
        "latency_ms": 3124,
        "pool_size": "4k",
        "pool_tokens": 3952,
        "pool_docs": 30
    },
    ...  // 200 条
]

// novel_d2l_8k.json
[
    {
        "id": 1,
        "question": "春秋蝉在十大奇蛊中排名第几...",
        "answer": "春秋蝉在十大奇蛊排名中位列第七...",
        "difficulty": "easy",
        "category": "item",
        "d2l_answer": "春秋蝉排名第七，作用是逆转时光...",
        "latency_ms": 14320,
        "window_tokens": 7936,
        "window_sections": [0, 1, 2, 3]
    },
    ...  // 131 条
]
```

这 4 个文件在实验完成后会被 scp 到本地 `experiments/013_msa_novel_memory/d2l_baseline/results/`，然后用 `score_results.py` 跑 Claude Sonnet 4.6 做 LLM Judge 评分。

---

## 8. 与 MSA / RAG 实验的对应关系

这次跑的 D2L 4 个任务**与 MSA / RAG 完全对齐**：**相同的 200 道 HotpotQA 题 + 相同的 131 道小说题**，**相同的 context pool**（同样的 2K/4K/8K token 预算）。

不同之处在于**每个方案如何"使用" context pool**：

| 方案 | 如何处理 8K pool 的 200 题 | 回答时的 prompt |
|------|---------------------------|----------------|
| RAG | 每题独立 FAISS 检索 top-5 → 塞 prompt | question + top-5 docs |
| MSA | 合并所有 pool docs 为一个 corpus，MSA engine 路由 top-16 chunks | question（chunks 由路由注入） |
| **D2L** | **每题独立 internalize 整个 pool → 生成 LoRA** | **question（无 context）** |

这样三种方案在**相同信息预算**下对比，ablation 出的是"记忆机制"本身的差异。

---

## 9. 常见问题

### Q: 为什么每次都要重新 `torch.load(checkpoint)`？能不能共享？

A: 4 个任务可以共享一个模型实例（省 ~30s），但代价是：
- CUDA 内存碎片随时间累积
- 一个任务崩溃会影响后续
- 断点续跑复杂度上升

**本实验选择了简单性**（每任务一个 Python 进程）。

### Q: `max_ctx_chunk_len=4096` 怎么选的？

A: 46 GB L40S 放 4B 模型后**约剩 30 GB**。`ctx_encoder` 返回 `[1, 36, seq_len, 2048]` 的 tensor，**seq_len=4096 占约 12 GB**（bf16），加 hypernet 的 Perceiver cross-attention 中间张量约 10 GB，峰值约 25 GB。更大的 chunk（比如 8K）会 OOM。

### Q: 为什么不用 `do_sample=True` 加温度？

A: 实验对比要**可重现**。所有三种方案（RAG/MSA/D2L）都用 `temperature=0, do_sample=False`（贪心解码），排除采样差异的噪声。

### Q: 如果 LoRA 生成失败会怎样？

A: 代码里的 `try/finally` 确保 `reset()` 总会执行，不会把错误 LoRA 带到下一题。但若 internalize 本身异常（OOM、数值溢出），单题会抛异常导致整个脚本崩溃。当前没有 per-question try/except 保护——因为 internalize 崩溃通常是系统性的（内存不足），继续跑也没意义。

### Q: 怎么扩展到新数据集？

A: 只需构造 `records = [{question, answer, context}]` 格式的 JSON，喂给 `D2LModel.ask(context, question)`。HotpotQA 路径是 `pools[size].docs` 拼接，小说路径是 `rec["context_text"]`。参考 `run_d2l.py`。

---

## 10. 文件清单（为后续维护）

本地仓库：`experiments/013_msa_novel_memory/d2l_baseline/`

```
d2l_baseline/
├── D2L_REPRODUCTION_GUIDE.md    # 环境搭建 + 坑与解
├── D2L_EXPERIMENT_WALKTHROUGH.md # 本文档
├── d2l_wrapper.py               # D2LModel 封装（internalize+generate+reset）
├── run_d2l.py                   # 任务 runner（带断点续跑 + 增量保存）
├── data/
│   ├── hotpotqa_pools.json      # 200 题 × 3 档 pool
│   └── novel_8k_pools.json      # 131 题 × 1 档 pool
└── results/                     # 每个任务一个 JSON 结果
    ├── hotpotqa_d2l_2k.json
    ├── hotpotqa_d2l_4k.json
    ├── hotpotqa_d2l_8k.json
    └── novel_d2l_8k.json
```

EC2 实例：`/home/ubuntu/`

```
d2l_strict_venv/          # Python 3.10 venv (torch 2.4 + flash-attn 2.7.0)
doc-to-lora/              # 官方代码（干净，不需要 patch）
├── checkpoints/
│   ├── qwen_4b_d2l/checkpoint-20000/pytorch_model.bin  # 本实验用
│   └── gemma_demo/checkpoint-80000/pytorch_model.bin   # 备用（需 HF token）
└── src/ctx_to_lora/...
d2l_baseline/             # 跟本地同步
scripts/run_d2l_all_strict.sh    # 入口脚本
```

日志：`/tmp/d2l_all_strict.log`（由 nohup 写入）
