# MSA 部署踩坑记录

部署 EverMind-AI/MSA 为 HTTP 服务时遇到的问题及修复方案。供后续部署参考。

## 问题 1: Conda ToS 阻断环境创建

**现象**: `conda create` 报 `CondaToSNonInteractiveError`，要求接受 Anaconda 频道的服务条款。

**原因**: 2024 年起 Anaconda 默认频道要求在非交互环境中显式接受 ToS。

**修复**:
```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

## 问题 2: `_sample()` 无条件读取 `meta['tokenizer']`

**现象**: `qa_mode=False` 时，`generate()` 报 `KeyError: 'tokenizer'`。

**原因**: `src/msa/generate.py` 的 `_sample()` 方法第 83 行无条件读取 `meta['tokenizer']`，不区分 `qa_mode`。只有 `qa_mode=True` 时 `MSAService.generate()` 才会将 tokenizer 注入 meta。

**修复**: 服务必须使用 `qa_mode=True`。

## 问题 3: `deserialize()` 后 rk/k 设备分配错误

**现象**: 从缓存加载后，推理报 `RuntimeError: Expected all tensors to be on the same device, but found cuda:2 and cpu`。

**原因**: `src/msa_service.py` 的 `deserialize()` 方法（~line 448）将 K 无条件加载到 GPU，但当模型使用解耦 router（`decouple_router=True`，有独立的 `rk` 文件）时，K 应留在 CPU（用于 attention），rk 应放 GPU（用于路由）。而 `_init_block_data()` 在首次编码时正确处理了这个逻辑，`deserialize()` 没有。

**修复**: 补丁 `src/msa_service.py` 的 `deserialize()`:
```python
# 原代码: K 总是上 GPU
current_k = temp_k.to(self.device)
# rk 留在 CPU（错误）
current_rk = torch.load(rk_path, map_location="cpu")

# 修复: 根据是否有 rk 决定 K 的位置
has_rk = os.path.exists(rk_path)
if has_rk:
    current_k = temp_k            # K stays CPU
    current_rk = torch.load(rk_path, map_location="cpu").to(self.device)  # rk → GPU
else:
    current_k = temp_k.to(self.device)  # K → GPU (兼做路由)
```

## 问题 4: `deserialize()` 后 BlockDesc 缺少 doc_lens/offsets

**现象**: 从缓存加载后，`doc_query()` 报 `TypeError: 'NoneType' object is not subscriptable`（`desc.doc_lens_cpu` 为 None）。

**原因**: `deserialize()` 只恢复了 `docs`、`doc_ids`、`pool_ids`，但 `doc_offsets_cpu` 和 `doc_lens_cpu` 是在 `init_docs()` 中计算的，`deserialize()` 没有调用它。

**修复**: 用 `init_docs()` 替代手动赋值:
```python
# 原代码
self.block_desc = BlockDesc(docs=bd_info["docs"], doc_ids=..., pool_ids=...)

# 修复: 调用 init_docs() 来正确计算 offsets 和 lens
self.block_desc = BlockDesc()
self.block_desc.init_docs(bd_info["docs"], self.device)
self.block_desc.pool_ids = bd_info["pool_ids"].to(self.device)
self.block_desc.pool_ids_cpu = bd_info["pool_ids"]
```

## 问题 5: 只做了一轮 generate，没有最终答案

**现象**: 服务返回的是引用的原文内容，而不是最终答案。

**原因**: MSA 的 QA 流程是**多轮**的，`benchmark.py` 的主循环通过 `should_regenerate()` 检测是否需要继续生成：

```
Round 1: 输入问题 → 模型检索文档，输出 [doc_ids]<|object_ref_end|>
Round 2: 输入 "<regenerate>" + Round1输出 → 模型加载引用文档原文，输出原文<|object_ref_end|>  
Round 3: 再次 regenerate → 模型基于原文生成 "The answer to the question is: ..."
```

`should_regenerate()` 的逻辑：只要响应以 `<|object_ref_end|>` 结尾且不包含 "The answer to the question is:"，就继续生成。一般需要 **3 轮**才能得到最终答案。

**修复**: 服务端用循环调用 generate，和 benchmark 一致：
```python
MAX_ROUNDS = 5
for _ in range(MAX_ROUNDS):
    raw = _sync_generate(prompt)
    response = _postprocess(raw)
    new_prompt = should_regenerate(request, response)
    if new_prompt is None:
        break
    prompt = new_prompt
```

## 问题 6: `engine.generate(callback=None)` 非线程安全

**现象**: 并发请求时结果错乱。

**原因**: 默认同步路径使用共享的 `self.sync_event` 和 `self.sync_rsp`，多线程同时调用会互相覆盖。

**修复**: 使用 callback 参数 + per-request Event:
```python
def _sync_generate(prompt):
    event = threading.Event()
    result = {}
    def cb(texts, recall_topk, userdata):
        result["texts"] = texts
        event.set()
    engine.generate([prompt], require_recall_topk=True, callback=cb)
    event.wait()
    return result["texts"][0]
```

## 最终服务架构

```
server.py (FastAPI)
  ├── MSAEngine 单例 (lifespan 初始化)
  ├── MSA_MEMORY_FILE 环境变量选择记忆库
  ├── run_qa() — 多轮 generate 循环 (max 5 rounds)
  │   ├── _sync_generate() — per-request Event, thread-safe
  │   ├── _postprocess() — 和 benchmark.py 一致
  │   └── should_regenerate() — 直接从 benchmark.py 导入
  └── extract answer: split("The answer to the question is:")

start_server.sh [memory_file]
  # bash start_server.sh data/hotpotqa/mdata_hotpotqa.pkl
  # bash start_server.sh mdata_novel.pkl
```

## 问题 7: RAG Generator 使用了 base 模型而非 Instruct

**现象**: RAG 生成的答案中 566/1000 包含未闭合的 `<think>` 标签，导致答案为空。

**原因**: 下载了 `Qwen/Qwen3-4B`（base 模型），而非 `Qwen/Qwen3-4B-Instruct`。base 版本默认启用 thinking 且不稳定。

**修复**: RAG generator 必须用 `Qwen/Qwen3-4B-Instruct`：
```bash
hf download Qwen/Qwen3-4B-Instruct --local-dir ckpt/Qwen3-4B-Instruct
```
生成时添加 `enable_thinking=False` 或在 chat template 中关闭 thinking。

## 问题 8: `huggingface-cli` 在新版 huggingface-hub 中被废弃

**现象**: `huggingface-cli download` 报 deprecated 错误。

**修复**: 新版使用 `hf download` 命令代替。

## 问题 9: RAG baseline 与论文配置不一致

**现象**: 我们的 RAG HotpotQA 复现得分 2.008，论文 Qwen3-4B R@5 = 3.179，差距 37%。

**原因（多重）**:
1. Generator 用了 `Qwen/Qwen3-4B`（base）而非 `Qwen3-4B-Instruct-2507`
2. Retriever 用了 KaLMv2-mini 而非论文的 `Qwen3-4B-Embedding`
3. 没有 Reranker（论文 RR 组用 `Qwen3-4B-Rerank`）
4. 直接 top-5 检索，论文是先检索 100 篇再 rerank 取 top-k
5. 没有使用 UltraRAG v2.0 框架

**论文 RAG 完整配置**:

| 组件 | Same-backbone (Table 2) | Best-of-breed (Table 3) |
|---|---|---|
| Retriever | Qwen3-4B-Embedding | KaLMv2-Embedding-Gemma3-12B-2511 |
| Generator | Qwen3-4B-Instruct-2507 | Qwen3-235B-Instruct / Llama-3.3-70B |
| Reranker (RR) | Qwen3-4B-Rerank | Qwen3-8B-Rerank |
| RAG 框架 | UltraRAG v2.0 | UltraRAG v2.0 |
| 检索流程 | 检索 100 → rerank → top-{1,5,10} | 同左 |
| Judge | Gemini 2.5 Flash (0-5) | 同左 |

**修复**: 严格复现需要:
```bash
# Models
hf download Qwen/Qwen3-4B-Instruct --local-dir ckpt/Qwen3-4B-Instruct
hf download Qwen/Qwen3-Embedding-4B --local-dir ckpt/Qwen3-Embedding-4B
hf download Qwen/Qwen3-Reranker-4B --local-dir ckpt/Qwen3-Reranker-4B
pip install ultrarag  # UltraRAG v2.0 框架
```

## 部署 Checklist

1. `conda tos accept` 两个频道
2. `pip install flash-attn==2.7.4.post1 --no-build-isolation`
3. 补丁 `src/msa_service.py` 的 `deserialize()`（问题 3 和 4）
4. `server.py` 必须用 `qa_mode=True`
5. `server.py` 必须用多轮 generate 循环
6. 首次编码后设 `MEMORY_DATA_PATH` 启用缓存（注意不同记忆库需要不同缓存路径）
