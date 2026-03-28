#!/bin/bash
# setup_vllm_instance.sh
# Full vLLM setup on a fresh Ubuntu 22.04 GPU instance (L40S / g6e family).
# Run as ubuntu user. Logs to /home/ubuntu/setup.log
# Takes ~30-45 min due to downloads.
set -euo pipefail
exec > >(tee -a /home/ubuntu/setup.log) 2>&1
echo "=== Setup started $(date) ==="

# ── 1. NVIDIA CUDA drivers ─────────────────────────────────────────────────
echo "[1/5] Installing CUDA 12.4 + drivers..."
cd /tmp
wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update -q
sudo apt-get install -y cuda-toolkit-12-4 cuda-drivers 2>&1 | tail -5
echo "[1/5] CUDA install done"

# ── 2. Python 3.11 + venv ─────────────────────────────────────────────────
echo "[2/5] Installing Python 3.11..."
sudo apt-get install -y python3.11 python3.11-venv python3-pip 2>&1 | tail -3
python3.11 -m venv /home/ubuntu/vllm-env
source /home/ubuntu/vllm-env/bin/activate
pip install --upgrade pip -q
echo "[2/5] Python ready"

# ── 3. vLLM ───────────────────────────────────────────────────────────────
echo "[3/5] Installing vLLM 0.8.x..."
pip install vllm 2>&1 | tail -5
echo "[3/5] vLLM installed: $(python -c 'import vllm; print(vllm.__version__)')"

# ── 4. HuggingFace hub + model download ───────────────────────────────────
echo "[4/5] Downloading Qwen3-32B (~64GB, may take 20-30 min)..."
pip install huggingface_hub -q
python3 -c "
from huggingface_hub import snapshot_download
print('Downloading Qwen3-14B...')
snapshot_download('Qwen/Qwen3-14B')
print('Downloading Qwen3-32B...')
snapshot_download('Qwen/Qwen3-32B')
print('Downloads complete.')
"
echo "[4/5] Models downloaded"

# ── 5. Upload restart script ───────────────────────────────────────────────
echo "[5/5] Setup complete. Upload restart_vllm.sh via scp before running experiments."

echo "=== Setup finished $(date) ==="
echo "GPU check:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
