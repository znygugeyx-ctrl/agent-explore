# Infrastructure: vLLM Inference Endpoint

EC2 GPU instance running vLLM for local model inference. Stopped nightly to save cost.

## Quick Reference

| Item | Value |
|------|-------|
| Instance ID | stored in `~/.aws-resources` (never commit) |
| Type | g6e.2xlarge (NVIDIA L40S 48GB) |
| Region | us-east-1 |
| Public IP | dynamic — query after each start (see below) |
| SSH Key | `~/.ssh/vllm-experiment-key.pem` |
| Security Group | stored in `~/.aws-resources` (never commit) |
| vLLM venv | `/home/ubuntu/vllm-env` |
| vLLM version | 0.18.0 |
| Model | `Qwen/Qwen3-8B` (pre-downloaded) |

## Daily Workflow

### 1. Start Instance

```bash
# Load your instance ID (store in ~/.aws-resources, never commit)
# e.g. export VLLM_INSTANCE_ID=i-xxxxxxxxxxxxxxxxx

aws ec2 start-instances --instance-ids $VLLM_INSTANCE_ID --region us-east-1
aws ec2 wait instance-running --instance-ids $VLLM_INSTANCE_ID --region us-east-1

# Get new public IP (changes each start)
aws ec2 describe-instances --instance-ids $VLLM_INSTANCE_ID --region us-east-1 \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
```

### 2. Start vLLM Server

```bash
# SSH in
ssh -i ~/.ssh/vllm-experiment-key.pem ubuntu@<PUBLIC_IP>

# Activate venv and start server
source /home/ubuntu/vllm-env/bin/activate
nohup vllm serve Qwen/Qwen3-8B \
  --host 0.0.0.0 --port 8000 \
  --enable-prefix-caching \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  > /home/ubuntu/vllm.log 2>&1 &

# Or use the restart script
bash /home/ubuntu/restart_vllm.sh
```

Server takes ~30s to load the model. Check readiness:
```bash
curl http://localhost:8000/v1/models
```

### 3. Create SSH Tunnel (from local machine)

```bash
ssh -f -N -L 8000:localhost:8000 -i ~/.ssh/vllm-experiment-key.pem ubuntu@<PUBLIC_IP>
```

After this, `http://localhost:8000/v1` is your local endpoint.

### 4. Verify

```bash
curl http://localhost:8000/v1/models
# Should return: {"data": [{"id": "Qwen/Qwen3-8B", ...}]}
```

### 5. Stop Instance (end of day)

```bash
aws ec2 stop-instances --instance-ids $VLLM_INSTANCE_ID --region us-east-1
```

### Troubleshooting: Stale Tunnel

If port 8000 is bound but not responding (from a previous session):
```bash
pkill -f "ssh.*8000.*vllm-experiment"
# Then recreate the tunnel
```

## vLLM Server Flags

| Flag | Purpose |
|------|---------|
| `--enable-prefix-caching` | KV cache reuse for shared prefixes (critical for experiments) |
| `--max-model-len 32768` | Qwen3-8B supports up to 32K context |
| `--gpu-memory-utilization 0.90` | Reserve 90% of GPU memory for KV cache |
| `--enable-auto-tool-choice` | Enable function calling support |
| `--tool-call-parser hermes` | Use Hermes-style tool call parsing (required for Qwen3) |

## Using the Endpoint

### Basic Inference (OpenAI-compatible)

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(base_url="http://localhost:8000/v1", api_key="no-key")
response = await client.chat.completions.create(
    model="Qwen/Qwen3-8B",
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.6,  # Qwen3 default
    max_tokens=1024,
)
```

### With Tool Calling

```python
response = await client.chat.completions.create(
    model="Qwen/Qwen3-8B",
    messages=messages,
    tools=[{
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
        },
    }],
    temperature=0.6,
    max_tokens=1024,
)
```

### With agent-explore Framework

```python
from core.types import Model, StreamOptions
from core.agent import AgentConfig, run_agent
import core.providers

model = Model(id="Qwen/Qwen3-8B", name="Qwen3-8B", provider="openai_compat",
              base_url="http://localhost:8000/v1")
config = AgentConfig(model=model, system_prompt="You are helpful.", tools=my_tools,
                     stream_options=StreamOptions(max_tokens=1024, temperature=0.6))
messages = await run_agent(config, "Your prompt here")
```

### Logit Bias (Logit Masking)

Block specific tokens at decode time without changing the prompt. Useful for preventing
the model from calling certain tools while preserving the KV prefix cache.

```python
# Step 1: Get token IDs for tool names via /tokenize endpoint
from core.providers.openai_compat import tokenize

token_ids = await tokenize("http://localhost:8000/v1", "Qwen/Qwen3-8B", "calculator")
# Returns: [token_id_1, token_id_2, ...]

# Step 2: Build logit_bias dict (token_id -> -100 to block)
logit_bias = {str(tid): -100 for tid in token_ids}

# Step 3: Pass via API
response = await client.chat.completions.create(
    model="Qwen/Qwen3-8B",
    messages=messages,
    tools=tools,
    logit_bias=logit_bias,  # blocks model from generating these tokens
)

# Step 3 (alt): Pass via agent-explore StreamOptions.extra
config = AgentConfig(
    model=model, system_prompt="...", tools=all_tools,
    stream_options=StreamOptions(max_tokens=1024, extra={"logit_bias": logit_bias}),
)
```

### Prefix Cache Metrics

Query vLLM's Prometheus `/metrics` endpoint to measure cache performance:

```bash
curl -s http://localhost:8000/metrics | grep prefix_cache
# vllm:prefix_cache_queries_total{...} 1812994
# vllm:prefix_cache_hits_total{...} 1723824
```

```python
import urllib.request

resp = urllib.request.urlopen("http://localhost:8000/metrics")
text = resp.read().decode()
for line in text.split("\n"):
    if line.startswith("vllm:prefix_cache_queries_total{"):
        queries = int(float(line.split()[-1]))
    elif line.startswith("vllm:prefix_cache_hits_total{"):
        hits = int(float(line.split()[-1]))
hit_rate = hits / queries
```

### Tokenize Endpoint

vLLM exposes `/tokenize` (NOT under `/v1`) for getting token IDs:

```python
import json, urllib.request

data = json.dumps({"model": "Qwen/Qwen3-8B", "prompt": "hello"}).encode()
req = urllib.request.Request("http://localhost:8000/tokenize",
                             data=data, headers={"Content-Type": "application/json"})
result = json.loads(urllib.request.urlopen(req).read().decode())
token_ids = result["tokens"]
```

## Qwen3-8B Model Notes

- Default sampling: `temperature=0.6, top_k=20, top_p=0.95`
- Use `temperature=0.0` for deterministic experiments
- Thinking model: uses `<think>...</think>` blocks; budget `max_tokens=1024` to avoid thinking exhausting output
- Tool call format: Hermes style (matched by `--tool-call-parser hermes`)
- Context window: 32,768 tokens
