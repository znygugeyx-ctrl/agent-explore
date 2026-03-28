#!/bin/bash
# restart_vllm.sh — stop any running vLLM container and start a new one via Docker.
# Placed at /home/ubuntu/restart_vllm.sh on the EC2 instance.
#
# Usage: bash restart_vllm.sh <MODEL_ID> [TENSOR_PARALLEL_SIZE] [MAX_MODEL_LEN]
#
# Examples:
#   bash restart_vllm.sh Qwen/Qwen3-14B
#   bash restart_vllm.sh Qwen/Qwen3-32B 4 8192

MODEL_ID="${1:?Usage: $0 <model_id> [tp_size] [max_model_len]}"
TP="${2:-1}"
MAX_LEN="${3:-32768}"

echo "[restart_vllm] model=$MODEL_ID tp=$TP max_model_len=$MAX_LEN"

# Stop and remove existing container
sudo docker rm -f vllm 2>/dev/null && echo "[restart_vllm] removed existing vllm container" || true

sudo docker run -d \
  --name vllm \
  --runtime nvidia \
  --gpus all \
  -v /home/ubuntu/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  --ipc host \
  vllm/vllm-openai:latest \
    --model "$MODEL_ID" \
    --tensor-parallel-size "$TP" \
    --max-model-len "$MAX_LEN" \
    --gpu-memory-utilization 0.90 \
    --enforce-eager \
    --enable-prefix-caching \
    --enable-auto-tool-choice \
    --tool-call-parser hermes

echo "[restart_vllm] container started: $(sudo docker ps --filter name=vllm --format '{{.Names}} {{.Status}}')"
echo "[restart_vllm] logs: sudo docker logs -f vllm"
