# Doc-to-LoRA (D2L) 复现指南

> **实验日期**: 2026-04-25
> **目标**: 在 agent-explore 013 中将 D2L 作为参数化记忆范式，与 MSA / RAG 进行对比
> **结论**: **复现成功** — Qwen3-4B SQuAD normalized recall = 0.892（论文 Figure 12 报告 ~0.85-0.90）

---

## 1. 快速开始（成功配置）

**硬件**: AWS EC2 `g6e.2xlarge`（1× L40S 46GB, 8 vCPU, 32GB RAM）
**磁盘**: 至少 1TB gp3（checkpoint ~5GB + 依赖 ~20GB + 实验数据）

**软件栈（验证可用）**:
- Python **3.10**
- torch **2.4.0+cu121**
- flash-attn **2.7.0.post2**（预编译 wheel for torch 2.4）
- transformers **4.51.3**
- doc-to-lora **原版代码**（不需要任何 patch）

### 一键部署脚本

```bash
#!/bin/bash
set -e
cd /home/ubuntu

# 1. Create clean Python 3.10 venv
python3 -m venv d2l_strict_venv
source d2l_strict_venv/bin/activate

# 2. Install torch 2.4.0 (matches flash-attn wheel)
pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 \
    --index-url https://download.pytorch.org/whl/cu121

# 3. Install prebuilt flash-attn 2.7.0.post2 wheel (critical: torch2.4 + cu12)
pip install "https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.0.post2/flash_attn-2.7.0.post2%2Bcu12torch2.4cxx11abiFALSE-cp310-cp310-linux_x86_64.whl"

# 4. Clone doc-to-lora
git clone --depth 1 https://github.com/SakanaAI/doc-to-lora.git
cd doc-to-lora

# 5. Install doc-to-lora package (may upgrade some deps - OK)
pip install -e .

# 6. Install missing runtime deps
pip install llmlingua tensorboard tensorboardX wandb

# 7. Fix huggingface-hub dist-info conflict (critical!)
pip install --force-reinstall "huggingface-hub==0.36.2"
rm -rf ~/d2l_strict_venv/lib/python3.10/site-packages/huggingface_hub-1.*.dist-info 2>/dev/null

# 8. Download checkpoints from HuggingFace
python -c "
from huggingface_hub import snapshot_download
snapshot_download('SakanaAI/doc-to-lora', allow_patterns='qwen_4b_d2l/*', local_dir='checkpoints')
snapshot_download('SakanaAI/doc-to-lora', allow_patterns='gemma_demo/*', local_dir='checkpoints')
"
```

### Sanity check

```bash
cd /home/ubuntu/doc-to-lora
WANDB_MODE=disabled python3 run_eval.py \
    --checkpoint_path checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin \
    --datasets squad --split test \
    --max_ctx_chunk_len 8192 --eval_batch_size_gen 1 \
    --max_test_samples_per_ds 100
```

**预期输出**: `test_squad_qa_f1_score ≈ 0.318`, **qa_recall ≈ 0.83**（normalized vs base ≈ 0.89）

---

## 2. 复现过程中的坑与解决方案

### 坑 1: `pip install -e .` 把 `huggingface_hub` 升级到 1.12（破坏 transformers）

**症状**:
```
ImportError: huggingface-hub>=0.30.0,<1.0 is required for a normal functioning of this module,
but found huggingface-hub==1.12.0
```

**原因**: doc-to-lora 的 `datasets` 依赖拉了新版本 huggingface-hub 1.12，但 transformers 4.51.3 不兼容。而且 pip metadata 会有两个 dist-info 目录共存，即使 `pip show` 显示正确版本，`importlib.metadata.version()` 仍返回旧版本。

**解决方案**:
```bash
pip install --force-reinstall "huggingface-hub==0.36.2"
# 手动删除残留 dist-info
rm -rf ~/venv/lib/python3.10/site-packages/huggingface_hub-1.*.dist-info
```

### 坑 2: flash-attn 必须与 torch 版本完全匹配 ABI

**症状**:
```
ImportError: .../flash_attn_2_cuda.cpython-310-x86_64-linux-gnu.so: undefined symbol: _ZN3c105ErrorC2...
```

**原因**: flash-attn 的 CUDA 扩展 ABI 与 torch 版本强绑定。`pip install flash-attn==X.Y.Z` 从 PyPI 下载的源码需要编译（g6e.2xlarge 8 vCPU 需 ~1h）。

**解决方案**: **用 GitHub release 的预编译 wheel**（注意 torch 版本要精确匹配）:

| flash-attn 版本 | 可用的 torch | unpad_input 返回值数 | doc-to-lora 兼容性 |
|---|---|---|---|
| 2.6.3 | 2.0-2.4 | 4 | ❌ 代码期望 5 个 |
| **2.7.0.post2** | **2.4, 2.5** | **5** | ✅ **最佳选择** |
| 2.7.4.post1 | 2.4-2.6 | 5 | ⚠️ `cu_seqlens` 参数格式更严，D2L 会报错 |

**关键发现**: doc-to-lora 代码硬编码了 flash-attn 2.7.0 的 `unpad_input` 返回 5 个值的 API。`idefics2.py:650`:
```python
context, _, cu_seq_lens_k, max_length_k, _ = unpad_input(context, attention_mask)
```

### 坑 3: 无法评估 `gemma-2-2b-it`（gated repo）

**症状**: `OSError: You are trying to access a gated repo`

**原因**: `google/gemma-2-2b-it` 需要在 HuggingFace 上申请访问。Qwen3-4B 无此问题。

**解决方案**:
- 主要用 Qwen3-4B checkpoint（20K steps 训练）
- 或者申请 Gemma-2-2b-it 访问后再用 Gemma checkpoint（80K steps, 论文主力）
- 在 EC2 上登录：`echo $HF_TOKEN > ~/.cache/huggingface/token`

### 坑 4: 用 SQuAD-style F1 低估 D2L（测评指标错用）

**症状**: D2L 初看 F1 = 0.318，似乎远低于论文水平。

**实际原因**: Qwen3-4B-Instruct 非常 verbose，即使 prompt 指示"Output only the answer"，仍会输出完整句子。例如：
- Gold: `"carbon monoxide"`（2 tokens）
- D2L: `"Increased oxygen concentrations in the patient's lungs displace carbon monoxide from the heme group of hemoglobin."`（17 tokens）

这导致：
- Recall = 1.0 ✅（gold 完整包含在 pred 中）
- Precision = 0.13 ❌（pred 过长）
- F1 = 0.23 ❌（被 precision 拖低）

**论文原文（App. E）**:
> "responses from Mistral-7B-Instruct-v0.2 and Qwen3-4B-Instruct-2507 are verbose despite instructing the model to output only the answer. This behavior makes the ROUGE-L precision and F1 scores much lower compared to gemma-2-2b-it. Therefore, for the Mistral-7B-Instruct-v0.2 and Qwen3-4B-Instruct-2507 model, **we report the ROUGE-L recall score instead of ROUGE-L F1 score.**"

**解决方案**: 对 Qwen 模型用 **Recall** 作为主指标：
```python
# 评估时用 recall
recall_list = [r['qa_recall'] for r in records]
normalized = mean(recall_list) / base_model_recall
```

### 坑 5: doc-to-lora 代码完全硬绑定 `flash_attention_2` — 无法用 SDPA 或 eager 绕过

**背景**: 我曾尝试避免 flash-attn 依赖，把代码从 `flash_attention_2` 改成 `sdpa` / `eager`。

**失败原因**:
1. `Idefics2PerceiverResampler` 不支持 SDPA（transformers 4.51.3 抛 `ValueError`）
2. `Idefics2PerceiverAttention` 的 `forward` 签名与 `Idefics2PerceiverFlashAttention2` **不兼容**——flash 版本额外接受 `is_cross_attn` 参数，eager 版本不接受
3. `idefics2.py:forward` 内深度使用 `cu_seqlens_k`, `max_length_k` 等 flash 特有 API
4. 即使绕过 attention，`unpad_input` 函数本身就来自 flash_attn 包

**结论**: **不要试图绕开 flash_attn**。必须装。上面的预编译 wheel 是最快路径（5min）。

### 坑 6: 长 context（>2K tokens）需要 chunked internalize

**我们的需求**: 小说 QA 每题 context 8K tokens。

**问题**: doc-to-lora 训练时 `max_packed_ctx_len=6144`，推理时的 `_internalize_from_ids` 单次调用接受的 tensor shape 是 `[1, seq_len]`，不分块。

**解决方案**（在 `d2l_wrapper.py` 中实现）:
```python
def _internalize_chunked(self, context: str):
    full_ids = tokenize_ctx_text({'context': [context]}, self.ctx_tokenizer)['ctx_ids'][0]
    if len(full_ids) <= self.max_ctx_chunk_len:
        return self.model._internalize_from_ids(torch.tensor([full_ids], device=self.model.device))

    # Split into roughly equal chunks, pad to same length, pass as batch [n_chunks, max_len]
    n_chunks = ceil(len(full_ids) / self.max_ctx_chunk_len)
    avg_len = ceil(len(full_ids) / n_chunks)
    chunks = [full_ids[i:i+avg_len] for i in range(0, len(full_ids), avg_len)]
    # ... pad with eos/pad token, build attention mask, return batched call
```

这与论文 eval 脚本 `run_eval.py` 的 `max_ctx_chunk_len=8192` 参数处理逻辑一致。

### 坑 7: wandb 导致 eval 崩溃

**症状**: eval 跑完 100 题但在计算 metric 前崩溃
```
wandb.errors.UsageError: No API key configured. Use `wandb login` to log in.
```

**解决方案**: 设置环境变量 `WANDB_MODE=disabled`:
```bash
WANDB_MODE=disabled python3 run_eval.py ...
```

---

## 3. 复现结果

### 3.1 Base Qwen3-4B-Instruct-2507（ICL, full context in prompt）

SQuAD 100 samples:
- **qa_recall**: 0.9315
- qa_precision: 0.7078
- qa_f1_score: 0.7497

### 3.2 Qwen3-4B + D2L (`qwen_4b_d2l/checkpoint-20000`)

SQuAD 100 samples:
- **qa_recall**: 0.8313 (70% samples with recall=1.0)
- qa_precision: 0.2191 (verbose outputs)
- qa_f1_score: 0.3168

**Normalized Recall**: 0.8313 / 0.9315 = **0.892**

**对比论文 Figure 12**: Qwen3-4B D2L on SQuAD normalized ≈ **0.85-0.90** ✅

**复现结论**: **成功** — 数字与论文报告一致（在误差范围内）。

### 3.3 关键观察：D2L 在不同任务上的表现差异

同一 D2L checkpoint（Qwen3-4B）：
- **SQuAD（单段落抽取）**: recall 0.83（强）
- **HotpotQA 4K（多跳推理）**: gold 字符串出现在预测中比例仅 25%，LLM judge score 1.41/5（弱）

这说明 D2L 在**训练分布外任务**（multi-hop）上表现下降 — 是方法本身的局限，不是复现问题。

---

## 4. 环境清单（精确版本）

运行 `pip list` 关键依赖：

```
torch                    2.4.0+cu121
torchvision              0.19.0+cu121
torchaudio               2.4.0+cu121
flash-attn               2.7.0.post2
transformers             4.51.3
peft                     0.13.2
accelerate               1.0.1
datasets                 3.0.1
huggingface-hub          0.36.2
deepspeed                0.15.4
tokenizers               0.21.4
numpy                    1.26.4 或 2.x 都可
einops                   0.8.2
llmlingua                0.2.2
tensorboard              2.x
```

**注意**: doc-to-lora pyproject.toml 要求 `datasets==3.6.0` / `deepspeed==0.17.1`，但用 3.0.1 / 0.15.4 也能 run（只是 pip 报 "incompatible"，不阻塞）。

---

## 5. 常用操作 cheatsheet

### 跑论文原生 eval（验证复现）

```bash
cd /home/ubuntu/doc-to-lora
source ~/d2l_strict_venv/bin/activate

# Qwen D2L on SQuAD (100 samples)
WANDB_MODE=disabled python3 run_eval.py \
    --checkpoint_path checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin \
    --datasets squad --split test --max_ctx_chunk_len 8192 --eval_batch_size_gen 1 \
    --max_test_samples_per_ds 100

# Base Qwen on SQuAD (no D2L, ICL only)
WANDB_MODE=disabled python3 run_eval.py \
    --model_name_or_path Qwen/Qwen3-4B-Instruct-2507 \
    --datasets squad --split test --eval_batch_size_gen 1 \
    --max_test_samples_per_ds 100
```

### 自定义 D2L 推理（用于对比实验）

```python
import torch
from ctx_to_lora.model_loading import get_tokenizer
from ctx_to_lora.modeling.hypernet import ModulatedPretrainedModel

# Load
sd = torch.load("checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin", weights_only=False)
model = ModulatedPretrainedModel.from_state_dict(sd, train=False, use_sequence_packing=False)
tokenizer = get_tokenizer(model.base_model.name_or_path)

# Internalize context (for long contexts use d2l_wrapper.D2LModel)
model.internalize("The Eiffel Tower is 330 metres tall, located in Paris.")

# Generate
chat = tokenizer.apply_chat_template(
    [{"role": "user", "content": "How tall is the Eiffel Tower?"}],
    add_generation_prompt=True, return_tensors="pt",
).to(model.device)
out = model.generate(input_ids=chat, max_new_tokens=64, do_sample=False)
print(tokenizer.decode(out[0][chat.shape[1]:], skip_special_tokens=True))

# Reset before next context
model.reset()
```

### 长 context 推理（用封装的 d2l_wrapper）

```python
from d2l_wrapper import D2LModel  # in experiments/013/d2l_baseline/
model = D2LModel(
    "checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin",
    max_ctx_chunk_len=2048,  # 关键：8K context 会被切成 4 个 chunks
)
answer = model.ask(context_8k_text, "your question here")
```

---

## 6. Checkpoint 说明

| Checkpoint | Base Model | Steps | 用途 |
|---|---|---|---|
| `qwen_4b_d2l/checkpoint-20000` | Qwen3-4B-Instruct-2507 | 20,000 | 主实验（与 MSA 一致的 backbone） |
| `gemma_demo/checkpoint-80000` | google/gemma-2-2b-it | 80,000 | 论文主实验，F1 更高 |
| `gemma_2b_d2l/checkpoint-20000` | google/gemma-2-2b-it | 20,000 | Gemma 同步数 sanity |
| `mistral_7b_d2l/checkpoint-20000` | Mistral-7B-Instruct-v0.2 | 20,000 | 未使用 |

**Gemma checkpoint 需要 HF token 访问 `google/gemma-2-2b-it`**。

---

## 7. 与 MSA / RAG 对比时的注意事项

### 7.1 评估指标必须对齐

| 指标 | 适合 | 不适合 |
|------|------|--------|
| SQuAD-style F1 | Gemma（简洁输出） | Qwen（verbose） |
| **Recall** | **Qwen D2L** | - |
| LLM Judge (0-5) | 综合对比 | 需要强 judge model |
| ROUGE-L | 所有 | 中文可能不准 |

**推荐**: 同时报告 recall（公平）+ LLM judge（综合）。

### 7.2 三方案性能特点（预期）

| 方案 | 优势任务 | 劣势任务 |
|------|---------|---------|
| **RAG** | 事实检索、明确答案 | context 压缩重构 |
| **MSA** | 长文档内 top-k 检索 | 中文（英文模板硬编码） |
| **D2L** | 单段落抽取（SQuAD-like） | 多跳推理（HotpotQA） |

### 7.3 推理延迟（L40S, Qwen3-4B）

| 方案 | 单题延迟 | 备注 |
|------|---------|------|
| RAG | ~2s | embedding + generate |
| MSA | ~1-2s | multi-round generation |
| D2L (2K) | ~2s | internalize + generate |
| D2L (4K) | ~4s | |
| D2L (8K, chunked) | ~15s | 4 chunks × internalize |

---

## 8. 失败尝试汇总（避免后人重蹈覆辙）

| 尝试 | 结果 | 教训 |
|------|------|------|
| torch 2.6 + flash-attn 2.6.3 wheel (torch 2.4 ABI) | 数值可能不准 | ABI 要匹配 |
| torch 2.6 + flash-attn 2.7.4.post1 (torch 2.6 wheel) | `cu_seqlens_k` shape 错误 | doc-to-lora API 不兼容 2.7.4 |
| torch 2.4 + flash-attn 2.6.3 wheel (原生 API 匹配) | `unpad_input` 返回 4 值 vs 期望 5 值 | doc-to-lora 绑定 2.7.0 API |
| Python 3.12 + 最新 wheel | 没有 py312 flash-attn for torch 2.4 | cp310 最稳 |
| 把 doc-to-lora 代码改用 `sdpa` / `eager` attention | API 签名不兼容，层层报错 | **不要改源码**，走原版+正确 wheel |
| 源码编译 flash-attn 2.6.3 | 8 vCPU 编译 > 1h | **用预编译 wheel** |

**黄金法则**: 装 flash-attn 2.7.0.post2 预编译 wheel（torch 2.4 版本），doc-to-lora 原版代码不改，就能跑。

---

## 9. 参考资料

- **论文**: https://arxiv.org/abs/2602.15902 (Doc-to-LoRA: Learning to Instantly Internalize Contexts)
- **代码**: https://github.com/SakanaAI/doc-to-lora
- **Checkpoints**: https://huggingface.co/SakanaAI/doc-to-lora
- **flash-attn releases**: https://github.com/Dao-AILab/flash-attention/releases
- **Qwen normalized recall 的说明**: 论文 App. E

---

## 10. 本次实验元数据

- **实例**: EC2 g6e.2xlarge (`<instance-id>`), us-east-1
- **IP**: 3.81.6.120
- **关键目录**:
  - `/home/ubuntu/doc-to-lora/` — 源码 + checkpoints
  - `/home/ubuntu/d2l_strict_venv/` — Python 环境
  - `/home/ubuntu/d2l_baseline/` — 实验代码（本实验自有）
- **保存的文件**（用于后续复现验证）:
  - `~/doc-to-lora/checkpoints/qwen_4b_d2l/eval-results-20000/20260425-130219_2f7b45df/` — SQuAD 100样本结果
  - `~/doc-to-lora/eval_results/Qwen/Qwen3-4B-Instruct-2507/20260425-124243_dbd19cad/` — Base Qwen SQuAD 结果
