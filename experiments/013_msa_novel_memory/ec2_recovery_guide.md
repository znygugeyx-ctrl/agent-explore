# EC2 环境恢复指南

如需在新实例上重新部署 MSA 实验环境，按以下步骤操作。

## 1. 启动实例

```bash
source ~/.aws-resources
aws ec2 run-instances \
  --region us-east-1 \
  --image-id $VLLM_AMI_US_EAST_1 \
  --instance-type g6e.12xlarge \
  --key-name $VLLM_KEY_NAME \
  --security-group-ids $VLLM_SG_US_EAST_1 \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":200,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=MSA-deploy},{Key=Experiment,Value=MSA}]'
```

AMI: `Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.7 (Ubuntu 22.04)` — 自带 CUDA 12.8, PyTorch 2.7。

## 2. 安装 Miniconda + Python 3.12

系统只有 Python 3.10，MSA 需要 3.12。

```bash
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p ~/miniconda3 && rm miniconda.sh
source ~/miniconda3/etc/profile.d/conda.sh
```

**坑：Conda ToS 必须先接受**（否则 `conda create` 报 `CondaToSNonInteractiveError`）：
```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

```bash
conda create -n msa python=3.12 -y
conda activate msa
```

## 3. 克隆 MSA 并安装依赖

```bash
git clone https://github.com/EverMind-AI/MSA.git && cd MSA
pip install -r requirements.txt
pip install flash-attn==2.7.4.post1 --no-build-isolation
pip install fastapi uvicorn boto3 sentence-transformers faiss-cpu
```

**注意**：`flash-attn` 编译约需 5 分钟，必须用 `--no-build-isolation`。

## 4. 下载模型

```bash
mkdir -p ckpt
# MSA-4B (用于 MSA 推理)
huggingface-cli download --resume-download EverMind-AI/MSA-4B --local-dir ckpt/MSA-4B
# Qwen3-4B (用于 RAG generator)
huggingface-cli download --resume-download Qwen/Qwen3-4B --local-dir ckpt/Qwen3-4B
```

## 5. 补丁 MSA 源码（必须）

MSA 的 `deserialize()` 有两个 bug，不修复的话从缓存加载会 crash。

### 5a. rk/k 设备分配修复

文件：`src/msa_service.py`，`deserialize()` 方法中加载 K 和 rk 的部分。

将：
```python
if os.path.exists(k_path):
    temp_k = torch.load(k_path, map_location="cpu", weights_only=False)
    current_k = temp_k.to(self.device)
    del temp_k

if os.path.exists(rk_path):
    current_rk = torch.load(rk_path, map_location="cpu", weights_only=False)
```

替换为：
```python
has_rk = os.path.exists(rk_path)

if os.path.exists(k_path):
    temp_k = torch.load(k_path, map_location="cpu", weights_only=False)
    if has_rk:
        current_k = temp_k  # K stays CPU when rk exists
    else:
        current_k = temp_k.to(self.device)
    del temp_k

if has_rk:
    current_rk = torch.load(rk_path, map_location="cpu", weights_only=False)
    current_rk = current_rk.to(self.device)  # rk → GPU
```

### 5b. BlockDesc 恢复修复

同一文件 `deserialize()` 中，将：
```python
self.block_desc = BlockDesc(
    docs=bd_info["docs"],
    doc_ids=bd_info["doc_ids"].to(self.device),
    pool_ids=bd_info["pool_ids"].to(self.device) if bd_info["pool_ids"] is not None else None
)
```

替换为：
```python
self.block_desc = BlockDesc()
self.block_desc.init_docs(bd_info["docs"], self.device)
self.block_desc.pool_ids = bd_info["pool_ids"].to(self.device) if bd_info["pool_ids"] is not None else None
self.block_desc.pool_ids_cpu = bd_info["pool_ids"] if bd_info["pool_ids"] is not None else None
```

## 6. 准备记忆数据

```bash
# 小说数据（需要从本地上传 蛊真人_utf8.txt，然后切分）
python prepare_novel.py  # → mdata_novel.pkl

# HotpotQA 数据（benchmark 首次运行时自动从 HuggingFace 下载）
```

## 7. 启动服务

```bash
export CUDA_VISIBLE_DEVICES=0,1,2,3
export MASTER_PORT=29509
export MSA_MEMORY_FILE=mdata_novel.pkl        # 或 data/hotpotqa/mdata_hotpotqa.pkl
export MEMORY_DATA_PATH=/home/ubuntu/MSA/memory_cache  # 编码缓存目录
mkdir -p $MEMORY_DATA_PATH
python -u server.py  # 端口 8080
```

首次启动需要编码全部文档（小说 ~2.5 分钟），编码结果缓存到 `MEMORY_DATA_PATH`。后续启动直接加载缓存（~12 秒）。

**注意**：不同记忆库需要不同缓存路径，否则会加载错误的缓存。

## 8. 本地连接

```bash
# SSH tunnel
ssh -f -N -L 8080:localhost:8080 -i ~/.ssh/vllm-experiment-key.pem ubuntu@<IP>

# 测试
curl http://localhost:8080/health

# 交互式客户端
python3 tools/msa_chat.py
```

## 9. 跑 benchmark

```bash
cd /home/ubuntu/MSA
python -u src/app/benchmark.py \
    --benchmark hotpotqa \
    --model_path ckpt/MSA-4B \
    --top_p 0.9 --temperature 0.0 \
    --max_length 2048 \
    --template QWEN3_INSTRUCT_TEMPLATE \
    --output_file bench_result.json \
    --max_batch_size 8 \
    --max_chunk_per_block 16384 \
    --block_size 2048 \
    --case_name hotpotqa
```

## 关键提醒

- MSA server **必须用 `qa_mode=True`**，否则 `_sample()` 报 `KeyError: 'tokenizer'`
- MSA 的 QA 是**多轮生成**（通常 3 轮），server 需要循环调用 `should_regenerate()`
- `engine.generate(callback=None)` **不是线程安全的**，并发使用需要 per-request Event + callback
- 本地端口 8000 可能被占用，SSH tunnel 用 8080
- 实例用完后务必 **terminate**（不是 stop），避免持续计费
