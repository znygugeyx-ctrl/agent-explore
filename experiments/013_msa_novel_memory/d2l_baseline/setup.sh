#!/bin/bash
# D2L Baseline 环境搭建脚本
# 在 EC2 g6e.2xlarge (1× L40S) 上运行

set -euo pipefail

echo "=== Step 1: Clone doc-to-lora ==="
cd /home/ubuntu
if [ ! -d "doc-to-lora" ]; then
    git clone https://github.com/SakanaAI/doc-to-lora.git
    cd doc-to-lora
else
    cd doc-to-lora
    git pull
fi

echo "=== Step 2: Install dependencies ==="
pip install -e ".[eval]" 2>/dev/null || pip install -e .
pip install flash-attn --no-build-isolation

echo "=== Step 3: Download checkpoints ==="
# Qwen3-4B D2L checkpoint (主实验)
python -c "
from huggingface_hub import snapshot_download
snapshot_download('SakanaAI/doc-to-lora', allow_patterns='qwen_4b_d2l/*', local_dir='checkpoints')
print('Qwen3-4B D2L checkpoint downloaded')
"

# Gemma-2-2B D2L checkpoint (sanity check)
python -c "
from huggingface_hub import snapshot_download
snapshot_download('SakanaAI/doc-to-lora', allow_patterns='gemma_demo/*', local_dir='checkpoints')
print('Gemma-2-2B D2L checkpoint downloaded')
"

echo "=== Step 4: Download base models ==="
python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
# Just download tokenizer for token counting (full model loaded by D2L)
AutoTokenizer.from_pretrained('Qwen/Qwen3-4B-Instruct-2507')
AutoTokenizer.from_pretrained('google/gemma-2-2b-it')
print('Tokenizers downloaded')
"

echo "=== Step 5: Verify basic inference ==="
python -c "
import torch
from ctx_to_lora.model_loading import get_tokenizer
from ctx_to_lora.modeling.hypernet import ModulatedPretrainedModel

state_dict = torch.load('checkpoints/gemma_demo/checkpoint-80000/pytorch_model.bin', weights_only=False)
model = ModulatedPretrainedModel.from_state_dict(state_dict, train=False, use_sequence_packing=False)
tokenizer = get_tokenizer(model.base_model.name_or_path)

model.internalize('The capital of France is Paris. It is known for the Eiffel Tower.')
chat = tokenizer.apply_chat_template(
    [{'role': 'user', 'content': 'What is the capital of France?'}],
    add_generation_prompt=True, return_tensors='pt'
).to(model.device)
out = model.generate(input_ids=chat, max_new_tokens=64)
answer = tokenizer.decode(out[0][chat.shape[1]:], skip_special_tokens=True)
print(f'Test answer: {answer}')
model.reset()
print('Basic inference OK')
"

echo "=== Setup complete ==="
