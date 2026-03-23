#!/bin/bash
set -ex

# Log everything to /var/log/vllm-setup.log
exec > >(tee -a /var/log/vllm-setup.log) 2>&1
echo "=== vLLM Setup Started at $(date) ==="

# Install vLLM
pip install vllm --upgrade

# Pre-download Qwen3-8B (smaller model for quick iteration)
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-8B')"

echo "=== vLLM Setup Complete at $(date) ==="
echo "To start vLLM server:"
echo "  vllm serve Qwen/Qwen3-8B --host 0.0.0.0 --port 8000 --enable-prefix-caching --max-model-len 32768"
echo "  vllm serve Qwen/Qwen3-32B --host 0.0.0.0 --port 8000 --enable-prefix-caching --max-model-len 32768"
