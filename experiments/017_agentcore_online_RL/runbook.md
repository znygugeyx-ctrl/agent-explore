# 017 — AgentCore + AWS GPU 在线 RL 最小实验 runbook

目标：跑通一条**纯 AWS** 的 online RL 闭环 —
`4B policy → AgentCore rollout → reward → veRL/GRPO 更新 LoRA → 新 policy 再 rollout`。
第一目标是**验证链路跑通**，不是练出强模型。

## 架构（单节点 g6e.12xlarge）

```
g6e.12xlarge (4×L40S, 192GB)
├── rLLM trainer (veRL FSDP backend, GRPO + LoRA rank16)
├── vLLM (collocated rollout 生成)
└── rllm-model-gateway (捕获 token/logprob，暴露给 AgentCore)
        ↑ HTTP 回调（关键网络环节）
AWS Bedrock AgentCore Runtime
└── strands_math_agent (GSM8K, reward=exact+format) → 写 S3
```

任务：GSM8K（reward 可验证、不依赖 LLM judge）。跑通后再换业务任务。

## 关键资源（已创建）

```
AWS account:  <AWS_ACCOUNT_ID>
Region:       us-east-1
Runtime ARN:  arn:aws:bedrock-agentcore:us-east-1:<AWS_ACCOUNT_ID>:runtime/rl_app-10GyZj7qsj
ECR image:    <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/agentcore/rl:dev   (linux/arm64)
S3 bucket:    agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1
Runtime role: AmazonBedrockAgentCoreSDKRuntime-us-east-1-4a9245d104
CodeBuild role: AmazonBedrockAgentCoreSDKCodeBuild-us-east-1-4a9245d104
toolkit repo: experiments/017_agentcore_online_RL/agentcore-rl-toolkit
agent name:   rl_app   (example: examples/strands_math_agent)
```

---

## Phase A — AgentCore rollout 链路（✅ 已完成 2026-06-27）

成功标准：部署成功 + `/invocations` 被调用 + rollout 结果写入 S3。**全部达成**。

### 环境踩坑与修复
1. **typer 太旧**：`bedrock-agentcore-starter-toolkit 0.2.2` 的 CLI 用了 `Literal['basic','production']`，
   typer 0.9.4 不支持 → 升级 `pip install -U 'typer>=0.12'`（实得 0.26.8）。任何 `agentcore` 子命令在此之前都会崩。
2. **本机无 docker**：用已装的 `finch`（Amazon 容器工具）。
   - `finch vm init` 初始化 VM。
   - finch 无 `buildx`、`build` 无 `--push` → 写了 `scripts/build_image_and_push_to_ecr_finch.sh`
     （`finch build` + `finch push` 两步）。
   - AgentCore Runtime 用 **arm64 (Graviton)**，Mac 也是 arm64 → 原生构建，无需模拟。

### 命令（已执行）
```bash
cd agentcore-rl-toolkit/examples/strands_math_agent

# 1. CLI 已 configure（.bedrock_agentcore.yaml 已存在，agent=rl_app, platform=linux/arm64）

# 2. 构建并推镜像（本机 finch）
cd ../..  # 回到 toolkit 根
./scripts/build_image_and_push_to_ecr_finch.sh \
  --dockerfile=examples/strands_math_agent/.bedrock_agentcore/strands_math_agent_rl/Dockerfile \
  --tag=dev \
  --context=examples/strands_math_agent

# 3. 部署到 AgentCore Runtime（云端 CodeBuild，自动建 role/ECR）
cd examples/strands_math_agent
agentcore deploy --agent rl_app --auto-update-on-conflict

# 4. 给 Runtime role 加 S3 写权限
aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1-4a9245d104 \
  --policy-name RLToolkitS3Access \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:PutObject","s3:GetObject"],"Resource":"arn:aws:s3:::agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1/*"}]}'

# 5. invoke 验证链路（base_url 故意不可达 → 预期 error 写入 S3）
agentcore invoke --agent rl_app '{
  "prompt": "Natalia sold clips to 48 friends in April, and half as many in May. How many altogether?",
  "answer": "72",
  "_rollout": {"exp_id":"smoke-1","input_id":"q1",
    "s3_bucket":"agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1",
    "base_url":"http://127.0.0.1:9/v1","model_id":"dummy"}
}'
# 返回 {"status":"processing","result_key":"smoke-1/q1/<session>.json"}

# 6. 读 S3 结果
aws s3 cp s3://agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1/smoke-1/q1/<session>.json - | python3 -m json.tool
```

### 结果
S3 出现 `{"status_code":500,"stop_reason":"Connection error.", ...完整 traceback + payload}`。
agent 真正构造了 OpenAIModel 并对 base_url 发起 chat completion，连接失败符合预期 →
**rollout runtime + S3 delivery 链路确认健康，只差可达的推理 endpoint。**

### payload 契约（来自 rl_app.py 实读）
- 顶层：`prompt`(题目), `answer`(GT, str, 用于算 reward)
- `_rollout`: `exp_id`, `input_id`, `s3_bucket`（必需）+ `base_url`, `model_id`, 可选 `sampling_params`
- agent 写死 `OpenAIModel(api_key="EMPTY")` → base_url 必须是 **OpenAI 兼容、不校验 key、AgentCore 可达** 的 endpoint。Bedrock 不能直接填。

---

## Phase 2 — 打通真实推理回路（进行中）

成功标准：AgentCore rollout 真正调到 EC2 上的 4B 模型，rollout 写出 `{"rewards":...}`，
且 token/logprob 被 rllm-model-gateway 捕获落库。

### 计划
1. 用 `infra-ops` skill 拉起 g6e.12xlarge（tag `Experiment=017_agentcore_online_RL`）。
2. EC2 上起 vLLM（Qwen 4B）+ rllm-model-gateway。
3. 解决网络可达性：AgentCore MicroVM → EC2 gateway 的回调路径
   （公网 IP + SG / ALB / ngrok 之一，待定）。
4. invoke 一条 GSM8K，验证 S3 出现 reward。

### 已核对（实读 rLLM 仓库，2026-06-27）
- **模型 = `Qwen/Qwen3-4B-Instruct-2507`**（转录里 "retired/Qwen3.5-4B" 是幻觉，已证伪）。
- **base_url 指向 gateway 不是 vLLM**：形态 `http://<gateway>/sessions/{sid}/v1`。
  gateway:9090 反向代理 → vLLM:8000（`/v1`）。veRL 模式下 GatewayManager 自动把 veRL 的 vLLM worker 注册进 gateway。
- **gateway 启动**：`rllm-model-gateway --port 9090 --worker http://localhost:8000/v1`。
- **网络回路 = cloudflared tunnel**（rLLM 原生）：
  `rllm.gateway.tunnel=cloudflared` → AgentCore 容器经 `*.trycloudflare.com` → 训练机 gateway:9090 → vLLM:8000。
  也可填自己的 tailscale/ngrok/bore/frp URL。**出站 tunnel，EC2 无需公网入站。**
- **官方 veRL 脚本 = 8×A100 40GB + Megatron TP=8**（`train_agentcore_math_verl.sh` 第 3 行注释）。
  → 我们 g6e.12xlarge (4×L40S) **必须改造**：FSDP 替 Megatron、n_gpus=4、缩小 context。
- **remote_runtime 配置**：`rllm/trainer/config/rllm/base.yaml` 第 131-147 行；脚本经 `.env` 注入
  `AGENTCORE_AGENT_ARN` / `AGENTCORE_S3_BUCKET`，加 `tps_limit=25` `session_timeout=300`。

### veRL 脚本关键配置（官方默认，待改造）
| 项 | 官方默认 | 我们的目标(4×L40S) |
|---|---|---|
| 模型 | Qwen/Qwen3-4B-Instruct-2507 | 同 |
| backend / engine | verl / **megatron** TP=8 | verl / **fsdp** |
| n_gpus_per_node | 8 | 4 |
| max_prompt / response | 14336 / 2048 | 缩小(待定 ~4096/1024) |
| rollout.n (group) | 4 | 4 |
| train_batch_size | 64 | 缩小(待定 16~32) |
| lora_rank | 16 | 16 |
| adv_estimator | grpo | grpo |

### GPU 实例（已就绪 2026-06-27）
- **g6e.12xlarge 全线无容量**（us-east-1/2/west-2 三区，连单卡 g6e.2xl 都没有，L40S 全局紧张）。
- 真实探容量后改用 **g5.24xlarge（4×A10G，每张 23GB，合计 ~92GB）@ us-east-2c**，~$8/h。
- 4 卡结构同原 g6e 方案，veRL FSDP n_gpus=4 直接套用；显存 92GB 跑 4B+LoRA+collocated vLLM 够用。
- 环境：Python 3.10.12、Docker 29.4.1、Deep Learning AMI（CUDA/驱动预装）、磁盘 300GB。
- ⚠️ us-east-2 用 default VPC 的 default SG，原只开 Self；已手动开放 22（用户放开到所有 IP）。
- 通过 tag `Experiment=017_agentcore_online_RL` 在 **us-east-2** 查找实例（不存 id/ip）。

### Phase 2 步骤（✅ 全部完成 2026-06-27）
1. ✅ 拉起 GPU 实例（g5.24xlarge @ us-east-2）。
2. ✅ EC2 起 vLLM(Qwen3-4B, docker) + rllm-model-gateway:9090（先不装 veRL）。
3. ✅ cloudflared quick tunnel 暴露 gateway。
4. ✅ invoke 一条 GSM8K → **S3 出 `{"rewards":1.0, "status_code":200}`**。

### Phase 2 完整闭环（已验证）
```
agentcore invoke (本地)
 → AgentCore Runtime (AWS 云端 MicroVM, runtime rl_app-10GyZj7qsj)
   → strands math agent (多轮 + calculator 工具)
     → cloudflared tunnel (公网, AgentCore 出站源 IP 如 <EGRESS_IP>)
       → rllm-model-gateway:9090 (EC2, 捕获 token/logprob → trace)
         → vLLM Qwen3-4B (2×A10G, TP=2)
   → GSM8KReward → rewards=1.0
 → 写 S3 ✓
```
gateway `/sessions` 确认捕获 trace：`{"session_id":"phase2b-q1","trace_count":1}`（训练所需 token 数据已落库）。

### EC2 上的服务命令（复现用）
```bash
# vLLM（必须带工具调用 flag，否则 strands calculator 工具报 400）
sudo docker run -d --name vllm --gpus all --shm-size=16g -p 8000:8000 \
  -v /home/ubuntu/hf:/root/.cache/huggingface vllm/vllm-openai:v0.8.5 \
  --model Qwen/Qwen3-4B-Instruct-2507 --tensor-parallel-size 2 \
  --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-prefix-caching \
  --enable-auto-tool-choice --tool-call-parser hermes

# gateway（host 上，pip install rllm-model-gateway）
python3 -m rllm_model_gateway --host 0.0.0.0 --port 9090 \
  --worker http://localhost:8000/v1 --store memory &

# tunnel
cloudflared tunnel --url http://localhost:9090 --no-autoupdate &
# → 取 https://<random>.trycloudflare.com，base_url = <tunnel>/sessions/{sid}/v1
```

### Phase 2 踩坑
- **vLLM 工具调用**：strands agent 用 calculator → 必须 `--enable-auto-tool-choice --tool-call-parser hermes`，
  否则 vLLM 返回 400 `"auto" tool choice requires ...`。第一次 invoke 就栽在这。
- **us-east-2 SG**：default SG 默认不开 22，需手动开放入站（已放开）。
- **本地访问 trycloudflare 不通**（本地网络/代理挡了），但**不影响 AgentCore**（云端访问 cloudflare）。
  验证应直接用 agentcore invoke，别卡在本地 curl tunnel。

### ⚠️ tunnel URL 是临时的
cloudflared quick tunnel 每次重启换 URL。当前：
`https://geographical-institutions-jonathan-graham.trycloudflare.com`
重启 cloudflared 后要更新 invoke 里的 base_url。Phase 3 训练时由 rLLM 的 `gateway.tunnel=cloudflared` 自动管理。

### A10G(24GB) vs L40S(48GB) 的配置影响
- 单卡显存减半 → max_model_len、batch、gpu_memory_utilization 都要更保守。
- Qwen3-4B (bf16 ~8GB 权重) + LoRA + KV cache + vLLM，单卡 23GB 偏紧 → 倾向 vLLM 用 TP，
  或训练/推理分卡。具体并行度在第 2 步实测定。

---

## Phase 3 — 完整训练 loop（进行中 2026-06-27）

目标：单机 g5.24xlarge collocated，veRL **FSDP**（非 Megatron）跑 GRPO LoRA。
先求"1 step 不 OOM + 能更新 + 权重 sync + reward 回流"，再放到 50-100 step。

### 研究确证（实读 rLLM 仓库, fork agent）
- **跳过 megatron**：veRL 默认 strategy=fsdp；`install_megatron.sh` 是独立脚本，FSDP 不需要 → 避开最大编译坑。
- **依赖**：`rllm[verl]` = verl==0.8.0, vllm==0.22.1, flash-attn==2.8.3, torch>=2.10.0。
  ⚠️ 系统 AMI 是 torch2.7，verl 要 torch2.10 → 用独立 venv（.venv-verl, py3.11）隔离。
  ⚠️ **flash-attn 是最可能卡住的点**（A10G sm_86 + CUDA12.8 wheel/编译）。
- **rLLM 全自动接管 vLLM + gateway + cloudflared**：训练启动前**必须停掉 Phase 2 手动起的
  vLLM/gateway/cloudflared**（抢端口 9090 和 GPU）。设 `rllm.gateway.tunnel=cloudflared` 由 rLLM 自己起 tunnel。
- **权重同步自动**：`actor_rollout_ref.hybrid_engine=True` + `lora.merge=true`，veRL 每步自动 sync LoRA→vLLM。
- **跨区**：训练机 us-east-2，AgentCore runtime + S3 在 us-east-1 → boto3 region 必须指 us-east-1。
- **数据**：`python -m examples.agentcore_math.prepare_gsm8k_data` → 注册 DatasetRegistry 名 `gsm8k_agentcore`。
- **vLLM 工具调用**：override 里要带 `engine_kwargs.vllm.enable_auto_tool_choice=true` +
  `tool_call_parser=hermes` + `tokenizer_mode=slow`（Phase 2 已证必须）。

### 缩小版关键配置（4×A10G，详见 fork 研究 / scripts 草案）
strategy=fsdp, n_gpus=4, lora rank16, hybrid_engine=True,
max_prompt=3072 max_response=1024 max_model_len=4096,
train_batch_size=8 ppo_mini_batch=8 rollout.n=4,
param/optimizer/activation offload=True, gradient_checkpointing=True,
rollout.tp=2 gpu_memory_utilization=0.4 enforce_eager=True,
remote_runtime.backend=agentcore + gateway.tunnel=cloudflared。

### 监控
wandb：需用户提供 WANDB_API_KEY（写入 ~/.aws-resources 或 EC2 wandb login）。
配好后 trainer.logger="['console','wandb']"。

### 安装位置
EC2: ~/rllm + venv ~/rllm/.venv-verl (py3.11)。

### ⭐ 依赖地狱与最终可用栈（2026-06-27，来之不易，务必复用）
**问题链**：
1. `uv pip install rllm[verl]` 默认拉 torch2.10(cu130) → flash-attn 源码编译，撞机器 CUDA12.8 → **编译失败**。
2. flash-attn 2.8.3 预编译 wheel 最高只到 torch2.8，无 torch2.10/2.11。
3. 但 **verl 0.8.0 本身不卡 torch 版本**（torch≥2.10 是 rLLM pyproject 写的）→ 可降级绕开。
4. vllm 0.8.5 硬钉 torch2.6；vllm 0.9.x 钉 torchvision0.21 → 与 torch2.7 冲突。**vllm 0.10.1 兼容 torch2.7**。
5. `transformers>=4.51` 被解析成 5.12.1 → verl import `MistralForSequenceClassification` 失败 → **降到 4.55.4**。

**最终可用版本组合**（全部预编译、零源码编译）：
```
torch==2.7.1+cu128  torchvision==0.22.1+cu128   (--index-url .../whl/cu128)
flash-attn==2.8.3   (预编译 wheel: cu12torch2.7cxx11abiFALSE-cp311)
vllm==0.10.1   verl==0.8.0   transformers==4.55.4   tokenizers<0.22
ray, deepspeed, wandb, agentcore-rl-toolkit>=0.1.2, rllm-model-gateway
```
**安装顺序**（关键）：
```bash
uv venv --python 3.11 .venv-verl && source .venv-verl/bin/activate
# 1) torch 地基
uv pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
# 2) flash-attn 预编译 wheel(不编译)
uv pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.7cxx11abiFALSE-cp311-cp311-linux_x86_64.whl
# 3) 约束文件锁 torch/flash 不被覆盖
printf 'torch==2.7.1+cu128\ntorchvision==0.22.1+cu128\nflash-attn==2.8.3\n' > /tmp/constraints.txt
# 4) verl+vllm
uv pip install verl==0.8.0 vllm==0.10.1 ray --constraint /tmp/constraints.txt --index-strategy unsafe-best-match
# 5) rllm 本体 --no-deps(绕 torch>=2.10 硬约束) + 配套
uv pip install -e . --no-deps
uv pip install "agentcore-rl-toolkit>=0.1.2" rllm-model-gateway wandb deepspeed "transformers==4.55.4" "tokenizers<0.22" --constraint /tmp/constraints.txt
```
冒烟测试全 import OK + torch.cuda.device_count()==4 → 装好。
wandb key 已写 EC2 ~/.bashrc（WANDB_API_KEY）。

### ⭐⭐ vLLM 0.10.1 → 0.11.0 升级（2026-06-27，Phase 3 必需，最终生效栈）
**起因**：rllm-model-gateway 期望 vLLM **0.11+** 在 `choices[0].token_ids` 回传 token id
（`data_process.extract_completion_token_ids` 注释写死 "vLLM 0.11+"）。
vLLM 0.10.1 忽略 `return_token_ids` 字段 → trace 里 `response_ids=0 但 logprobs=107` →
构造训练样本 `Step` 时 pydantic 断言 `length mismatch` → 训练崩。
**升级可行性核实**（升前必查，全部满足）：
- verl 0.8.0 对 vLLM 约束 `>=0.8.5,<=0.12.0` → 0.11.0 在范围内 ✓
- verl 0.8.0 核心不硬钉 torch（只有 sglang extra 要 2.9.1，我们不用）→ torch 自由 ✓
- vllm 0.11.0 钉 **torch==2.8.0** / torchvision0.23.0 / xformers0.0.32.post1
- flash-attn 2.8.3 有 **torch2.8 预编译 wheel**（`cu12torch2.8cxx11abiFALSE-cp311`）→ 不编译 ✓
- 机器 CUDA 12.8 → 全套 cu128 wheel ✓
- ⚠️ vllm 0.11.2+ 钉 torch2.9（更激进，flash-attn 无 torch2.9 wheel）→ **只升到 0.11.0，别更高**。
**升级命令**（在 /tmp 下跑，避开 rllm pyproject 的 override-dependencies）：
```bash
VPY=~/rllm/.venv-verl/bin/python
uv pip install --python $VPY torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python $VPY --no-deps --reinstall-package flash-attn \
  https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.8cxx11abiFALSE-cp311-cp311-linux_x86_64.whl
printf 'torch==2.8.0+cu128\ntorchvision==0.23.0+cu128\nflash-attn==2.8.3+cu12torch2.8cxx11abifalse\nnumpy==2.2.6\ntransformers==4.55.4\n' > /tmp/constraints28.txt
uv pip install --python $VPY vllm==0.11.0 --constraint /tmp/constraints28.txt --index-strategy unsafe-best-match
```
**升级后生效栈**：torch2.8.0 / torchvision0.23.0 / flash-attn2.8.3(torch2.8) / vllm0.11.0 /
torchaudio2.8.0 / xformers0.0.32.post1 / verl0.8.0 / transformers4.55.4 / numpy2.2.6。

---

## Phase 3 — 完整训练 loop（✅ 1-step 冒烟成功 2026-06-27）

**成功标准全部达成**：4×A10G FSDP collocated，veRL GRPO LoRA，1 train step 不 OOM +
reward 真实回流 + LoRA 权重 sync 到 vLLM。**整条 online RL 闭环点亮。**

### 训练脚本
`examples/agentcore_math/train_agentcore_math_fsdp.sh`（已存仓库 017 目录）。
官方 megatron 8×A100 脚本改造为 FSDP 4×A10G：去 megatron、`fsdp_config.{param,optimizer}_offload=True`、
n_gpus=4、TP=2、batch 8、max_prompt3072/resp1024/model_len4096、gpu_mem_util0.6、
gradient_checkpointing、`rllm.gateway.tunnel=cloudflared`、logger 带 wandb。
`STEPS=1` 跑单步冒烟（`trainer.total_training_steps=1`），`STEPS=0` 跑完整 epoch。
启动：`STEPS=1 bash examples/agentcore_math/train_agentcore_math_fsdp.sh`。

### 启动前置（关键）
```bash
export VLLM_USE_V1=1          # verl 0.8 用 V1 AsyncLLM，环境默认 False 会崩
export WANDB_API_KEY=<key>    # 已在 ~/.bashrc
set -a && source examples/agentcore_math/.env && set +a   # AGENTCORE_AGENT_ARN/S3_BUCKET/region
```
rLLM 自动接管 vLLM + gateway:9090 + cloudflared，**启动前确保无 Phase 2 手动残留进程**。

### 冒烟实测结果（step:1，wandb run z0nqg70o，project agentcore-math）
- **reward/default/mean = 0.75**（8 题 ×4 = 32 trajectory，全 env_done，无 timeout/error）
- solve_all 0.375 / solve_partial 0.625；GRPO advantage std 0.79（±1.732）
- actor 更新：pg_loss 0.601，grad_norm 472.9，update_weights 10.4s（LoRA→vLLM sync ✓）
- **token 对齐**：rollout_probs_diff=0，pearson_corr=1.0（vLLM0.11 升级解决了 token_ids 坎）
- 显存峰值 18.7/21GB reserved（24GB 卡安全），throughput 218 tok/s，step 66s
- 数据见 `results/smoke_step1_metrics.txt`。

### Phase 3 踩坑全记录（按攻克顺序，6+1 个）
1. **缺 polars**：dataset 加载依赖 → `uv pip install polars`（在 /tmp 下跑避开 override）。
2. **VLLM_USE_V1=False**：verl 0.8 用 V1 AsyncLLM 引擎 → `export VLLM_USE_V1=1`。
3. **numpy 被拉到 2.4.6**：numba 要 `numpy<2.3`，但 **rllm pyproject `[tool.uv] override-dependencies`
   强拉 `numpy>=1.26`** → 在 rllm 目录下跑 uv 必还原成最新。
   解法：`cd /tmp && uv pip install --python <venv>/bin/python numpy==2.2.6 --no-deps`。
4. **KV cache 无显存**：`gpu_memory_utilization=0.4` 太低（4B 权重吃掉后 KV 无空间）→ 提到 **0.6**。
5. **gateway 不认 `--model`**：装了 PyPI `rllm-model-gateway==0.1.0`（旧），但 rllm pyproject 指定
   `path=./rllm-model-gateway editable`（带 `--model`/`--cumulative-token-mode`）。
   解法：`uv pip install --no-deps --reinstall-package rllm-model-gateway -e ~/rllm/rllm-model-gateway`。
6. **AgentCore AccessDeniedException**：EC2 `~/.aws/credentials` 是临时凭证，已过期；instance profile
   是安全监控角色无权调 bedrock-agentcore。解法：把本地长期 IAM user key（`iam-for-bedrock-access`，
   `[bedrock]` profile，无 session token 不过期）经 ssh stdin 写入 EC2 `~/.aws/credentials`。
7. **token_ids length mismatch**：见上 vLLM 0.10.1→0.11.0 升级（⭐⭐ 节）。

### 下一步（未做）
- 完整 50~100 step 训练：`STEPS=0`（跑满 1 epoch）或设 `trainer.total_training_steps=50`。
  ⚠️ `total_training_steps=N` 训练结束会触发对**全量 test 集 1319 题**的 final validation（~30min/次），
  冒烟时已观察到；正式训练可接受，或调 `trainer.test_freq` / 缩小 val 集。
- 实例 g5.24xlarge @ us-east-2（tag `Experiment=017_agentcore_online_RL`）冒烟后已 kill 进程、GPU 释放，
  **实例仍 running**，按需 stop 或继续正式训练。

---

## Phase O — OfficeBench 工具调用 online RL（进行中 2026-06-27）

目标：把 GSM8K 闭环切到 OfficeBench（300 办公任务，训多工具调用/跨应用编排）。详见
`officebench_training_plan.md`。训练侧链路全复用 Phase 3 栈，新增数据/重镜像/训练脚本。

### 基础设施（已就绪）
- **S3 数据**：`preprocess.py` 上传 300 subtask → `s3://agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1/officebench/`
  （每 subtask 一个 config.json + 每 task 一个 testbed.tar.gz + manifest.json）。OfficeBench 仓库 clone 在 /tmp。
- **ECR 镜像**：`agentcore/rl:office-v1`（524MB，含 LibreOffice/Tesseract/ImageMagick/21工具）。
  用 finch 脚本构建：`build_image_and_push_to_ecr_finch.sh --dockerfile=.../strands_officebench_agent/Dockerfile
  --context=.../strands_officebench_agent --additional-context=toolkit=. --tag=office-v1`。
  toolkit 根 .env 需 AWS_REGION/AWS_ACCOUNT/ECR_REPO_NAME=agentcore/rl。
- **AgentCore office runtime**：`arn:aws:bedrock-agentcore:us-east-1:<AWS_ACCOUNT_ID>:runtime/officebench_rl-9hrX718tLD`
  （`deploy.py` + config.toml，networkMode PUBLIC，复用 math 的 runtime role）。
- **runtime role 权限**（在 AmazonBedrockAgentCoreSDKRuntime-us-east-1-4a9245d104）：
  RLToolkitS3Access（GetObject/PutObject `/*` + **ListBucket** on bucket）、RLToolkitBedrockInvoke（bedrock:InvokeModel）。

### 数据划分（results/officebench_split.json，make_split.py 生成）
分层 80/20，按 category 分层、按 task_id 切（防 subtask 泄漏），剔除 bug 任务 1-10、1-14，seed=42。
**train 234 subtask（132 task）/ test 56 subtask（33 task）**。cat 分布 train 16/37/79、test 4/9/20。

### 训练侧脚本（EC2 ~/rllm/examples/agentcore_office/，本地仓库也存档）
- `prepare_officebench_data.py`：读 split.json，注册 `officebench_train/test`，
  每条样本 = `{task_uri, testbed_uri, task_id, subtask_id}`（训练侧 payload 契约，原样发 AgentCore）。
- `train_agentcore_office_verl.py`：load `officebench_train/test` + AgentTrainer。
- `train_agentcore_office_fsdp.sh`：复制 math fsdp，改 dataset/office ARN/长度/timeout。
  关键参数：max_prompt=8192 max_response=2048 max_model_len=12288，
  **ppo_max_token_len_per_gpu=10240**（必须 ≥ 最长序列），gpu_memory_utilization=0.5，
  session_timeout=600，**test_freq=-1（关 validation，见踩坑）**，project=agentcore-office。
  `.env`：AGENTCORE_AGENT_ARN=office runtime，S3_BUCKET，region us-east-1。

### 进度
- ✅ Phase O-1 部署冒烟：1-1/0 PASS reward=1.0（4s，真多轮工具调用）；c2 任务 42.7s/18 工具调用/status200。
- ✅ Phase O-2 训练 1-step 冒烟：rollout 32/32 + actor update（无 OOM）+ update_weights done（LoRA sync）。
- 🔄 Phase O-3 短训 20 step：STEPS=20，wandb run e897buoz（project agentcore-office）。
- 🔄 Haiku 4.5 基线：benchmark.py 对 test 集 56 题（--split_file + --split test，走 Bedrock，与训练并行）。

### Phase O 踩坑（office 特有）
1. **testbed 403 而非 404**：容器 setup_testbed 对无 testbed 的任务（如纯日历 1-1）head_object 缺失对象，
   S3 无 ListBucket 权限时返回 **403**（而非代码预期的 404）→ 优雅降级没触发 → 崩。
   解法：runtime role **加 s3:ListBucket**（bucket 级），缺失对象才正确返回 404。
2. **actor update OOM**：office max_prompt/response 是 math 的 ~2.7×，24GB 卡训练阶段（FSDP+梯度+激活）撑爆。
   降 gpu_memory_utilization 0.6→0.5 给训练腾显存。
3. **ppo_max_token_len_per_gpu 断言**：降太狠（6144）触发
   `max_token_len must be >= max_seq_len（got 6144 vs 8229）`——该值必须 ≥ 单条最长序列。设 10240。
4. **final validation OOM**：`test_freq>0` 时训练**结束**触发 final validation，把整个 test 集作为一个 batch
   发推理引擎 → 56 题并发长 context OOM。解法：**test_freq=-1 完全关 validation**，评测改用独立 benchmark.py。
5. **vLLM 400 context exceeded**（非致命）：个别 office 多轮对话累积略超 max_model_len（如 12325>12288），
   该轮请求被拒、agent 那轮无回复，但不中断训练。可调大 max_model_len 或接受少量噪声。

### benchmark.py 增强（本地改）
加 `--split_file <split.json> --split test|train` 参数，按 split 过滤评测范围（用于训练前后对 test 集对比）。

---

## Phase O-32B — 升级到 Qwen3-32B @ p4d.24xlarge（进行中 2026-06-27）

### 背景
4B @ g5.24xlarge(24GB卡) 训练 office 反复 OOM（actor update 撞长序列）。根因是单卡显存不足 +
office 长上下文。决定换大卡大模型。

### 机型决策过程（容量探测实录）
- 想直接训 **Qwen3.6-27B**：核实后发现是 2026-04 新架构 `qwen3_5`（Gated DeltaNet 线性注意力+多模态+MTP），
  要 **vllm≥0.19**，而 **veRL 0.8 训练侧不支持该架构**、且与我们 torch2.8 栈互斥 → **训练跑不了**（非显存问题）。
  → 改用标准架构 **Qwen3-32B**（`Qwen3ForCausalLM`，与已验证的 4B 同系，零栈风险）。
- **p4de.24xlarge（A100 80GB）**：us-east-1/us-west-2 dry-run 绿但**实起全无容量**。
- **p4d.24xlarge（A100 40GB）**：us-east-1/us-west-2 也无容量 → **us-east-2 抢到** ✅。
- 备选 g6e.12xlarge（L40S 48GB×4）us-east-1 四 AZ 全有容量（未用，留作 fallback）。

### 新实例
- **p4d.24xlarge @ us-east-2a，8×A100-SXM4-40GB（320GB，NVLink）**，磁盘 500GB，DLAMI <AMI_ID>。
- tag `Experiment=017_agentcore_online_RL` Name=017-office-32b-p4d。**跨区**：训练机 us-east-2，
  office runtime + S3 在 us-east-1（boto3 region=us-east-1，与 Phase 3 跨区一致）。
- g5.24xlarge（4B 实验机）已 **terminate**。

### 依赖栈（p4d 重装，同 torch2.8 配方，A100 sm_80 兼容）
torch2.8.0+cu128 / flash-attn2.8.3(torch2.8 wheel) / vllm0.11.0 / verl0.8.0 / transformers4.55.4 /
numpy2.2.6 / gateway(本地 editable)。8 卡可见。
⚠️ 安装关键：**flash-attn 和最终 numpy 都要在 /tmp 下 `--no-deps` 装**（避开 rllm pyproject 的
`extra-build-dependencies`/`override-dependencies` 干扰）；numpy 单独最后装（verl 要<2.0 但 numba 要<2.3 → 强装2.2.6）。

### 32B 训练脚本：examples/agentcore_office/train_agentcore_office_32b_fsdp.sh
关键改动 vs 4B：MODEL=Qwen/Qwen3-32B，n_gpus=8，**rollout.tp=2**（32B 单卡40GB放不下推理），
lora rank32，max_prompt8192/resp2048/model_len12288（A100 比 24GB 宽），ppo_max_token_len=12288，
gpu_mem_util0.55，train_batch16，test_freq=-1（关 validation），project=agentcore-office。

### 状态
- ✅ 依赖栈装好（8 卡），dataset 注册（train234/test56），cloudflared+wandb 配好，AWS 凭证写入。
- 🔄 预下载 Qwen3-32B（~64GB）。
- ⏭️ 待下载完 → 1-step 冒烟 → 短训。

### Haiku 4.5 基线（已出，test 56 题）
总体 71.4%（1-app 66.7% / 2-app 85.0% / 3-app 61.9%）。作为训练后对比基准。

---

## Phase O-14B — 降到 Qwen3-14B 跑通 (✅ 1-step 冒烟成功 2026-06-27)

### 为什么不是 32B
32B 在 8×A100-40GB collocated 结构性 OOM:vLLM推理权重+FSDP actor权重在单卡40GB叠加,
各环节(vLLM加载/KVcache/actor update/权重同步)轮流爆。**rllm AgentCore 训练路径硬锁 collocated**
(`agent_workflow_trainer.py:101` assert hybrid_engine=True),不能分卡。→ 降 14B(collocated 能稳跑的最大实用尺寸)。

### ⭐ 攻克 OOM 死结的最终配方 (14B @ 8×A100-40GB collocated)
反复试错才定下来,核心是几个旋钮的平衡:
- **rollout TP=8**(关键!): 14B 推理权重摊薄到每卡 ~2GB,给权重同步腾出空间。
  TP=2/4 时 vLLM 单卡占 16GB,权重同步瞬间与 actor 20GB 叠加必爆。TP=8 是解 update_weights OOM 的钥匙。
- **max_prompt=5120 / max_response=1536**(最长序列 ~6656),压低 actor backward 显存。
- **ppo_max_token_len_per_gpu=8192**: 必须 ≥ 最长序列(否则 AssertionError),又要够小控显存。8192 是平衡点。
- **train_batch=8 / ppo_mini_batch=8 / gpu_memory_utilization=0.6**。
- 其余: lora rank32, n_gpus=8, gradient_checkpointing, param/optimizer offload, test_freq=-1。
脚本: `examples/agentcore_office/train_agentcore_office_14b_fsdp.sh`。

### OOM 调试踩坑顺序(都试过)
1. gpu_mem 0.55→0.35→0.45→0.6→0.7: 单调 gpu_mem 无解(0.5 KVcache不够 / 0.7 权重同步爆)。
2. update_weights_bucket_megabytes: **该参数在 verl0.8 RolloutConfig 不存在**,加了报 TypeError。放弃。
3. TP=2→4→8: **TP=8 才解决权重同步 OOM**(摊薄推理权重)。
4. TP=8 后转为 actor update OOM → 降 batch16→8 + token_len → 但 token_len<最长序列触发 AssertionError。
5. 最终: 降 max_prompt 缩短序列(5120) + token_len=8192 + TP=8 + batch8 → **EXIT_CODE=0 跑通**。

### 1-step 冒烟结果 (EXIT_CODE=0)
- **critic/score/mean = 0.103**(14B 初始 office reward 10.3%, 是 4B 的 3.1% 的 3 倍)。
- 2× update_weights done(初始 + step末尾 LoRA→vLLM sync 完整闭环)。
- timing_s/update_actor=94s(14B 8卡 FSDP backward, 慢但稳)。solve_none=0.875。
- 个别 rollout(3个)因 office 长任务 context 超限失败(reward=0,非致命)。

### 实例
p4d.24xlarge @ us-east-2a (<EC2_IP>), 8×A100-40GB。模型 Qwen3-14B(已下到 ~/.cache/huggingface)。
也下了 Qwen3-32B(62G,因 collocated OOM 未用,留着)。跨区: runtime/S3 在 us-east-1。

### 进行中
- 🔄 Phase O-14B 短训 20 step: STEPS=20, wandb project agentcore-office。看 reward 趋势。
- Haiku 4.5 基线(test 56题)71.4% 作对比。

---

## Phase O-8B — 自主训练架构 (2026-06-28, 用户断网期间 EC2 自主运行)

### 为什么 8B
14B 在 40GB 卡 collocated 长序列 actor update 间歇 OOM(能跑5步撞长序列批次就崩),不稳定。
8B actor 显存需求更小 → 改 8B。**关键稳定配方: max_model_len=ppo_max_token_len=7168**
(prompt5120+resp2048, 序列硬上限自洽), TP=8(推理权重摊薄), gpu_mem=0.6, batch8, lora rank32。
8B 在此配方下稳跑(突破了 14B 反复崩的位置)。

### 自主运行架构(双 tmux, 脱离 SSH, 断网不停)
- **tmux `sup`** (auto_train_8b.sh): 自愈训练. resume_mode=auto + save_freq=5,
  崩溃自动从最新 ckpt 续训, 跑满 total_training_steps=40 或 6h 硬上限停。
- **tmux `sentinel`** (sentinel_8b.sh): 独立哨兵. 监视 sup 结束 → 自动跑 finalize_8b.sh:
  上传最新 ckpt(LoRA adapter + actor 分片) + 训练日志 + 脚本到
  `s3://agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1/checkpoints/officebench-8b-<日期>/`, 写 ~/rllm/FINALIZE_DONE 标记。
- 监控: wandb project agentcore-office (8B run nc4mi440), critic/score/mean。

### 课程学习(未实施, 留作后续改进)
用户提出: OOM 主因是难任务(three-app)长序列, 且 reward 稀疏(solve_none 0.875)也源于难任务多。
课程学习(category1→1+2→全量分阶段续训)可同时缓解 OOM(前期短序列)和稀疏(易任务先建信号)。
方案: 注册 3 个 category 分层 dataset, 分段从 ckpt 续训。待 8B 基线出来后评估是否上。

### 用户回来后的收尾(待执行)
1. 核对 sup/sentinel 状态 + FINALIZE_DONE + S3 是否有 ckpt。
2. 拉 wandb/日志的 score 趋势, 判断合理性(链路健康+趋势)。
3. 写 results/analysis.md (含 8B 训练曲线 + Haiku 71.4% 基线对比 + 全程 OOM 调试结论)。
4. terminate p4d 实例 i-? @ us-east-2 (<EC2_IP>) 止血。
   ⚠️ 32B/14B/8B 模型已下到 HF 缓存, 实例 terminate 后丢失, 复现需重下(runbook 有命令)。

---

## Phase O-Math — 改训 GSM8K，成功！(2026-06-28 收尾)

OfficeBench 诊断出"任务太难→GRPO信号稀疏(effective仅15-25%)→reward不上升"后,改训 **GSM8K**
(单步推理+calculator,reward可验证,难度适中),同一 Qwen3-8B 从原始base起训。

### 结果:教科书级上升收敛曲线 ✅
- script: train_agentcore_math_8b_fsdp.sh (TP=8,n=8,lr=5e-6,max_model_len=4096), wandb run tkqdjl3g
- **critic/score: 0.31(起步) → 0.95(末段10步均值)**, 全程均值0.881, 4次达1.0
- **solve_none: 0.18 → 0.04**(末段几乎全解出)
- **effective fraction = 0.75**(office仅0.15-0.25) ← 信号充足的关键
- 31步,0 OOM,0崩溃。应用户要求step31停止收尾。

### 决定性反证
同一套链路: GSM8K reward顺利上升 vs OfficeBench震荡无上升 → 证明 office 学不动是
**任务难度问题(8B解题率低)**,不是链路/超参问题。online RL 框架完全有效。

### 收尾动作(已执行)
1. ✅ analysis.md 完整(results/analysis.md): 含 math 成功曲线 + office 诊断 + Haiku 基线对比
2. ✅ 脚本+日志归档本地(train_agentcore_math_8b_fsdp.sh, results/p4d_runs/math_8b_train.tail.log)
   + S3(s3://.../checkpoints/gsm8k-8b-20260628/{config,logs}/)
3. ✅ 模型权重ckpt应用户要求未保留(只存脚本+日志可复现)
4. ✅ **EC2 p4d.24xlarge <INSTANCE_ID> @ us-east-2 已 terminate**(止血)
5. ✅ AgentCore runtime(math rl_app-10GyZj7qsj / office officebench_rl-9hrX718tLD)+ S3数据 + ECR镜像保留,可快速复现
