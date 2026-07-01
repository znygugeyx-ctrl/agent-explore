# OfficeBench Online RL 训练计划

> 目标：把 017 已跑通的 GSM8K online RL 闭环切换到 **OfficeBench**（300 个办公自动化任务，
> 训练模型的**多工具调用 / 跨应用编排能力**）。训练侧链路（4×A10G FSDP + veRL GRPO LoRA +
> gateway + cloudflared）完全复用 Phase 3 已验证成果，主要新增工作在数据、容器镜像、训练侧脚本。

状态：**计划阶段，未动手建资源**。先与用户对齐决策点（见 §6）再执行。

---

## 0. 复用 vs 新建一览

| 组件 | GSM8K（现状） | OfficeBench（目标） | 工作量 |
|---|---|---|---|
| 训练机 / GPU | g5.24xlarge 4×A10G @ us-east-2（running） | 同 | 复用 |
| 依赖栈 | torch2.8 / vllm0.11 / verl0.8 / flash-attn2.8.3 | 同 | 复用 |
| gateway / cloudflared / wandb | 已通 | 同 | 复用 |
| AgentCore Runtime | math 的 `rl_app-10GyZj7qsj` | **新建** office runtime（不同镜像/工具/依赖） | 新建 |
| ECR 镜像 | math（轻量） | **新建** 重镜像（LibreOffice+Tesseract+ImageMagick+apps） | 新建 |
| S3 数据 | GSM8K HF dataset | **新建** `s3://.../officebench/`（preprocess 上传） | 新建 |
| reward | GSM8KReward（exact+format） | **现成** OfficeBenchReward（9 检查，二值） | 复用（example 自带） |
| 数据集字段契约 | `{prompt, answer}` | **`{task_uri, testbed_uri}`** | 改造 |
| 训练侧 prepare/train 脚本 | `examples/agentcore_math/*` | **新写** office 版（rllm/examples 无现成） | 新写 |

**关键认知**：rLLM 仓库**没有 officebench 训练 example**（只有 toolkit 侧的部署/评测）。训练侧的
`prepare_*.py` + `train_*.sh` 需照 `agentcore_math` 模板自己写。

---

## 1. Benchmark 与数据结构

- **OfficeBench**：300 个任务，6 类 app（calendar/email/excel/word/pdf/ocr），按协作 app 数分 3 档：
  - category 1（single app）：93 任务
  - category 2（two apps）：95 任务
  - category 3（three apps）：112 任务
- 每个任务 `task_id`（如 `1-1`）下含多个 **subtask**（`0,1,...`），共享一份 testbed。
- 训练/评测的**最小单元是 subtask**（`{task_id}/{subtask_id}`）。300 是"任务目录"数，subtask 总数更多
  （preprocess `--dry_run` 可得确切数，计划执行时统计）。
- 已知 2 个 ground-truth bug 任务（`1-10/3`、`1-14/2`）恒失败，算分/分析时剔除。

### 验证方式（reward）
`reward.py::OfficeBenchReward` — 纯结果导向，只查 `/testbed` 磁盘最终文件状态，**不用 LLM judge**：
- 9 个检查函数（file_exist / contain / excel_cell_value / exact_match / calendar_no_overlap / diff 等）。
- 任务 `config.json` 的 `evaluation` 列表逐项检查，**全过 → reward=1.0，任一失败/异常 → 0.0**（二值，适配 GRPO）。

---

## 2. 数据划分方案（训练 / 测试）

### 设计原则
- OfficeBench 原生**只有一个评测集**（300 任务无官方 train/test split）。online RL 需要自己切。
- 必须 **按 category 分层**切分，保证 train/test 在 3 档难度上分布一致（否则 reward 信号有偏）。
- 切分**以 task_id 为单位**（而非 subtask），避免同一任务的不同 subtask 跨进 train 和 test 造成泄漏
  （同任务 subtask 共享 testbed + 高度同构）。
- 剔除 2 个已知 bug 任务。

### 推荐切分：分层 80/20（按 task_id）
| category | 总 task | train (~80%) | test (~20%) |
|---|---|---|---|
| 1 (single) | 93 | ~74 | ~19 |
| 2 (two) | 95 | ~76 | ~19 |
| 3 (three) | 112 | ~90 | ~22 |
| **合计** | **300** | **~240** | **~60** |

- 固定随机种子（如 42）做分层抽样，切分清单落盘 `results/officebench_split.json`（task_id 级，可复现）。
- 训练用 train 集对应的所有 subtask；测试用 test 集对应的所有 subtask。
- 实现：preprocess 把 300 任务全量上传 S3 后，在**训练侧 prepare 脚本**里按 split 清单
  过滤出 train/test 的 subtask，分别注册成 `officebench_train` / `officebench_test` 两个 DatasetRegistry。

> 备选方案（先不采用）：若想最大化训练数据、且接受 test 与原 leaderboard 不可比，也可全 300 训练、
> 另留固定 60 做 held-out。默认走分层 80/20，干净可复现。

### 数据集字段契约（关键）
训练侧 `agentcore_runtime.py` 把每个 task dict **原样**作为 payload 发给 AgentCore（`payload=sub.task`）。
officebench `rl_app.py` 的 `InvocationRequest` 要求：
```python
{"task_uri": "s3://bucket/officebench/1-1/0/config.json",
 "testbed_uri": "s3://bucket/officebench/1-1/testbed.tar.gz"}
```
→ prepare 脚本注册 dataset 时，每条样本就是上面这个 dict（外加 task_id/subtask_id 便于分组）。
`base_url`/`model_id`/`sampling_params` 由训练引擎在 invoke 时注入 `_rollout`，**不在 dataset 里**。

---

## 3. 基础设施部署步骤

> 区域决策见 §6。下面以"office runtime 建在 us-east-1（与 math 同区，沿用现有 role/凭证）"为默认假设书写。

### 3.1 准备 OfficeBench 源数据（本地，一次性）
```bash
git lfs install   # OfficeBench testbed 用 LFS
git clone https://github.com/zlwang-cs/OfficeBench /path/to/OfficeBench
```

### 3.2 上传任务到 S3（一次性）
```bash
cd agentcore-rl-toolkit/examples/strands_officebench_agent
python preprocess.py --dry_run --officebench_dir /path/to/OfficeBench   # 先统计 subtask 数
python preprocess.py \
    --officebench_dir /path/to/OfficeBench \
    --s3_bucket agentcore-rl-<AWS_ACCOUNT_ID>-us-east-1 \
    --s3_prefix officebench
```
产出 `s3://.../officebench/{task_id}/{subtask}/config.json` + `{task_id}/testbed.tar.gz` + `manifest.json`。
（复用现有 math 的 bucket，仅加 `officebench/` 前缀。）

### 3.3 构建重镜像并推 ECR（本机 finch，linux/arm64）
officebench Dockerfile 装 LibreOffice + Tesseract + ImageMagick + clone OfficeBench apps → 镜像比 math 大很多。
用我们已有的 finch 脚本（支持 `--additional-context`）：
```bash
cd agentcore-rl-toolkit
# .env 需含 AWS_REGION / AWS_ACCOUNT / ECR_REPO_NAME（office 专用 repo）
./scripts/build_image_and_push_to_ecr_finch.sh \
  --dockerfile=examples/strands_officebench_agent/Dockerfile \
  --context=examples/strands_officebench_agent \
  --additional-context=toolkit=. \
  --tag=v1
```
⚠️ 风险点：①镜像体积大、构建慢；②apt 装 LibreOffice 在 arm64 上偶有源问题；③首次冷启动慢。

### 3.4 部署到 AgentCore Runtime
```bash
cd examples/strands_officebench_agent
cp config.example.toml config.toml   # 填 region / image_uri / execution_role_arn
python deploy.py                       # 产出 agent_arn → 回填 config.toml
```
- execution_role 需要：S3 读（取 task/testbed）、S3 写（写 rollout 结果）。
- 若用 Bedrock 当评测基线，role 还需 bedrock invoke（训练时用 vLLM 则训练阶段不需要）。

### 3.5 给 runtime role 加 S3 权限
沿用 math 的做法（`aws iam put-role-policy ... RLToolkitS3Access`），确保覆盖 officebench 前缀读 + 结果写。

### 3.6 部署冒烟（关键，建训练前必做）
```bash
python benchmark.py --exp_id smoke --limit 1 --base_url <vLLM> --model_id Qwen/Qwen3-4B-Instruct-2507
```
确认 S3 出现 `{"rewards":...}` 且对话历史含真实工具调用 → runtime 健康。

---

## 4. 训练侧改造（rllm/examples 新写）

照 `agentcore_math` 模板，在 `rllm/examples/agentcore_office/` 新建：

1. **`prepare_officebench_data.py`**
   - 读 S3 `manifest.json` 拿全部 (task_id, subtask)。
   - 按 §2 的 split 清单分层切 train/test（剔 2 个 bug 任务）。
   - 每条样本注册为 `{task_uri, testbed_uri, task_id, subtask_id}`。
   - 注册 `officebench_train` / `officebench_test` 两个 dataset。

2. **`train_agentcore_office_fsdp.sh`**
   - 直接复制 Phase 3 的 `train_agentcore_math_fsdp.sh`，改：
     - dataset 名 → `officebench_*`
     - `AGENTCORE_AGENT_ARN` → office runtime 的 ARN（新 `.env`）
     - `experiment_name` → `exp017-officebench-fsdp-4xa10g-4b`
   - ⚠️ **长度需调大**：office 多轮 + 工具 schema（21 个工具）+ 文件内容 →
     prompt/response 远长于 GSM8K。初值建议 `max_prompt=8192 max_response=2048 max_model_len=12288`，
     1-step 冒烟时按显存/截断率实测收敛。
   - ⚠️ **session_timeout 调大**：office rollout 比 math 慢（多轮+LibreOffice 转换），
     建议从 300s 提到 600s+。
   - 其余（FSDP offload / TP=2 / VLLM_USE_V1=1 / gateway.tunnel=cloudflared）照搬。

3. **`train_agentcore_office_verl.py`**：照 math 版改 dataset 名即可。

---

## 5. 训练与验证流程（分阶段，断点恢复）

遵循 CLAUDE.md 的 pilot→full 两阶段：

### Phase O-1：部署冒烟（§3.6）
- 1 task invoke 通 + S3 出 reward + 有工具调用。

### Phase O-2：训练 1-step 冒烟
- `STEPS=1` 跑单步：不 OOM + reward 回流（非全 0/全 1）+ 权重 sync + token 对齐。
- 重点观察：截断率（prompt/response clip_ratio）、rollout 超时率、单 step 时长。
- 据此定 max_len / batch / timeout 的最终值。

### Phase O-3：短训验证（10~20 step）
- 看 reward 曲线是否有上升趋势、advantage 是否非退化、显存稳定。
- wandb 全程（project 复用 `agentcore-math` 或新建 `agentcore-office`）。

### Phase O-4：正式训练 + 评测
- `STEPS=0`（或 `total_training_steps=N`）跑 50~100 step。
- ⚠️ 训练结束触发全量 test 集 final validation（officebench test ~60 任务对应的 subtask，
  比 GSM8K 1319 快），可接受；或调 `test_freq`。
- **训练前后各跑一次 `benchmark.py`**（分 category 出分），对比训练增益：
  ```bash
  python benchmark.py --exp_id office_pre  --base_url <vLLM-base>    # 训练前
  python benchmark.py --exp_id office_post --base_url <vLLM-trained> # 训练后
  ```
- 结果落 `results/`（rollouts.jsonl + summary.json），写 `analysis.md`。

---

## 6. 决策（已与用户对齐 2026-06-27）

1. **AgentCore runtime 区域**：✅ **us-east-1**（与 math 同区，沿用现成 role/凭证/bucket）。
2. **数据划分**：✅ **分层 80/20**（按 category 分层、按 task_id 切，train~240/test~60）。
3. **训练规模**：✅ **先到短训为止**——做到 Phase O-3（10~20 step 验证 reward 趋势），拿到曲线后再回来定正式规模。
4. **基线对照**：✅ **训练的同时并行跑 Bedrock Claude Haiku 4.5 基线**（用 benchmark.py 对 test 集，
   需 runtime role 加 bedrock invoke 权限；与训练 GPU 互不抢占，因走 Bedrock 而非 vLLM）。

---

## 7. 主要风险

- **重镜像构建**（LibreOffice/Tesseract on arm64）：最可能卡住的新环节，build 慢且可能踩 apt 源/依赖坑。
- **上下文长度**：21 个工具 schema + 多轮 + 文件内容，易超 max_model_len → 截断 → reward 噪声。需冒烟实测。
- **rollout 慢 / 超时**：LibreOffice 文档转换耗时，session_timeout 要给足，否则大量 timeout→reward=0。
- **reward 稀疏**：二值 + 全检查通过才给 1.0，three-app 任务难 → 训练早期可能 reward 多为 0，
  GRPO 组内无区分度（solve_none）。可考虑先用 category 1/2 暖身或分阶段课程。
