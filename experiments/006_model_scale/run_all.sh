#!/bin/bash
# Experiment 006: Run guided decoding experiment across Qwen3 model sizes.
#
# Usage:
#   EC2_IP=<ip> bash experiments/006_model_scale/run_all.sh
#
# Prerequisites:
#   - SSH tunnel must NOT be active (script manages it)
#   - EC2 instance must be running
#   - restart_vllm.sh on EC2 must accept MODEL_ID as $1

set -euo pipefail

EC2_IP="${EC2_IP:?Set EC2_IP environment variable}"
KEY="$HOME/.ssh/vllm-experiment-key.pem"
SSH="ssh -i $KEY ubuntu@$EC2_IP"
LOCAL_PORT=8001
OBSERVER_URL="${OBSERVER_URL:-http://localhost:7777}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODELS=(
  "Qwen/Qwen3-0.6B"
  "Qwen/Qwen3-1.7B"
  "Qwen/Qwen3-4B"
  "Qwen/Qwen3-8B"
  "Qwen/Qwen3-32B"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

kill_tunnel() {
  pkill -f "ssh.*${LOCAL_PORT}:localhost:8000" 2>/dev/null || true
  sleep 1
}

start_tunnel() {
  kill_tunnel
  ssh -f -N -L "${LOCAL_PORT}:localhost:8000" -i "$KEY" "ubuntu@$EC2_IP"
  echo "[tunnel] localhost:${LOCAL_PORT} -> EC2:8000"
}

wait_for_model() {
  local model_id="$1"
  echo "[wait] Waiting for vLLM to load $model_id ..."
  local attempts=0
  until curl -s "http://localhost:${LOCAL_PORT}/v1/models" 2>/dev/null | grep -q "$(basename $model_id)"; do
    sleep 10
    attempts=$((attempts + 1))
    if [ $attempts -ge 60 ]; then
      echo "[error] Timeout waiting for $model_id after 10 minutes"
      exit 1
    fi
    echo "  ... still waiting ($((attempts * 10))s)"
  done
  echo "[ready] $model_id is ready"
}

model_to_dir() {
  # Qwen/Qwen3-0.6B -> qwen3-0.6b
  echo "$1" | sed 's|Qwen/||' | tr '[:upper:]' '[:lower:]'
}

model_to_tp() {
  case "$1" in
    *32B*|*70B*) echo 4 ;;
    *14B*)        echo 2 ;;
    *)            echo 1 ;;
  esac
}

model_to_max_len() {
  case "$1" in
    *32B*) echo 8192 ;;
    *)     echo 32768 ;;
  esac
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

cd "$PROJECT_ROOT"

for MODEL in "${MODELS[@]}"; do
  MODEL_SHORT=$(model_to_dir "$MODEL")
  RESULTS_DIR="experiments/006_model_scale/results/$MODEL_SHORT"

  echo ""
  echo "====================================================================="
  echo "  Model: $MODEL"
  echo "  Results: $RESULTS_DIR"
  echo "====================================================================="

  # Skip if results already complete (allow resume)
  if [ -f "$RESULTS_DIR/report.md" ]; then
    echo "[skip] Results already exist, skipping $MODEL"
    continue
  fi

  # Copy 8B results from 005 instead of re-running
  if [ "$MODEL" = "Qwen/Qwen3-8B" ]; then
    echo "[copy] Copying Qwen3-8B results from experiment 005 ..."
    mkdir -p "$RESULTS_DIR"
    cp experiments/005_guided_decoding/results/*.json "$RESULTS_DIR/" 2>/dev/null || true
    cp experiments/005_guided_decoding/results/report.md "$RESULTS_DIR/" 2>/dev/null || true
    echo "[done] 8B results copied"
    continue
  fi

  # 1. Restart vLLM with this model
  TP=$(model_to_tp "$MODEL")
  MAX_LEN=$(model_to_max_len "$MODEL")
  echo "[vllm] Starting vLLM with $MODEL (TP=$TP, max_len=$MAX_LEN) ..."
  $SSH "bash /home/ubuntu/restart_vllm.sh $MODEL $TP $MAX_LEN"

  # 2. (Re)start SSH tunnel
  start_tunnel

  # 3. Wait for model to be ready
  wait_for_model "$MODEL"

  # 4. Run experiment
  mkdir -p "$RESULTS_DIR"
  echo "[run] Running experiment (runs=3, concurrency=4) ..."
  python3 -m experiments.005_guided_decoding.run \
    --base-url "http://localhost:${LOCAL_PORT}/v1" \
    --model-id "$MODEL" \
    --runs 3 \
    --concurrency 4 \
    --results-dir "$RESULTS_DIR" \
    --observer-url "$OBSERVER_URL"

  echo "[done] $MODEL completed"
done

echo ""
echo "====================================================================="
echo "  All models done. Running cross-model analysis ..."
echo "====================================================================="
python3 experiments/006_model_scale/analyze.py

echo ""
echo "Report: experiments/006_model_scale/results/report.md"
