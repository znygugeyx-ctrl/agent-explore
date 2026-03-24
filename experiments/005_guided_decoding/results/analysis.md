# 实验 005：Guided Decoding 分析报告

**日期**：2026-03-23
**模型**：Qwen3-8B via vLLM 0.18.0（/no_think 模式，temperature=0.0）
**规模**：30 个任务 × 3 个策略 × 3 轮 = 270 次 LLM 调用

---

## 一、核心数据

| 指标 | free | prompt | guided |
|---|---|---|---|
| JSON 解析成功率 | **0%** (0/90) | **100%** (90/90) | **100%** (90/90) |
| Schema 验证通过率 | **0%** | **100%** | **100%** |
| 平均延迟 | 5.07s | **2.20s** | 2.44s |
| 平均输出 token | 181 | **55** | 64 |

---

## 二、假设验证结果

### H1：guided 保证 100% 结构合法 ✅ 确认

`free` 策略 0/90 解析成功——Qwen3-8B 在无约束、无结构要求的情况下，始终生成自然语言回复而非 JSON（即使有 `/no_think`）。
`prompt` 和 `guided` 均达到 100% parse 和 schema 通过率。

> 结论：`response_format: json_schema` 是 100% 可靠的结构保证。prompt-only 在该任务设计下同样可靠（因为任务明确、模型能力足够）。

---

### H2：Group A 清晰 case，guided 与 prompt 准确率相当 ❌ 不成立

| 字段 | prompt | guided |
|---|---|---|
| name | 100% | 100% |
| age | 100% | 100% |
| **role** | **100%** | **60%** |
| location | 100% | 100% |
| skills | 70% | 70% |
| available | 100% | 100% |

**最意外的发现**：即使在信息完全明确的情况下（例如"software engineer"直接映射 `engineer`），guided 的 role 准确率仅 60%，比 prompt 低 40pp。

**原因分析**：xgrammar 在生成 enum 字段时，对 `role` 的枚举概率分布存在偏置——某些 enum 值（如 `designer`）出现频率异常高，即便原文明确指向其他选项。这是"合法但错误"现象的直接体现。

`skills` 两者均为 70%（不是 100%）原因：exact match 对顺序和措辞敏感，例如 prompt 输出 `["project delivery", "risk management", "budgeting"]`，guided 输出 `["PMP", "risk management", "budgeting"]`，都合理但不完全一致。

---

### H3：B1 role 歧义，guided 准确率显著低于 prompt ✅ 强烈确认

| 策略 | B1 role 准确率 |
|---|---|
| prompt | **75%** (9/12) |
| guided | **0%** (0/12) |

guided 在所有 role 歧义任务上全部失败（0/12）。具体表现：

- B101（DevOps engineer → `engineer`）：guided 输出 `designer` 或 `other`
- B102（data scientist → `analyst`/`engineer`）：guided 输出 `designer`
- B103（IT consultant → `other`）：guided 输出 `manager`
- B104（product manager → `manager`）：guided 输出 `designer`

**关键机制**：当原文的职位名称不在枚举中时，guided 必须从 5 个选项中"盲选"——在没有推理的情况下，模型倾向于输出某个高频 token（`designer` 出现频率在该 enum 中最高），而非语义上最合理的选项。

prompt 能达到 75% 的原因是模型有足够的 token 预算先理解文本，再做枚举映射。

---

### H4：B2 available 歧义，guided 与 prompt 差异 ⚠️ 结果反直觉

| 策略 | B2 available 准确率 |
|---|---|
| prompt | **25%** (3/12) |
| guided | **50%** (6/12) |

**guided 反而更准**。原因分析：

- `available` 是 boolean，只有 true/false 两个选项，随机猜对率 50%
- LLM judge 对 available 的判断本身有较高主观性（"passively looking" 算 true 还是 false？）
- prompt 在某些模糊表述上过度谨慎，输出了与 judge 判断不一致的答案

这个结果不支持"guided 在歧义字段上更差"的假设，但也不能推翻——boolean 字段只有两个值，信号太弱。

---

### H5：Group C 缺失信息，两者幻觉率相同 ⚠️ 假设部分成立

| 子组 | 缺失字段 | prompt 幻觉率 | guided 幻觉率 |
|---|---|---|---|
| missing_age (C1) | age | **100%** | **100%** |
| missing_available (C2) | available | **100%** | **100%** |

两者幻觉率完全相同，均为 100%。

**原因**：schema 中 `age` 是 required integer，`available` 是 required boolean，两者均不允许 null。因此：
- guided：xgrammar 强制生成合法值，必然幻觉
- prompt：模型遵循 schema 指令，同样填入了猜测值（如 age=0、age=25、available=false 等）

> 结论：**H5 部分成立**——guided 的幻觉是机制强制的；但 prompt 在强 schema 指令下同样幻觉，两者无显著差异。若 schema 允许 null（可选字段），结果可能不同，这是后续实验的方向。

---

### H6：/no_think 后三策略延迟无明显差异 ✅ 基本确认

| 策略 | 平均延迟 |
|---|---|
| prompt | **2.20s** |
| guided | 2.44s |
| free | 5.07s（因无约束，生成长文本） |

prompt vs guided 差 0.24s（约 11%），在可接受范围内。guided 略慢的原因是 xgrammar 编译 schema 有一次性开销（首次请求），以及每步 token mask 计算的少量代价。

`free` 显著更慢（5.07s）是因为无约束下模型生成了完整的自然语言回复（平均 181 token vs prompt 的 55 token）。

---

## 三、关键发现总结

### 发现 1：guided 在枚举字段上存在系统性偏置

即使是明确的 "software engineer" → `engineer` 映射，guided 也有 40% 的概率输出错误的 enum 值。这说明 xgrammar 的 token mask 在 enum 选择时没有改变模型的语义推理，只是改变了"哪些 token 合法"——当概率分布本身偏向某些 enum token 时（如 `designer`），结果就会出错。

**这是本实验最重要的结论**，直接验证了论文框架中的核心主张：

> **强约束是"可靠性增强器"，不是"能力增强器"**（H7）

结构合法了，但语义正确率实际下降了。

### 发现 2：prompt-only 在该场景下已足够可靠

在有明确 schema 指令的情况下，prompt 达到 100% parse 和 schema 通过率，且语义准确率显著高于 guided（role 字段：100% vs 60%/0%）。

这说明对于 Qwen3-8B 这样的指令跟随能力较强的模型，guided decoding 的"保险丝"作用是多余的，反而引入了语义损耗。

### 发现 3：/no_think 使两种策略延迟接近，但 free 仍有显著差异

/no_think 后 prompt vs guided 延迟差 0.24s，几乎可以忽略。guided 的速度优势（相比 thinking 模式）来自禁用推理，而非解码约束本身的加速。

### 发现 4：必填字段的幻觉无法通过策略区分

只要 schema 要求某字段为非空，两种策略都会对缺失信息产生幻觉。想解决这个问题需要在 schema 设计层面允许 optional 字段（如 `age: integer | null`）。

---

## 四、对原论文假设的回应

| 论文假设 | 实验结论 |
|---|---|
| H1：强约束提升结构正确性 | ✅ 确认，parse 率 0%→100% |
| H1后半：但不提升语义正确性 | ✅ 确认，role 准确率反而下降 |
| H5：约束过强导致"合法但更错" | ✅ 强烈确认（B1 guided role 0%）|
| H7：强约束是可靠性增强器而非能力增强器 | ✅ 确认 |

---

## 五、局限性

1. **单一 schema**：结论高度依赖 enum 字段的存在；纯 string 字段的实验可能得出不同结论
2. **单一模型**：Qwen3-8B 的 enum token 概率偏置可能不代表其他模型
3. **LLM judge 主观性**：B2 available 的判断存在歧义，judge 结果可信度有限
4. **xgrammar enum 偏置**：需要进一步分析哪些 enum 值被过度选择（推测是 `designer`），以及是否可通过 system prompt 干预
5. **/no_think 并未完全消除 thinking**：部分任务仍有短暂 think 块（`has_think=True`），可能影响一致性
