# 014 与 "Towards a Science of Scaling Agent Systems" 论文对齐

**日期**：2026-05-24
**触发**：用户指出当前 benchmark 过于简单 / 不贴合实际使用，需要参考 Google Research / DeepMind 这篇 2026-04 论文重选。

## 论文核心结论

- MAS 是否优于 SAS **完全取决于任务结构**：极差从 +80.8% 到 -70.0%
- 论文 6 个 benchmark 极差很大：
  - **Finance Agent**: +57% ~ +81%（MAS 最大胜场）
  - **Workbench**: -11% ~ +6%（中性）
  - **PlanCraft**: -39% ~ -70%（MAS 最大败场）
- 3 条 scaling 法则：
  1. Tool-coordination trade-off (β=-0.096, p=0.002)：tool 多 → MAS 协调税重
  2. Capability ceiling (β=-0.236, p=0.004)：single 已 >45% 时加 agent 负收益
  3. Architecture-dependent error amplification: Independent 17.2× / Centralized 4.4×
- **agentic task 必要属性**（论文 §3.2）：
  - Sequential interdependence（动作依赖前一步观察）
  - Partial observability（信息隐藏需主动查）
  - Adaptive strategy formation
  - Action-Observation loop length L > 3

GSM8K / MMLU / HumanEval / SQuAD / Bamboogle / FanOutQA 都是 **non-agentic**——L 不够。

## 与之前实验的对照偏差

```
之前用                    论文判定
─────────────────────────────────────────────
MATH-500              ✗ non-agentic（single-shot 推理）
HumanEval+            ✗ non-agentic（specification-complete）
Bamboogle             ✗ L≈2-3 太短
FanOutQA              ✗ L≈2-3 + 答案漂移
```

**结论**：之前 4 个 benchmark 三模式表现都接近——不是 single/OW/SW 没差异，而是任务本身根本不需要 multi-step interaction，所以三种架构都饱和或都失败。

## 修正后的 3 任务方案（用户已同意）

| Task | 论文对应 | 假设的 MAS 表现 | 工具数 | 题量 |
|---|---|---|---|---|
| **T1: WorkBench** | ±6% | 中性，看 tool-coord 税 | 26 | pilot 30 / full 690 |
| **T2: FinanceBench**（替代论文 Finance Agent；后者需付费） | +80% | MAS 主场 | web search | pilot 30 / full 150 |
| **T3: PlanCraft** | -70% | MAS 反主场 | 4 | pilot 30 / full 100 |

每个 benchmark **任何方向的结果都有信息量**（论文已给方向预测）。

## 工程路径决策

CC `--print` 自带 WebSearch / Bash / Edit 等通用工具，但**不知道** WorkBench 的 calendar 工具、PlanCraft 的 craft 等 domain-specific 工具。三条路径：

| 路径 | 描述 | 工程量 | 是否符合 agentic |
|---|---|---|---|
| **A. MCP server 包装** | 每个 benchmark 写 MCP server 暴露工具给 CC | ~6h/bench | ✅ 真正 agentic |
| B. agent 输出意图，外部执行 | agent 在 final_text 输出 ACTION=...，外部 dispatch | ~1h/bench | ❌ 缺 obs-feedback |
| C. 放弃，找现成 MCP | 几乎没有满足 "轻量 + agentic + 无 docker" 全条件的 | — | — |

**用户选择路径 A**。预期总工程量 ~15h（3 benchmark × 5h），换得真正的 agentic 实验。

## 工程清单（执行中）

执行顺序：
1. WorkBench MCP server（最有价值，sandbox + 26 工具 + 5 domain，能复用）
2. 跑 30 题 × 3 模式 pilot，验证整套 MCP 路径走通
3. 如成功 → 接 FinanceBench MCP（轻：sec-edgar 检索 + 文档读取）
4. 接 PlanCraft MCP（中：4 工具 + inventory 状态查询）
5. 全量 pilot：30 题 × 3 模式 × 3 benchmark = 270 runs

## Benchmark 装备状态（已完成）

- ✅ WorkBench: cloned 到 `_vendor/WorkBench/`（git@olly-styles/WorkBench, 690 题, 26 tools, 5 domain）
- ✅ FinanceBench: HF `PatronusAI/financebench`, 150 题
- ✅ PlanCraft: `pip install plancraft` 已装（gautierdag/plancraft）

## 还要清理掉的

- ❌ 删 `tasks/t1_math.jsonl` `t2_bamboogle.jsonl` `t3_humanevalplus.jsonl`
- ❌ 旧的 dashboard 数据（之前 18+6 runs）准备清空，重新开始
- ❌ verifiers.py 的 verify_math / verify_humanevalplus / verify_bamboogle / verify_fanoutqa 都将作废
- ⚠ `runner/cc_runner.py` 需要支持 `--mcp-config` 参数传给 claude

## 假设清单（实验结束后回看）

- **H1（架构-任务对齐）**：T2 OW > Single；T3 OW < Single；T1 OW ≈ Single
- **H2（协调税）**：T1 (26 工具) 的 OW 协调开销比 T3 (4 工具) 更糟
- **H3（饱和效应）**：T2 上 OW 收益和 (1 - single_baseline) 正相关

定性方向对就是成功复现，**不追求绝对数值**。

## 下次接续提示

如果对话中断，状态：
- 三个 benchmark 都已 vendored / 装好
- 现在要写 WorkBench MCP server
- 路径已与用户确认（路径 A）
- pilot 规模 270 runs，可接受

## 进度更新（2026-05-24 续）

- ✅ WorkBench MCP server 骨架写完 (`mcp_servers/workbench_server.py`)
- ✅ 验证 27 个 WorkBench tools 全部 register 成功
- ⏳ 下一步：写 task runner 起 MCP server + 调 CC，跑 1 个 calendar task 端到端
- ⏳ 写 verifier：比较 sandbox state vs ground-truth state

## 关键工程要点

- WorkBench tool 是 LangChain `@tool` 装饰的函数，有 `.name` 和 `.func` 属性
- 每个 task 一个独立 server 子进程（保 sandbox 隔离）
- atexit 把最终 sandbox dump 到 `/tmp/wbench_state_<task_id>.json`
- MCP tool 名用 `_` 替换 `.`（MCP 名字规则不允许 `.`）

## 进度更新 - WorkBench 端到端打通 ✅

**关键里程碑**：calendar/81 任务 PASS（25s）
- CC `--print --mcp-config` 起 MCP server 子进程成功
- 27 个 WorkBench 工具全部可被 CC 看见和调用
- 5 次 tool 调用后 sandbox state 与 ground-truth 完全一致
- 4 domain state 比对全部 PASS

**踩过的坑**：
1. FastMCP 装饰 `**kwargs` wrapper → schema 失败 → 改用 exec 合成真实签名
2. atexit dump 不可靠（CC 关 stdio 后强杀） → 改 per-call dump
3. `customer_relationship_manager` 模块全局变量名是 `CRM_DATA` 不是 `CUSTOMERS`
4. `execute_actions_and_reset_state` 返回 6-tuple 而非读模块全局（函数末尾已 reset）

**剩余 WorkBench 工作**：
- ⏳ 把 1 题端到端扩展到 30 题 × 3 模式（Single/OW/SW）
- ⏳ 把 verifier 整合进 pilot 主 runner
- ⏳ dashboard 适配 workbench 任务展示

**状态判断**：路径 A 已证实可行，工程量在控制范围内。继续推下一个 benchmark（FinanceBench 或 PlanCraft）。
