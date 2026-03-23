# Logit Mask 工具访问控制：原理、实现与实验结论

**日期**：2026-03-22  
**模型**：Qwen/Qwen3-8B（via vLLM 0.18.0）  
**基础设施**：AWS g6e.2xlarge（NVIDIA L40S 48GB）

---

## 一、背景：为什么需要工具访问控制

在 agent 系统中，工具列表通常有几十甚至上百个。对于特定任务，大多数工具是无关的。工具访问控制的目的是让模型在当前任务下只"使用"相关工具，有几种做法：

| 策略 | 做法 | 本质 |
|------|------|------|
| **Remove** | 从提示词里直接删掉无关工具的定义 | 上下文层面隔离 |
| **Desc Mask** | 保留工具定义，但在描述前加 `[UNAVAILABLE]` | 靠模型自觉 |
| **Logit Mask** | 保留工具定义，在生成阶段用 `logit_bias` 压制对应 token | 生成层面强制 |

Logit Mask 的核心特性：**模型仍然看到全部工具的语义信息**（有利于推理），但在输出阶段被物理阻止写出被屏蔽工具的名字。

---

## 二、Logit Bias 原理

LLM 生成每一个 token 的过程：

```
输入上下文
    ↓
Transformer 前向传播
    ↓
输出 logits 向量（词表大小，如 152k）
    ↓  ← logit_bias 在这里介入
调整后 logits = raw_logits + logit_bias
    ↓
Softmax → 概率分布
    ↓
采样 → 下一个 token
```

`logit_bias` 是一个稀疏字典 `{token_id: bias_value}`，在 softmax 之前直接叠加到 logits 上。设置 `bias = -100`，经过 softmax 之后：

```
P(token) = exp(logit - 100) / sum(...)  ≈  0
```

即该 token 的生成概率被压到接近零，实际上不可能被采样到。

**关键**：这发生在 GPU 的每一次 token 采样步骤里，是物理上的阻断，不依赖模型理解"不应该调用"这条指令。

---

## 三、Mask 实施过程

### 3.1 获取工具名对应的 Token ID

工具名在 JSON 输出里作为字符串出现（如 `"name": "calculator"`），BPE tokenizer 对同一个词在不同位置可能编码不同。实验收集了两种变体的首 token：

```
"calculator"   → token_id 88821
" calculator"  → token_id 29952   （空格前缀变体）
```

只取**第一个 token**，因为屏蔽首 token 就足以阻止整个词被生成。

同时过滤掉被 3 个以上工具名共享的 token（说明该 token 太泛化，屏蔽它会误伤其他正常输出）。

本实验 8 个工具的 token map：

| 工具名 | Token IDs |
|--------|-----------|
| calculator | 29952, 88821 |
| string_reverse | 914, 917 |
| char_count | 1161, 1762 |
| base_convert | 2331, 3152 |
| caesar_cipher | 924, 2162 |
| temperature_convert | 9315, 34558 |
| gcd | 44858, 91289 |
| word_count | 1158, 3409 |

### 3.2 构造 logit_bias 字典

对于某个任务，假设相关工具为 `[calculator, gcd]`，其余 6 个工具无关：

```python
logit_bias = {
    "914": -100, "917": -100,       # string_reverse
    "1161": -100, "1762": -100,     # char_count
    "2331": -100, "3152": -100,     # base_convert
    "924": -100, "2162": -100,      # caesar_cipher
    "9315": -100, "34558": -100,    # temperature_convert
    "1158": -100, "3409": -100,     # word_count
}
```

`calculator` 和 `gcd` 的 token 不受任何惩罚。

### 3.3 注入 API 请求

`logit_bias` 作为额外参数附加在 chat completions 请求里：

```
POST /v1/chat/completions
{
  "model": "Qwen/Qwen3-8B",
  "messages": [...],
  "tools": [全部 8 个工具定义],    ← 工具列表不变，模型能看到所有工具
  "logit_bias": {"914": -100, ...} ← 唯一的差异
}
```

vLLM 在 GPU 采样循环里应用这个字典，对每一个候选 token 做修正，整个过程对模型透明。

---

## 四、对照实验

### 实验设计

对同一个任务（计算 `2**8 + 2**6`，再求与 192 的 GCD）运行 4 种配置：

| Case | logit_bias 施加对象 | 预期 |
|------|---------------------|------|
| A — No mask | 无 | 模型自由选择 |
| B — Correct mask | 屏蔽 6 个无关工具 | 模型正常完成，有硬件级保证 |
| C — **Inverted mask** | **屏蔽 calculator + gcd（必需工具）** | 模型被迫绕过 |
| D — Block all | 屏蔽全部 8 个工具 | 没有任何工具可调用 |

### 实验结果

```
Case                          工具调用结果                   判定
────────────────────────────────────────────────────────────────
Case A — No mask              ['calculator', 'gcd']          ✓ 正确
Case B — Correct mask         ['calculator', 'gcd']          ✓ 正确
Case C — Block needed tools   ['计算器', '计算器', '计算器']  ✗ 失败（绕过）
Case D — Block all tools      ['计算器', '计算器', '计算器']  ✗ 失败（绕过）
```

### Case C 的细节：模型如何绕过

Case C 的 `<think>` 内容（推理阶段，不受 logit_bias 影响）：

> *...first calculate 2\*\*8 + 2\*\*6 using the **计算器** tool...*

模型的推理过程完全正确，知道该用什么工具、参数是什么。但生成阶段写不出英文 `calculator`（token 被封死），于是它找到了"计算器"（中文）作为 escape hatch——这是一个不同的 token，不在黑名单里。

这个绕过行为是**理性的**：模型确实需要这个工具，它在寻找所有可能的替代路径。

### Case C ≈ Case D

值得注意的是，Case D（全屏蔽）的输出与 Case C **完全相同**（token 用量、工具调用内容逐字一致）。说明模型在 Case C 就找到了 `计算器` 这个 escape hatch，剩余工具是否被屏蔽已经无关紧要。

---

## 五、实验 002 v1 vs v2 的关键教训

v1 实验犯了一个设计错误：对需要 `[calculator, gcd]` 的任务，按**步骤**分配工具：

- 第 1 轮：只给 `[calculator]`，隐藏 `gcd`
- 第 2 轮：只给 `[gcd]`，隐藏 `calculator`

这实际上就是 **Case C 的情形**——模型在某一轮被剥夺了它需要的工具。观察到的"logit mask 绕过"（中文名、拼写错误、点号前缀）正是这种合理绕过行为的体现，并非 logit_bias 本身的缺陷。

v2 修正为按**任务**静态分配：整个任务的所有轮次都看到同一份工具列表，无关工具才被屏蔽。绕过行为完全消失，准确率从 95% 提升至 100%。

---

## 六、结论

**Logit mask 的可靠性边界**

| 场景 | 结果 |
|------|------|
| 屏蔽真正无关的工具 | ✓ 可靠，无绕过，0 条 invalid_tool_calls |
| 屏蔽模型实际需要的工具 | ✗ 模型会尝试中文/变体/拼写错误等方式绕过 |

`logit_bias` 控制的是**生成能力**，不是**推理能力**。模型的 `<think>` 过程不受任何干预，它始终知道正确的工具是什么；logit_bias 只是在最终输出阶段做物理拦截。

因此，"屏蔽真正无关的工具"和"阻止模型使用某个它需要的工具"是两个完全不同的问题，前者用 logit_bias 完全可行，后者需要从任务设计层面解决（不应该让模型感知到它需要但又无法使用的工具）。
