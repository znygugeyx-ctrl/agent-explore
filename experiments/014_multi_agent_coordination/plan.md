# Experiment 014: Multi-Agent Coordination Patterns

> **状态**：讨论草稿（2026-05-06）。尚未锁定假设、任务集、benchmark、具体组数。
> 本文件保留从 idea 起步到当前的完整讨论过程，作为后续细化的上下文。

---

## 0. 背景与动机

- Anthropic 官方博客 [Multi-Agent Coordination Patterns](https://claude.com/blog/multi-agent-coordination-patterns) 提出五种 multi-agent 协调模式
- 另一份讨论文档 `/Users/zny/Documents/Codex/2026-04-27/https-claude-com-blog-multi-agent/multi-agent-experiment-design.md` 已经草拟了一版大规模实验方案
- 目标是**系统性、严谨地**比较这几种架构，**充分利用 Claude Code / Claude Agent SDK 工程级实现**
- 实验设计原则（用户明确要求）：
  1. 不考虑工程量，只考虑**实验完整性与严谨性**
  2. 不受以前实验（007/011/012/013）的思路牵制，从实验本身出发
  3. 全面比较，**充分利用现有 Claude Code 基础设施**

---

## 1. 博客定义的五种 Pattern（权威定义）

来源：https://claude.com/blog/multi-agent-coordination-patterns

| # | Pattern | 结构 | 主场特征（博客） | 典型任务（博客） |
|---|---|---|---|---|
| 1 | **Generator-Verifier** | Generator 产出，Verifier 按显式标准验证，失败反馈回 Generator 直到通过或到达上限 | 有明确验证标准、错误成本高 | 代码生成、客服邮件、事实核查、合规检查 |
| 2 | **Orchestrator-Subagent** | Lead agent 规划拆解、派发 bounded subtask、汇总 subagent 结果 | 可分解为互不依赖子任务、需 lead 统一整合 | 多角度代码审查 |
| 3 | **Agent Teams** | Coordinator 生成持久 worker，workers 从 shared queue 领任务、自主多步执行、跨任务积累 domain context | 并行独立长任务、worker 需跨任务保留上下文 | 大规模代码框架迁移 |
| 4 | **Message Bus** | Agents 通过 pub/sub 交互，router 按 topic 分发事件；工作流从事件中涌现 | 事件驱动、工作流随发现变化、agent 生态持续扩展 | 安全告警分诊 |
| 5 | **Shared State** | Agents 通过持久共享存储（DB/FS/文档）协调，**无中心协调者**；读发现→行动→写结果 | 协作研究，agent 实时在彼此发现上累积 | 多源研究综述 |

博客核心立场：
- **Orchestrator-Subagent 是默认**（"handles the widest range of problems with the least coordination overhead"）
- **Pattern 选择应该基于任务结构**，不是基于"听起来厉害"
- **Shared State 系统必须把 termination 作为一等设计问题**，否则会出现 reactive loop 无限循环

---

## 2. 关键发现：Claude Code Agent Teams 是 Compound，不是 Pure Pattern

参见：https://code.claude.com/docs/en/agent-teams

Claude Code 原生 Agent Teams 实际上是 **三种机制的 compound**：

```
Claude Native Agent Teams =
    Agent Teams (长期 teammate sessions + team lead)
  + Shared State (shared task list, task claiming, dependencies)
  + Message Bus (mailbox, teammate direct messaging)
```

这对实验设计有三个核心影响：

### 2.1 "Pure Agent Teams" 在工程界几乎不存在
博客定义的 "pure Agent Teams"（长期 worker + task queue + **无通信无 shared state**）是理论构造。Claude Code、CrewAI、AutoGen 的 teams 实现默认都带通信层。**这本身就是一个值得记录的发现：pattern 正交性可能是叙述便利而非工程实在**。

### 2.2 预注册预测表的基础假设受挑战
博客预测 "T3 (refactor) 主场是 Agent Teams"。但 T3 成功是否**必须**依赖 mailbox 或 shared task list？如果"pure Teams"跑不动 T3，博客的预测就隐含了 compound 而不是 pure。这直接决定假设该怎么写。

### 2.3 Claude Code Agent Teams 本身是独立的科学对象
它是 **P3 ∪ P4 ∪ P5 的产品化实现**。"compound 是否 > sum of parts" 是高价值问题 —— 且只能通过 ablation 回答。

---

## 3. Claude Agent SDK 可观测性调查（已完成）

调查结论：**SDK 可观测性基本够用，不需要改 claude-code 源码**。

### 3.1 Hooks（程序化回调，无需 settings.json）
通过 `ClaudeAgentOptions(hooks=...)` 注册：

| Hook | Trigger |
|---|---|
| `PreToolUse` / `PostToolUse` / `PostToolUseFailure` | 每次工具调用前后 |
| `SubagentStart` / `SubagentStop` | 子 agent 启停（含 `agent_transcript_path`） |
| `UserPromptSubmit` / `Stop` / `PreCompact` / `PermissionRequest` / `Notification` | 各种生命周期点 |
| `TeammateIdle` / `TaskCompleted` | TS SDK 明确有，Python SDK 需验证 |

### 3.2 Streaming Events（`include_partial_messages=True`）
- `message_start` / `content_block_start` / `content_block_delta` / `message_stop`
- 子 agent message 携带 `parent_tool_use_id` → 实时关联父子
- thinking blocks 在 `max_thinking_tokens` 模式下不流式

### 3.3 Session 完整 Transcript
- `list_sessions()` + `get_session_messages()` 读全量
- 存储位置：`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- 子 agent transcript 单独存，路径从 `SubagentStop` 拿

### 3.4 Token/成本
`ResultMessage.total_cost_usd`、`model_usage.{inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens}`、`AssistantMessage.usage` 每步

### 3.5 OpenTelemetry 原生支持
`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` 自动生成 `claude_code.interaction > claude_code.llm_request + claude_code.tool` 的 span 层级，subagent span 嵌套在父 tool span 下

### 3.6 唯一盲区：Agent Teams 没有程序化 spawn API
- 文档明确：**Agent Teams 目前 CLI/interactive-only**
- 状态落在 `~/.claude/teams/<team>/config.json` + `~/.claude/tasks/<team>/`（可读但非 API）
- 观测路径：`TeammateIdle` / `TaskCompleted` hooks + 文件系统监听
- **fallback**：手里有 Claude Code 2.1.88 源码 `/Users/zny/Documents/LLM/claude-code`，可改源码，但这会让实验结果不再代表"产品行为"

---

## 4. 实验整体框定

### 4.1 核心假设（候选，未最终锁定）

> **博客声称"每种 pattern 有天然适配的任务结构"。我们系统验证：
> (H1) 在每种 pattern 的主场任务上，它是否真能击败 Orchestrator-Subagent 默认方案；
> (H2) 在错配任务上，它的损失有多大；
> (H3) Claude Code 原生 Agent Teams（compound）是否 > sum of parts（纯 Teams / Teams+Bus / Teams+State）。**

### 4.2 公平性原则（必须硬约束）

```
Benchmark task
  -> Common Agent Kernel
       same model (Sonnet 4.6 主实验；Haiku 4.5 / Opus 4.7 作为副实验)
       same tool set (基础工具完全一致，pattern 只加 coordination-specific tools)
       same temperature
       same context limit
       same token/time/cost budget
       same logging
  -> Coordination Layer (唯一变化)
  -> Same Evaluator
```

预算建议两种设置并行：
1. **Equal total budget**：所有方案总 token/成本相同
2. **Equal per-agent budget**：每 agent 预算相同，观察并行扩展上限

---

## 5. 四种架构组方案（逐步增强严谨性）

### 选择 A：Compound Baseline + Pure 三组
```
6 组：Single / GenVer / OrchSub / PureTeams(SDK) / MsgBus(SDK) / SharedState(SDK)
+ 1 组 Compound Baseline：Claude Code Agent Teams
```
- **优点**：严格验证博客 5 个 pure pattern 预测 + 独立评估产品级 compound
- **缺点**：pure Teams 可能在每任务都垫底 —— 但这正是结论

### 选择 B：Claude Native Teams Ablation Tree
通过 `disallowedTools` 或 prompt 关闭子机制：

| 变体 | task list | mailbox | ≈ 近似 pure pattern |
|---|---|---|---|
| CC-Full | ✅ | ✅ | Compound（产品形态） |
| CC-NoMail | ✅ | ❌ | ≈ Teams + Shared State |
| CC-NoList | ❌ | ✅ | ≈ Teams + Message Bus |
| CC-Neither | ❌ | ❌ | ≈ Pure Agent Teams |

- **优点**：在同一 runtime 内做受控变量，消除 "SDK 版 vs CLI 版" 的 confound
- **缺点**：prompt 关闭不是硬隔离，agent 可能"作弊"；需要 hook 合规性校验
- **风险**：CC Teams runtime 内部可能有观察不到的耦合

### 选择 C：双轨并行（当前推荐方案）
```
轨道 1（SDK 纯 pattern）：
  Single / GenVer / OrchSub / PureTeams / MsgBus / SharedState
  + 2 个 pairwise 组合：Teams+Bus, Teams+State

轨道 2（CC Native Ablation）：
  CC-Full / CC-NoMail / CC-NoList / CC-Neither
```
- **9 + 4 = 13 组**
- **优点**：
  - 验证博客的 pure pattern 预测（轨道 1）
  - 独立评估产品 compound 与内部解耦（轨道 2）
  - **交叉对比 SDK-PureTeams vs CC-Neither** —— 验证结论不是实现产物
  - 若两轨一致：effect 是 pattern 本身；若不一致：发现 "Claude Code runtime 本身有隐性机制"
- **缺点**：规模翻倍，~10000 runs

### 选择 D：放弃 "pure pattern" 叙事，直接测 compound 空间
```
Single / GenVer / OrchSub / Teams+State / Teams+Bus / Teams+State+Bus(=CC-Full)
```
- **优点**：工程最干净，所有组都有真实部署场景
- **缺点**：无法直接回答博客的 5-pattern 预测；需要重新设计假设（"哪种 compound 最划算"）

**当前倾向：选择 C**，理由：
1. 博客的 5-pattern 叙事值得严格检验 —— 即使 pure Teams 全败也是关键证据
2. CC Teams ablation 是独立高价值实验 —— Anthropic 自己产品内部机制贡献分解，社区无人做过
3. 交叉对比提供方法论保险：结论不依赖单一实现

---

## 6. 任务矩阵（5 主场任务，5×N 组 cells）

每个 pattern 按博客提示的"主场特征"匹配一个典型任务。每个 pattern 跑所有 5 个任务，形成主场 vs 错配的完整比较。

| 任务 | 主场 Pattern | 博客依据 | Benchmark 候选 |
|---|---|---|---|
| **T1. 代码+测试** | Generator-Verifier | 有显式验证标准（unit test），错误成本高 | LiveCodeBench / HumanEval+ / MBPP+ |
| **T2. 多角度代码审查** | Orchestrator-Subagent | 可分解为互不依赖子任务，需 lead 整合 | CodeReviewer / RepoBench-R / 自建（SWE-bench PR + 4 角度 rubric） |
| **T3. 多文件重构/迁移** | Agent Teams | 长时独立子任务，worker 需累积模块上下文 | SWE-bench Multi-file 子集 / Commit0 / 自建（N 文件 API 迁移） |
| **T4. 事件分诊路由** | Message Bus | 发现驱动路由，多专家响应 | τ-bench (airline/retail，多 domain) / SOSbench |
| **T5. 多源研究综述** | Shared State | 发现相互启发累积，无中心协调 | FRAMES / FanOutQA / HotpotQA fullwiki |

### 6.1 规模估算

- 5 tasks × ~50 题 × 13 patterns × 3 seeds ≈ **9750 runs**（若选 C）
- 或 5 tasks × ~50 题 × 6 patterns × 3 seeds ≈ **4500 runs**（若选 A 的 6 组）
- 平均 per-run ~150K tokens → 总计约 0.7–1.5B tokens
- 参考：011 规模 7200 calls

---

## 7. 预注册预测表（A/B/C/D = 最优/中等/偏弱/显著劣后）

实验前锁定，实验后检验博客预测是否成立。

| | T1 code+test | T2 review | T3 refactor | T4 triage | T5 research |
|---|---|---|---|---|---|
| Single | C | C | D | D | C |
| Gen-Verify | **A★** | B | C | C | C |
| Orch-Sub | B | **A★** | B | B | B |
| Pure Teams | D | C | **A★?** | C | C |
| Msg Bus | D | C | C | **A★** | B |
| Shared State | C | B | B | B | **A★** |

**★ = 博客预测的主场胜者**

**关键附加预测**：
- **Pure Teams 在 T3 上成功率可能 < 30%**（如果 T3 任务含跨文件依赖，pure Teams 因无通信无共享状态，无法协调 —— 这将说明博客的 "Agent Teams" 其实隐含了 compound）
- **CC-Full 在 T3 上 > SDK PureTeams**（compound 必然 beat pure）
- **CC-Neither ≈ SDK PureTeams**（同一概念的两种实现应一致，否则说明实现 confound）

---

## 8. 评估指标（每 cell 都记录）

### 8.1 主指标（程序化）
- 任务准确率 / pass@1（代码）/ 关键事实召回率（研究任务）
- 任务完成率（未超 budget 且产出最终答案）

### 8.2 过程指标
- 总 token（input / output / cache hit / cache write 分开）
- 端到端延迟
- LLM 调用次数 / 工具调用次数 / subagent/teammate 数量
- 重试次数（Gen-Verifier）
- **信息流动率**：
  - Shared State 的写入被其他 agent 读取并影响行动的比例
  - Message Bus 的事件消费率与无效事件率
  - Orch-Sub 的子 agent 发现是否被 lead 保留到最终答案
- **冲突/重复劳动率**（Teams）
- **终止正确性**：
  - Shared State：是否出现无限反应循环
  - Teams：所有任务是否领取完毕

### 8.3 复合指标
- **每单位正确率的 token 成本**（关键 trade-off 指标）
- **方差**：3 seed 下每 cell 的 std

### 8.4 LLM-as-Judge（仅补充程序化指标不能覆盖的维度）
- 报告完整性、推理质量、结论充分性、协作过程合理性、发现复用度
- 必须：盲评 + 随机化候选顺序 + pairwise 优先于打分 + 多次评估计算一致性

---

## 9. 实现架构（工程草图）

```
experiments/014_multi_agent_coordination/
  plan.md                  # 本文件
  hypothesis.md            # 待写：锁定假设 + 预注册预测
  config.yaml              # 待写：所有参数
  run.py                   # 待写：入口（支持断点恢复）
  harness/
    sdk_runner.py          # Claude Agent SDK Python 封装：query() + hooks
    observer_adapter.py    # hook callbacks → observer/client.py
    cc_team_driver.py      # CLI subprocess 驱动 Claude Code Agent Teams
    budget_guard.py        # token/time/cost budget 强制执行
  patterns/
    single.py
    gen_verifier.py
    orchestrator_subagent.py
    pure_teams.py
    message_bus.py
    shared_state.py
    teams_plus_bus.py
    teams_plus_state.py
    cc_full.py
    cc_nomail.py
    cc_nolist.py
    cc_neither.py
  tools/
    pub_sub.py             # custom tools: publish / subscribe (for Message Bus)
    state_store.py         # custom tools: read_state / write_state + SQLite
    task_queue.py          # custom tools: claim_task / complete_task (for Pure Teams)
  tasks/
    t1_code_test/
    t2_code_review/
    t3_refactor/
    t4_triage/
    t5_research/
  eval/
    programmatic.py        # 每任务的程序化 verifier
    llm_judge.py           # 盲评 + pairwise
    metrics.py             # process metrics 计算
  results/
```

### 核心抽象
```python
class AgentKernel:
    def run(prompt, session_id, tools, budget, cwd) -> RunResult
    def resume(session_id, prompt) -> RunResult
    def collect_usage() -> Usage
    def collect_trace() -> Trace

class CoordinationLayer:
    def run_task(task) -> Output
    def enforce_protocol()  # 合规性检查：是否违反 pattern 边界
    def emit_trace()

class Evaluator:
    def score(task, output, workspace) -> float
    def collect_process_metrics(trace) -> Metrics
```

### 观测架构
```
SDK Python (轨道 1)
  ├── PreToolUse/PostToolUse hooks → observer/client.py
  ├── SubagentStart/SubagentStop → agent_transcript_path → observer
  ├── Streaming events (partial_messages) → token-level log
  └── ResultMessage.model_usage → cost tracker

Claude Code CLI (轨道 2, Agent Teams)
  ├── CLI subprocess + settings.json hooks
  ├── 文件监听 ~/.claude/tasks/<team>/, ~/.claude/teams/<team>/
  └── TeammateIdle / TaskCompleted 事件
```

---

## 10. 关键工程注意事项

### 10.1 控制 Claude Code 隐式配置
Claude Code / SDK 可能读取项目 CLAUDE.md / agents / skills / hooks。为保证可复现：
- 主实验中明确设置 setting sources
- 关闭不必要隐式配置
- 所有实验组使用同一份配置
- 固定 Claude Code / SDK 版本
- 固定模型、max turns、权限模式、allowed tools

### 10.2 文件系统隔离
- 每个 run 使用独立 workspace
- 多 worker 修改代码时使用独立 git worktree 或 container
- 最终由 harness 合并 patch，或每个 worker 只能修改自己的路径分区
- 记录冲突和合并失败

### 10.3 协议合规测试（必须自动化）
用 hook 日志校验每组真正遵守 pattern 边界：
- Pure Teams 中没有 message / state tool 调用
- Message Bus 组所有跨 agent 通信都经过 event log
- Shared State 组所有共享信息都经过 state store
- Orchestrator-Subagent 组 subagent 只把 final result 返回 parent
- Generator-Verifier 组 verifier 不直接修改最终答案（除非实验允许）

### 10.4 日志与可观测性（每 run 必记录）
```
run_id / task_id / pattern / model / agent_id / session_id / prompt_hash
tool_calls / events / state_reads / state_writes
token_usage / cost_estimate / latency
final_output / score / failure_reason
```

### 10.5 Agent Teams 合规性验证的具体问题
- Claude Code Agent Teams 内部的 mailbox / task_list 是否作为可禁用的 tool 暴露？
- 如果是：Ablation 可通过 `disallowedTools` 硬隔离
- 如果否：只能靠 prompt 建议 + hook 合规日志事后验证，隔离强度降低
- **待用 `claude-code-guide` 确认**

---

## 11. 副实验（主实验走通后考虑）

- **模型跨度**：Haiku 4.5 + Sonnet 4.6 + Opus 4.7，验证 pattern 优势是否与模型规模相关
- **Pattern 组合**：P2+P1（Orch-Sub 内嵌 Verifier）、P5+P4（State+Bus） —— 博客暗示真实系统会混用
- **CC Ablation 深化**：除了 mailbox / task_list，再尝试关闭 team lead（看是否退化成 pure Teams）

---

## 12. 需要用户拍板的关键决策点

### 12.1 架构组方案（最核心）
- [ ] 选 A / B / C / D？当前推荐 **C（双轨 13 组）**
- 如果选 C，接受 ~10000 runs 规模吗？

### 12.2 CC Teams 内部机制可否硬禁用
- [ ] 需要调查：mailbox / task_list 是否作为 tool 暴露，可通过 `disallowedTools` 硬隔离？
- 影响：决定轨道 2 的 ablation 是硬隔离还是软约束
- 可用 `claude-code-guide` skill 确认

### 12.3 Benchmark 最终选择
- [ ] T1：LiveCodeBench / HumanEval+ / MBPP+？
- [ ] T2：SWE-bench PR + 自建 rubric？还是 CodeReviewer？
- [ ] T3：SWE-bench Multi-file 子集 / Commit0 / 自建迁移任务？
- [ ] T4：τ-bench retail+airline / SOSbench / 自建分诊集？
- [ ] T5：FRAMES / FanOutQA / HotpotQA fullwiki？
- 可用 `benchmark-library` skill 深度评估每个候选

### 12.4 预注册预测精确度
- [ ] 当前 A/B/C/D 粗分级是否升级为定量区间（如 "T1 上 Gen-Verify 准确率 > Single +15pp ±5pp"）？

### 12.5 "Pure Teams 在 T3 上失败" 作为强预注册预测
- [ ] 接受吗？接受的话 014 就不是"让每个 pattern 都有机会"，而是"让某些 pattern 证明自己无法独立存在" —— 对博客结论更强的检验

### 12.6 预算设置
- [ ] Equal total budget / Equal per-agent budget 都跑？还是只跑一个？

### 12.7 模型选择
- [ ] 主实验 Sonnet 4.6 确认？
- [ ] 副实验跨模型何时触发？

---

## 13. 下一步

1. 用户基于本文档讨论并锁定 §12 的决策点
2. 最终方案锁定后：
   - 写 `hypothesis.md`：锁定假设 + 预注册预测矩阵 + 成功/失败标准
   - 写 `config.yaml`：所有参数
   - 用 `benchmark-library` 和 `experiment-design` skill 细化 T1–T5 任务定义
   - 先做 Pilot（建议：选择 2 个 pattern × 2 个任务 × 10 题，验证 harness 和观测链路），再扩全尺度
3. Pilot 通过后进入正式运行；遵循 `CLAUDE.md` 的"断点恢复"要求

---

## 附录 A：参考资料

- Anthropic 博客：https://claude.com/blog/multi-agent-coordination-patterns
- Claude Code Agent Teams：https://code.claude.com/docs/en/agent-teams
- Claude Agent SDK Subagents：https://code.claude.com/docs/en/agent-sdk/subagents
- Claude Agent SDK Sessions：https://code.claude.com/docs/en/agent-sdk/sessions
- Claude Agent SDK Hooks：https://code.claude.com/docs/en/agent-sdk/hooks
- Claude Agent SDK Custom Tools：https://code.claude.com/docs/en/agent-sdk/custom-tools
- Claude Agent SDK Streaming：https://code.claude.com/docs/en/agent-sdk/streaming-output
- Claude Agent SDK Cost Tracking：https://code.claude.com/docs/en/agent-sdk/cost-tracking
- 本地源码 fallback：`/Users/zny/Documents/LLM/claude-code`（2.1.88）
- 前期讨论文档：`/Users/zny/Documents/Codex/2026-04-27/https-claude-com-blog-multi-agent/multi-agent-experiment-design.md`

## 附录 B：agent-explore 框架可复用能力

- `observer/` 服务：持久化 HTTP + SSE + JSONL，用于实时观察 agent context
- `core/agent.py` 的 hook 机制：在本实验中**仅作为 fallback 参考**（本实验主走 SDK/CC 原生 infra）
- `bench/` 基础设施：task loader、parallel runner、verifier、stats aggregator
- 实验必须 `attach_observer(config, task_id, run_id="exp_014_multi_agent")`
