# 实验 012：Mask vs Remove v2 — 升级版假设验证

## 背景

Manus 论文（Context Engineering for AI Agents）在"遮蔽，而非移除"章节主张：
- 在大型工具池（50-100+）场景下，动态移除工具会打断 KV-cache 前缀，增加延迟和成本
- 应保留所有工具在上下文中，仅通过 logit masking 阻断不可用工具的生成
- 工具名称统一前缀（如 browser_*）使组级遮蔽成为可能

实验 001-003 未能找到支持证据。根本原因：
1. **静态工具列表** — 每 task 内工具固定，Manus 的核心场景是轮次间动态切换
2. **vLLM 自动缓存太强** — 块级匹配使小变化几乎不可见，所有策略均 ~99% 命中
3. **上下文太短** — ~10K tokens，cache miss 代价可忽略
4. **无商业 API 测试** — Manus 的经济论点需要 Anthropic 这类 cached/uncached = 10x 成本差的 API

## 核心假设

**H1（Cache 经济学）**：在 Claude/Bedrock 上，轮次间动态移除工具（remove_dynamic）产生比保持工具列表不变（all）更多的 cache miss，导致可量化的更高成本（预期差异 >20%）

**H2（前缀稳定性）**：动态 logit masking（mask_logit）通过保持工具定义前缀不变，实现与 all 相近的 cache 命中率，同时具有 remove_dynamic 无法比拟的可靠性

**H3（模型混淆）**：remove_dynamic 在轮次间移除之前已被引用的工具时，会导致准确率显著低于 all 策略

**H4（模型规模）**：8B 与 14B 在各策略效果上的差异——更强的模型是否对工具列表变化更鲁棒？

## 对比实验 001-003 的升级点

| 维度 | 实验 001-003 | 实验 012 |
|------|-------------|---------|
| 基准 | 自制玩具任务 | BFCL v3 multi-turn（公开标准） |
| 工具变化 | 静态（task 内固定） | **动态（逐轮切换）** |
| 商业 API | 无 | Claude Haiku 4.5（Bedrock）|
| 指标 | 准确率/延迟/cache 命中率 | + 每轮 TTFT + **每 task 成本 $** |
| 模型 | Qwen3-8B 单一 | Qwen3-8B + Qwen3-14B 对比 |
| 工具调度 | 人工或随机 | Claude Opus 4.6 自动推导 |

## 策略定义

### vLLM（5 种）
- **all**：所有工具每轮可见，基线
- **remove_static**：task 相关工具，task 内固定（复现实验 003 设计）
- **remove_dynamic**：每轮仅当轮可用工具，动态变化（打断前缀）
- **mask_desc**：全部工具，不可用工具加 `[UNAVAILABLE]` 标记（前缀变化）
- **mask_logit**：全部工具，不可用工具 logit_bias=-100（前缀稳定）

### Claude/Bedrock（3 种）
- **all** / **remove_dynamic** / **mask_desc**
- 注：Bedrock 不支持 logit_bias，无法测 mask_logit

## 预期结果

若假设成立：
- Claude：`all.cost_per_task < remove_dynamic.cost_per_task`（>20% 差异）
- vLLM：turn 3+ 时 `mask_logit.ttft < remove_dynamic.ttft`
- 准确率：`remove_dynamic.accuracy < all.accuracy`（H3）

若假设不成立：
- 各策略成本/延迟/准确率无统计显著差异
- 本实验结果将作为 Manus 假设的更严格反证
