# Exp 012 v4：公平 Mask vs Remove 实验（修订版）

## 核心假设（两个独立 H）

**H1（准确率）**：工具可用性提示（Remove / Mask）能提高模型在大工具池中选出正确工具的准确率。

**H2（缓存命中率 / TTFT）**：Manus 核心假设——保持 prompt prefix 稳定（不动态修改工具列表）能保留 KV cache，降低 TTFT。尤其对长对话效果显著——turn 越多，缓存节省的 token 数越大。

---

## 策略设计（4 种）

| 策略 | 工具展示 | 每轮变化？ | Prefix 稳定？ | 测 H1 | 测 H2 |
|---|---|---|---|---|---|
| `all` | 60 工具，无限制 | ❌ | ✅ | 基准 | 基准 |
| `remove_dynamic` | 每轮 5 工具（当前组） | ✅ 变化 | ❌ | ✅ 期望最优 | ❌ 期望最差 |
| `mask_logit` | 60 工具 + 组级 token 封锁 | ❌ | ✅ | ✅ 期望同 remove_dynamic | ✅ |
| `mask_hint` | 60 工具 + 用户消息注入可用工具名 | ❌ | ✅ | ✅ 软提示 | ✅ |

**删除 remove_static**：不测试 prefix 稳定性，无独立假设，与 all 无区分度。

### mask_hint 设计（替代旧 mask_desc）

旧 mask_desc 修改工具描述（`[UNAVAILABLE]`），导致工具定义每轮变化，prefix cache 全部失效，与 remove_dynamic 无区别。

新 mask_hint：工具定义完全不动，每轮用户消息前追加可用工具提示：
```
[Available tools this turn: math_add, math_gcd, math_sqrt, math_factorial, math_power]

Water boils at 100°C. At what temperature does it boil in Fahrenheit?
```
- System prompt + 60 工具定义（~6K tokens）完全不变 → prefix cache 保留 ✅
- 仅用户消息文本变化（几十 tokens），不影响大 prefix 命中
- 更贴近真实场景（MCP routing hint 风格）

### 强化系统提示（替代 tool_choice 强制）

```
You are a helpful assistant with access to a set of tools.
For EVERY user request, you MUST call exactly one tool to answer.
Do NOT compute answers mentally or from memory — always invoke a tool.
Do NOT write a plain text response instead of a tool call.
Even if you know the answer, you must still call the appropriate tool.
```

---

## 任务设计（15 个任务，3–10 轮）

目标：
- 短任务（3-4 轮）：快速验证基本准确率
- 中任务（5-6 轮）：主力测试
- 长任务（8-10 轮）：专门测试缓存累积效果，turn 越深缓存节省越大

总计约 15 × 平均 6 轮 ≈ 90 个 turn / 策略，统计显著性充足。

| # | 任务 ID | 序列（M=math, T=text, U=unit, C=code） | 轮数 |
|---|---|---|---|
| 1 | chain_M_T_U | M→T→U | 3 |
| 2 | chain_C_M_T_U | C→M→T→U | 4 |
| 3 | chain_T_C_M | T→C→M | 3 |
| 4 | chain_U_T_C | U→T→C | 3 |
| 5 | chain_M_U_T_C | M→U→T→C | 4 |
| 6 | chain_M_T_U_C_M_T | M→T→U→C→M→T | 6 |
| 7 | chain_C_U_T_M_C | C→U→T→M→C | 5 |
| 8 | chain_T_M_C_U_T | T→M→C→U→T | 5 |
| 9 | chain_U_C_M_T_U_C | U→C→M→T→U→C | 6 |
| 10 | chain_M_C_T_U_M_C_T | M→C→T→U→M→C→T | 7 |
| 11 | chain_T_U_M_C_T_U_M_C | T→U→M→C→T→U→M→C | 8 |
| 12 | chain_C_M_T_U_C_M_T_U_C | C→M→T→U→C→M→T→U→C | 9 |
| 13 | chain_U_M_C_T_U_M_C_T_U_M | U→M→C→T→U→M→C→T→U→M | 10 |
| 14 | chain_M_T_C_U_M_T_C_U_M_T | M→T→C→U→M→T→C→U→M→T | 10 |
| 15 | chain_T_C_U_M_T_C_U_M_T_C | T→C→U→M→T→C→U→M→T→C | 10 |

### 复合提示风格（场景描述，而非工具名）

| 组 | 工具 | 复合提示示例 |
|---|---|---|
| math | math_gcd | "I want to simplify the fraction 48/36. What's the largest number that evenly divides both?" |
| math | math_factorial | "In how many different orders can 7 people stand in a line?" |
| math | math_power | "A data center doubles its servers every year. Starting from 1, how many are there after 10 years?" |
| text | text_reverse | "If you spelled the word 'Python' backwards, what would you get?" |
| text | text_count_chars | "My password must be at least 12 characters. How long is 'Machine Learning'?" |
| text | text_count_words | "The sentence 'To be or not to be that is the question' — how many words does it have?" |
| unit | unit_temp | "Water boils at 100°C. At what temperature does it boil in Fahrenheit?" |
| unit | unit_base | "I need to represent the number 255 in binary for a network mask. What's the binary form?" |
| unit | unit_miles | "A road sign says 26.2 miles — what is that in kilometers?" |
| code | code_caesar | "Send a secret message: rotate each letter in 'HELLO' forward by 5 positions." |
| code | code_rot13 | "Apply the standard ROT13 substitution to the word 'PYTHON'." |
| code | code_md5 | "Generate a fingerprint hash of the string 'password123' using MD5." |

---

## 监测指标

| 指标 | 来源 | 用途 |
|---|---|---|
| **准确率 (per-turn / per-task)** | TurnMetrics.correct | H1 |
| **TTFT (按 turn_idx 分组)** | TurnMetrics.ttft_seconds | H2，turn 0=热身，turn 1+ 显示缓存效果 |
| **vLLM prefix cache hit rate** | /metrics delta per strategy | H2 全局指标 |
| **tools_presented** | TurnMetrics.tools_presented | 验证各策略工具数正确 |
| **output_tokens** | TurnMetrics.output_tokens | 排查异常（死循环等） |

重点观察：在 8-10 轮长任务中，`mask_logit` / `mask_hint` 的 turn 5+ TTFT 应**显著低于** `remove_dynamic`。

---

## 需要修改的文件

### 1. `strategies.py`
- 删除 `make_remove_static_strategy`
- 新增 `make_mask_hint_strategy`（返回 `{"user_message_prefix": hint}`）：
  ```python
  def make_mask_hint_strategy(schedule):
      def strategy(all_tools, turn_idx):
          available = schedule.get(turn_idx, [])
          hint = f"[Available tools this turn: {', '.join(available)}]\n\n"
          return all_tools, {"user_message_prefix": hint}
      return strategy
  ```
- `build_strategy`：删除 `remove_static` 分支，`mask_desc` → `mask_hint`

### 2. `run.py`
- `run_multiturn_task` 提取 `user_message_prefix` 并注入：
  ```python
  turn_tools, extra_params = strategy(all_tools, turn_idx)
  user_prefix = extra_params.pop("user_message_prefix", "")
  actual_user_msg = user_prefix + user_msg if user_prefix else user_msg
  # extra_params 剩余部分（如 logit_bias）合并入 StreamOptions.extra
  ```
- 无 `tool_choice="required"`（仅靠系统提示）

### 3. `config.yaml`
- `strategies.vllm`: `[all, remove_dynamic, mask_logit, mask_hint]`
- 更新系统提示（强制工具调用文字版）

### 4. `prepare_tasks_synthetic.py`
- 重写为 15 个任务，3-10 轮，复合提示
- `tool_availability_schedule` 仍按组（整组 5 工具）

### 5. `experiments/012_mask_vs_remove_v2/plan.md`（新建）
- 保存完整实验设计文档，供后续 review

---

## 执行前清理
- 删除 `experiments/012_mask_vs_remove_v2/results/*.json`
- 删除 `observer/data/exp_012_*`

---

## 两阶段执行

**Phase 1 Pilot**：3 个任务（任务 #1 短3轮、#9 中6轮、#13 长10轮），4 种策略，验证：
- 所有 turn 的 tool_called ≠ None
- mask_hint / mask_logit 的 turn 2+ TTFT 低于 remove_dynamic
- 长任务缓存效果更明显

**Phase 2 Full**：全部 15 任务 × 4 策略 × 1 run

---

## 验收标准

1. 所有 turn 的 tool_called ≠ None（系统提示有效）
2. `mask_logit` 准确率 ≥ `all`（无 token 碰撞）
3. `remove_dynamic` 准确率 ≥ `all`（工具集小，选择更容易）
4. TTFT turn1+ 排序：`remove_dynamic` > `all` ≈ `mask_logit` ≈ `mask_hint`
5. 长任务（10 轮）缓存命中率差异最显著
